"""
 lists, creates and deletes pods with kubernetes API
"""
import logging
import os
import yaml
from mako.template import Template
from config import Config
from kubernetes import client, watch

logger = logging.getLogger(__name__)

meta_label_prefix = 'config-controller.semafor.ch/meta-'
name_label = 'config-controller.semafor.ch/instance-name'
type_label = 'config-controller.semafor.ch/instance-type'
name_prefix = 'cc-app'


def load_config():
    from kubernetes import config
    if os.getenv('KUBERNETES_SERVICE_HOST'):
        config.load_incluster_config()
    else:
        config.load_kube_config()


class IntensJob(object):
    def __init__(self, app_type, name, create=True, template_variables=dict()):
        """construct a job instance

        :param app_type: Type of the app to make a job for.
        :param name: Name of the specific instance.
        :param create: Whether or not to create the
                        job object in kubernetes if it's missing.
        """
        self.app_type = app_type
        self.name = name
        self.template_variables = template_variables
        self.job_name = name_prefix + '-' + app_type + '-' + name
        self.v1 = client.CoreV1Api()
        self.batch_v1 = client.BatchV1Api()
        pods = self.v1.list_namespaced_pod(Config.NAMESPACE,
                                           label_selector='job-name='
                                           + self.job_name).items

        self.exists = not len(pods) == 0

        if not self.exists and create:
            self.create_job()

    def get_pod_ip(self):
        """get the ip address of the pod

        Wait until the pod us running and then return the ip address of it.
        This method will lock until the pod is started.

        :return bool
                Whether the ip was successfully retrieved

        :return str
                The ip address of the pod. Or if none is ready, a status message
        """
        w = watch.Watch()
        scheduling = True
        # Pending, Running

        for event in w.stream(func=self.v1.list_namespaced_pod,
                              namespace=Config.NAMESPACE,
                              label_selector='job-name=' + self.job_name,
                              timeout_seconds=10):
            statuses = event['object'].status.container_statuses
            if statuses is None:
                continue

            scheduling = False
            # check if every container status has ready
            ready = all(s.ready for s in statuses)
            if ready and event['object'].status.pod_ip is not None:
                w.stop()
                return True, event['object'].status.pod_ip

        if scheduling:
            return False, "node_not_ready"

        return False, "pulling_image"

    def get_meta_labels(self):
        """get custom set metadata

        Get all metadata labels that were custom set with the add_labels function

        :return dict
                The metadata
        """
        pod_def = self.v1.list_namespaced_pod(
            Config.NAMESPACE, label_selector='job-name=' + self.job_name,).items[0]
        pod_labels = dict([[k.removeprefix(meta_label_prefix), v]
                          for k, v in pod_def.metadata.labels.items()
                           if k.startswith(meta_label_prefix)])

        return pod_labels

    def create_job_object(self):
        """create the job object from in-cluster configmaps

        Creates the object to upload to the kubernetes cluster.
        Raises an exception of the configmap does not exist or is invalid.

        :return V1Job
                Job object based on the configmap template
        """
        # Get all configmaps that are marked as a config-controller app
        config_maps = self.v1.list_namespaced_config_map(Config.NAMESPACE,
                                                         label_selector=Config.CONFIG_MAP_SELECTOR).items

        file_name = self.app_type + '.yaml'
        yaml_data = None

        for map in config_maps:
            if file_name in map.data:
                yaml_data = map.data[file_name]
                break

        if yaml_data is None:
            raise Exception('No configs found for app ' + file_name)

        try:
            rendered_yaml = Template(yaml_data).render(
                alternatives=self.template_variables)
        except Exception as e:
            logger.error(e)
            raise e

        try:
            kube_info = yaml.safe_load(rendered_yaml)
        except Exception as e:
            logger.error(e)
            raise e

        kube_info['metadata']['labels'][name_label] = self.name
        kube_info['metadata']['labels'][type_label] = self.app_type

        job = client.V1Job(
            api_version='batch/v1',
            kind='Job',
            metadata=client.V1ObjectMeta(name=self.job_name),
            spec=client.V1JobSpec(template=kube_info)
        )
        return job

    def create_job(self):
        """create the kubernetes job

        Creates the job in kubernetes.
        Raises an exception if create_job_object also fails
        """
        try:
            self.batch_v1.create_namespaced_job(
                body=self.create_job_object(),
                namespace=Config.NAMESPACE)
            self.exists = True
        except Exception as e:
            raise e

    def add_labels(self, pod_labels):
        """add metadata to a job

            This add a bunch of metadata to the running pod of the job.
            They are namespaced to not interfere with any other potential labels.

            Note that there is no function to remove labels.

        :param pod_labels: A dict of labels you want to add as metadata

        """
        pod_def = self.v1.list_namespaced_pod(
            Config.NAMESPACE, label_selector='job-name=' + self.job_name,).items[0]
        for key, val in pod_labels.items():
            pod_def.metadata.labels[meta_label_prefix +
                                    key] = val

        self.v1.patch_namespaced_pod(
            pod_def.metadata.name, Config.NAMESPACE, pod_def)

    def delete_job(self):
        """delete the kubernetes job

        Deletes the job in kubernetes.
        """
        api_response = self.batch_v1.delete_namespaced_job(
            name=self.job_name,
            namespace=Config.NAMESPACE,
            body=client.V1DeleteOptions(
                propagation_policy='Foreground',
                grace_period_seconds=0))
        logger.info('Job deleted. status="%s"' % str(api_response.status))


