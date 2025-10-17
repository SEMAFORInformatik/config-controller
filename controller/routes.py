import flask
import pathlib
from flask import current_app, request
from controller import kube, dock
import os


bp = flask.Blueprint('routes', __name__)


def get_properties(confdir, name, logger):
    """return dict with properties statefulset | image (envs, ports, imagepullsecrets, imagepullpolicy)"""
    p = pathlib.Path(confdir) / (name+'.properties')
    d = dict(ports=[], envs=[], parts=[], volumes=[], resources=dict(
        requests=dict(), limits=dict()))
    n = 0
    for l in p.open():
        try:
            k, v = [s.strip() for s in l.split('=')]
            v = v.format(**os.environ)
            if k in ('image', 'statefulset'):
                d[k] = v
            elif k == 'imagepullsecrets':
                d['imagePullSecrets'] = v
            elif k == 'imagepullpolicy':
                d['imagePullPolicy'] = v
            else:
                prop = k.split('.')
                if prop[0] == 'env':
                    d['envs'].append({prop[1].upper(): v})
                if prop[0] == 'volume':
                    d['volumes'].append({prop[1]: v})
                elif prop[0] == 'part':
                    d['parts'].append({prop[1]: v})
                elif prop[0] == 'port':
                    d['ports'].append({prop[1]: int(v)})
                elif prop[0] in ['requests', 'limits'] and prop[1] in ['memory', 'cpu']:
                    d['resources'][prop[0]][prop[1]] = v
            n += 1
        except ValueError as e:
            logger.warning("%s (line %d) %s: '%s'",
                           name, n, str(e), l.strip())
    return d


def get_manifest(name, properties):
    manifest = dict(
        apiVersion="v1",
        kind="Pod",
        metadata=dict(labels=dict(app=name)),
        spec=dict(containers=[]))
    parts = ','.join([p['name'] for p in properties['parts']])
    if parts:
        manifest['metadata']['labels']['parts'] = parts

    c = dict(name=name, env=[], volumes=[])
    for e in properties['envs']:
        k = list(e.keys())[0]
        c['env'].append(dict(name=k, value=e[k]))
    for v in properties['volumes']:
        k = list(v.keys())[0]
        c['volumes'].append(dict(name=k, mount=v[k]))
    for p in properties['parts']:
        k = list(p.keys())[0]
        c['env'].append(dict(name=k.upper(), value=p['addr']))
    if properties['ports']:
        c['ports'] = []
        for p in properties['ports']:
            k = list(p.keys())[0]
            c['ports'].append(dict(containerPort=p[k], name=k))
    if 'imagePullPolicy' in properties:
        c['imagePullPolicy'] = properties['imagePullPolicy']
    if 'resources' in properties:
        c['resources'] = properties['resources']
    c['image'] = properties['image']
    manifest['spec']['containers'].append(c)
    if 'imagePullSecrets' in properties:
        manifest['spec']['imagePullSecrets'] = [
            dict(name=properties['imagePullSecrets'])]
    return manifest


def create_instance(num_idling_containers, confdir, name, sessionID, logger):

    properties = get_properties(confdir, name, logger)
    if 'statefulset' in properties:
        if kube:
            return kube.scale_stateful_set(
                num_idling_containers,
                properties['statefulset'], sessionID)
        raise ValueError("stateful not supported in docker")

    for p in properties['parts']:
        k = list(p.keys())[0]
        p.update(create_instance(0, confdir, p[k], sessionID, logger))

    manifest = get_manifest(name, properties)

    if kube:
        return kube.create_pod(name, manifest)

    return dock.create_container(num_idling_containers,
                                 name, manifest, sessionID)


def get_containers_or_pods(label_key, label):
    qlabel = f'{label_key}={label}'
    if kube:
        return kube.get_pods(qlabel)
    return dock.get_containers(qlabel)


