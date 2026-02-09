import json
import flask
import logging
from controller import kube


logger = logging.getLogger(__name__)
bp = flask.Blueprint('routes', __name__)


@bp.route('/app')
def templates():
    return flask.jsonify(kube.list_templates())


@bp.route('/app/<type>')
def getAll(type):
    return flask.jsonify(kube.get_jobs(type))

@bp.route('/api/<type>')
def getAll_(type):
    return flask.jsonify(kube.get_jobs(type))


@bp.route('/app/<type>/<name>')
def get(type, name):
    try:
        job = kube.get_job(
            type, name, template_variables=flask.request.args.to_dict(True))
        success, instance = job.get_pod_ip()
        if not success:
            return flask.jsonify(status=instance), 202

        meta_labels = job.get_meta_labels()
        logger.info('{"hostname": "%s"}', instance)
        return flask.jsonify(dict(ip=instance) | meta_labels)
    except Exception as e:
        logger.warn(e)
        return flask.jsonify(dict(status='error', msg=str(e))), 404


@bp.route('/app/<type>/<name>', methods=['PATCH'])
def patch(type, name):
    try:
        job = kube.get_job(type, name, create=False)
        if not job.exists:
            raise Exception('Job does ' + type + '/' + name + ' not exist')
        data = flask.request.get_json()
        job.add_labels(data)
        return flask.jsonify(dict(status='Success')), 200
    except Exception as e:
        logger.warn(e)
        return flask.jsonify(dict(status='error', msg=str(e))), 404


@bp.route('/app/<type>/<name>', methods=['DELETE'])
def delete(type, name):
    resp = kube.delete_job(type, name)
    if resp:
        return flask.jsonify(dict(status='Success')), 200

    return flask.jsonify(dict(status='No job found')), 404


@bp.route('/create/<name>')
def create_old(name):
    sessionID = flask.request.args.get("sessionID")
    def get_app():
        try:
            job = kube.get_job(
                name, sessionID, template_variables=flask.request.args.to_dict(True))
            success, instance = job.get_pod_ip()
            if not success:
                return instance, 202

            meta_labels = job.get_meta_labels()
            logger.info('{"hostname": "%s"}', instance)
            return instance, 200
        except Exception as e:
            logger.warn(e)
            return str(e), 404

    while True:
        reply = get_app()
        if reply[1] != 202:
            break

    ip = reply[0]
    return flask.jsonify(dict(hostname=ip,
                              addr=ip))


@bp.route('/release/<name>')
def release(name):

    for template in kube.list_templates():
        for job in kube.get_jobs(template):
            if job['name'] == name or job['sessionID'] == name:
                delete(template, job['name'])
                return flask.jsonify(dict(status='Success')), 200

    return flask.jsonify(dict(status='Not found')), 404
