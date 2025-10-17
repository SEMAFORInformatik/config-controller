"""
 lists, creates and deletes containers with docker API

https://docker-py.readthedocs.io

Note: Labels on images, containers, local daemons, volumes, and networks are
  static for the lifetime of the object. To change these labels you must
  recreate the object. (https://docs.docker.com/config/labels-custom-metadata)
"""
import docker
import logging
import uuid
import time
import os

logger = logging.getLogger(__name__)


def get_ipaddr(c):
    """return ip address of container"""
    for k in c.attrs['NetworkSettings']['Networks']:
        if 'IPAddress' in c.attrs['NetworkSettings']['Networks'][k]:
            return c.attrs['NetworkSettings']['Networks'][k]['IPAddress']
    return ''


class DockerApi(object):

    def __init__(self, basedir=''):
        self.docker_client = docker.DockerClient(
            base_url='unix://var/run/docker.sock')
        self.docker_network = None
        self.basedir = basedir if basedir else os.getcwd()
        schema_key = 'org.label-schema.name'
        schema_name = 'config-controller'
        for c in self.docker_client.containers.list(filters={
                "label": "{}={}".format(
                    schema_key, schema_name)}):
            networks = [k for k in c.attrs['NetworkSettings']['Networks']]
            logger.info("Networks %s", networks)
            if len(networks) > 0:
                self.docker_network = networks[0]
        if not self.docker_network:
            self.docker_network = 'bridge'
            logger.warn("WARNING: Use default network: %s",
                        self.docker_network)

    def get_containers(self, label):
        """returns containers by label"""
        key, value = label.split('=')
        return [dict(
            addr=get_ipaddr(c),
            name=c.attrs['Name'][1:],
            assigned=c.labels.get('assigned', ""),
            sessionID=c.labels.get('sessionID', "0"))
            for c in self.docker_client.containers.list(filters={
                "label": "{}={}".format(
                    key.strip(), value.strip())})]

    def get_labels(self, name):
        """returns container labels by name"""
        try:
            container = self.docker_client.containers.get(name)
            return container.labels
        except docker.errors.NotFound as e:
            pass
        return {}

    def find_unassigned_containers(self, labels):
        return [c for c in self.docker_client.containers.list(
            filters={
                "label": [f'{k}={labels[k]}' for k in labels.keys()]})
                if not c.labels.get('assigned', "")]

    def create_container(self, num_idling_containers, nameprefix,
                         manifest, sessionID):
        prefix = ''
        if self.docker_network != 'bridge':
            prefix = self.docker_network.split('_')[0]+'_'
        image_name = manifest['spec']['containers'][0]['image']
        c = manifest['spec']['containers'][0]
        env = ['{0}={1}'.format(e['name'], e['value']) for e in c['env']]
        volumes = ['{0}/{1}:{2}'.format(self.basedir, v['name'], v['mount'])
                   for v in c['volumes']]
        logger.info("Volumes %s", volumes)
        if sessionID != '0':
            assign_ts = str(int(time.time()))
        else:
            assign_ts = ''

        #uc = self.find_unassigned_containers(manifest['metadata']['labels'])
        # if len(uc)-1 < num_idling_containers:
        container_name = prefix+nameprefix+'-'+uuid.uuid4().hex[:8]
        self.docker_client.containers.run(
            image_name, name=container_name,
            labels={'app': nameprefix,
                    'sessionID': sessionID,
                    'assigned': assign_ts},
            detach=True, environment=env,
            volumes=volumes,
            network=self.docker_network,  # remove=True, ???
            restart_policy={"Name": "on-failure",
                            "MaximumRetryCount": 5})
        logger.info("Started container %s on network %s", container_name,
                    self.docker_network)
        c = self.docker_client.containers.list(
            filters={"name": container_name})[0]
        # if uc:
        #    c = uc[0]
        #    c.labels['sessionID'] = sessionID
        return dict(name=container_name, addr=get_ipaddr(c))

    def delete_container(self, num_idling_containers, name):
        try:
            logger.info("removing container %s", name)
            # self.docker_client.containers.get(name).stop()
            self.docker_client.containers.get(name).remove(force=True)
            #logger.info("delete %s ignored")
            return dict(status='OK', message='{} deleted'.format(name))
        except docker.errors.NotFound as e:
            logger.warning('delete container %s: %s', name, str(e))
            return dict(status='NotFound')