class KubernetesApi(object):
    def __init__(self):
        self.v1 = client.CoreV1Api()
        self.batch_v1 = client.BatchV1Api()

    def get_jobs(self, type):
        """get running jobs of a type

        This methods brings a list of all running jobs of a specific app type.
        The data it gives about a job are the ip address, the name,
        and a timestamp of when it started.

        :param type: Type of the application you want jobs of.

        :return list(dict(ip=str, name=str, start=str))
                A list of all running jobs of the type.
        """

        podlist = []
        pods = self.v1.list_namespaced_pod(namespace=Config.NAMESPACE,
                                           label_selector=type_label+'='+type)
        for pod in pods.items:
            if pod.status.conditions is None:
                return podlist
            for condition in pod.status.conditions:
                if condition.type == 'Ready' and condition.status == 'True':
                    meta_labels = dict([[k.removeprefix(meta_label_prefix), v]
                                        for k, v in pod.metadata.labels.items()
                                       if k.startswith(meta_label_prefix)])
                    podlist.append(dict(
                        ip=pod.status.pod_ip,
                        name=pod.metadata.labels[name_label],
                        start=pod.status.start_time.timestamp()) | meta_labels)
                    break
        return podlist

    def list_templates(self):
        """list all available application template names

        This method goes through all configmaps with the selector
        and returns a list of the applications.

        :return list
                A list containing the names you can requrest applications with.
        """
        config_maps = self.v1.list_namespaced_config_map(Config.NAMESPACE,
                                                         label_selector=Config.CONFIG_MAP_SELECTOR).items

        templates = []
        for map in config_maps:
            for template in map.data.keys():
                templates.append(template.removesuffix('.yaml'))
        return templates

    def get_job(self, type, name, create=True, template_variables=dict()):
        """create a job of an app giving it a name

        Starts a kubernetes job using the template from the application type
        assigning it the given name.
        If there already is an instance of that name running, it will
        not create a new job.

        If there exists no template of the given type
        or it contains invalid syntax
        an exception is raised.

        :param type: What application you want a pod of.
        :param name: Name of the application instance.

        :return str
                ip address of the pod.
        """
        job = IntensJob(type, name, create, template_variables)
        return job

    def delete_job(self, type, name):
        """delete a job of an app with a given name

        Delete a kubernetes job of that type or name.

        :param type: Type of the application.
        :param name: Name of the application instance.

        :return bool
                Whether or not a job was deleted.
        """
        job = IntensJob(type, name, create=False)
        if job.exists:
            job.delete_job()
            return True

        return False
