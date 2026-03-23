"""
lists, creates and deletes pods with docker API
"""

import socket

import datetime

import logging
import os
import glob
import docker
import configparser
from config import Config

logger = logging.getLogger(__name__)

TEMPLATE_FOLDER = '/etc/config-controller'
name_label = 'config-controller.semafor.ch/instance-name'
type_label = 'config-controller.semafor.ch/instance-type'

client: docker.DockerClient
docker_network: str
work_dir: str


def load_config():
    global client, docker_network, work_dir
    client = docker.DockerClient()
    cc_container = client.containers.get(socket.gethostname())
    work_dir = cc_container.labels['com.docker.compose.project.working_dir']
    networks = [k for k in cc_container.attrs['NetworkSettings']['Networks']]
    logger.info('Networks: %s', networks)
    if len(networks) > 0:
        docker_network = networks[0]
    if not docker_network:
        docker_network = 'bridge'
        logger.warning('WARNING: Use default network: %s', docker_network)


class IntensJob(object):
    def __init__(self, app_type, name, create=True, template_variables=dict()):
        properties_file = os.path.join(TEMPLATE_FOLDER, app_type + '.properties')
        config_parser = configparser.RawConfigParser(allow_unnamed_section=True)
        config_parser.read(properties_file)
        self.container_name = app_type + '-' + name

        try:
            self.container = client.containers.get(self.container_name)
            self.ip = self.container.attrs['NetworkSettings']['Networks'][
                docker_network
            ]['IPAddress']
            return
        except:
            if not create:
                return

        self.env = {}
        self.volumes = []

        for key, val in config_parser.items(configparser.UNNAMED_SECTION):
            if key == 'image':
                self.image = val
                continue
            if key.startswith('env.'):
                self.env[key.removeprefix('env.').upper()] = val
                continue
            if key.startswith('volume.'):
                self.volumes.append(
                    '{0}/{1}:{2}'.format(
                        Config.BASE_DIR if Config.BASE_DIR else work_dir,
                        key.removeprefix('volume.'),
                        val,
                    )
                )

                # self.volumes[key.removeprefix("volume.")] = val
                continue

        client.containers.run(
            self.image,
            name=self.container_name,
            environment=self.env,
            volumes=self.volumes,
            labels={name_label: name, type_label: app_type},
            network=docker_network,
            detach=True,
        )
        self.container = client.containers.get(self.container_name)
        self.ip = self.container.attrs['NetworkSettings']['Networks'][docker_network][
            'IPAddress'
        ]
        pass

    def get_ip(self):
        return True, self.ip
        # return False, "unfinished"
        pass

    def get_meta_labels(self):
        return {}
        pass

    def add_labels(self, pod_labels):
        pass

    @property
    def exists(self):
        return hasattr(self, 'container') and self.container is not None

    def _delete(self):
        if self.exists:
            self.container.remove(force=True)
            return True

        return False


class DockerApi(object):
    def __init__(self):
        pass

    def get_jobs(self, type):
        jobs = []
        for container in client.containers.list(
            filters={'label': '{0}={1}'.format(type_label, type)}
        ):
            logger.info(container.attrs)
            ip = container.attrs['NetworkSettings']['Networks'][docker_network][
                'IPAddress'
            ]
            name = container.labels[name_label]
            time: str = container.attrs['State']['StartedAt'].split('.')[0]
            start = datetime.datetime.strptime(time, '%Y-%m-%dT%H:%M:%S').timestamp()
            jobs.append(
                {
                    'ip': ip,
                    'name': name,
                    'sessionID': name,
                    'hostname': name,
                    'addr': ip,
                    'start': start,
                }
            )

        return jobs

    def list_templates(self):
        template_files = glob.glob(os.path.join(TEMPLATE_FOLDER, '*.properties'))

        return [os.path.basename(f.removesuffix('.properties')) for f in template_files]

    def get_job(self, type, name, create=True, template_variables=dict()):
        job = IntensJob(type, name, create, template_variables)
        return job

    def delete_job(self, type, name):
        return self.get_job(type, name, create=False)._delete()