@bp.route('/app/<type>', methods=['GET'])
def containers_or_pods_new(type):
    current_app.logger.info("{'label': '%s'}", type)
    # manifest = flask.render_template(label, name=label)
    containers = get_containers_or_pods(current_app.config['LABEL_KEY'],
                                        type)
    return flask.jsonify([dict(hostname=c['name'],
                               ip=c['addr'],
                               name=c['sessionID'],
                               start=c['assigned'])
                          for c in containers])


@bp.route('/api/<label>', methods=['GET'])
def containers_or_pods(label):
    current_app.logger.info("{'label': '%s'}", label)
    # manifest = flask.render_template(label, name=label)
    containers = get_containers_or_pods(current_app.config['LABEL_KEY'],
                                        label)
    return flask.jsonify([dict(hostname=c['name'],
                               addr=c['addr'],
                               sessionID=c['sessionID'],
                               assigned=c['assigned'])
                          for c in containers])


@bp.route('/app/<name>/<sessionID>')
def create_new(name, sessionID):
    try:
        containers = get_containers_or_pods(current_app.config['LABEL_KEY'],
                                            name)
        instance = [x for x in containers if x['sessionID'] == sessionID]
        if len(instance) > 0:
            return flask.jsonify(dict(ip=instance[0]['addr']))

        instance = create_instance(
            current_app.config['MIN_NUM_IDLING_CONTAINERS'],
            current_app.config['CONFIG_DIR'], name, sessionID,
            current_app.logger)
        current_app.logger.info("{'hostname': '%s'}", instance['name'])
        return flask.jsonify(dict(ip=instance['addr']))

    except Exception as e:
        return flask.jsonify(dict(status='error', msg=str(e))), 404

@bp.route('/create/<name>')
def create(name):
    try:
        sessionID = request.args.get("sessionID")
        instance = create_instance(
            current_app.config['MIN_NUM_IDLING_CONTAINERS'],
            current_app.config['CONFIG_DIR'], name, sessionID,
            current_app.logger)
        current_app.logger.info("{'hostname': '%s'}", instance['name'])
        return flask.jsonify(dict(hostname=instance['name'],
                                  addr=instance['addr']))

    except Exception as e:
        return flask.jsonify(dict(status='error', msg=str(e))), 404


@bp.route('/app/<name>/<sessionID>', methods=['DELETE'])
def release_new(name, sessionID):
    containers = get_containers_or_pods(current_app.config['LABEL_KEY'],
                                        name)
    instance = [x for x in containers if x['sessionID'] == sessionID]
    if len(instance) > 0:
        return release(instance[0]['name'])

    return flask.jsonify(dict(status='warning', msg=f'{name} not found')), 404


@bp.route('/release/<name>')
def release(name):
    num_idling_containers = current_app.config['MIN_NUM_IDLING_CONTAINERS']
    clabels = {}
    if kube:
        clabels = kube.get_labels(name)
    else:
        clabels = dock.get_labels(name)
    current_app.logger.debug("{'name': '%s', 'labels': %s}", name, clabels)
    app = clabels.get(current_app.config['LABEL_KEY'], '')
    if app:
        containers = get_containers_or_pods(
            current_app.config['LABEL_KEY'], app)
        current_app.logger.info("{'num': %d, 'idling': %d}",
                                len(containers),
                                len([c for c in containers if not c.get('assigned', '')]))
    else:
        return flask.jsonify(dict(status='warning', msg=f'{name} not found')), 404

    if kube:
        resp = kube.delete_pod(num_idling_containers, name)
    else:
        resp = dock.delete_container(num_idling_containers, name)
    return flask.jsonify(resp)


def get_templates(confdir):
    return [p.name.split('.')[0]
            for p in pathlib.Path(confdir).glob('*.properties')]


@ bp.route('/templates')
def templates():
    return flask.jsonify(get_templates(current_app.config['CONFIG_DIR']))


def delete_all_containers(confdir, label_key):
    if dock:
        for template in get_templates(confdir):
            for cont in get_containers_or_pods(label_key, template):
                dock.delete_container(0, cont['name'])
