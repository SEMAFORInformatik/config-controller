"""
 lists, creates and deletes pods with kubernetes API
"""
import logging
import os
import uuid
import time
from kubernetes import client
from threading import Timer

logger = logging.getLogger(__name__)
namespace = os.environ.get("SET_NAMESPACE", 'default')


def load_config():
    from kubernetes import config
    if os.getenv('KUBERNETES_SERVICE_HOST'):
        config.load_incluster_config()
    else:
        config.load_kube_config()


class KubernetesApi(object):
    def __init__(self):
        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.scale_timers = {}
        # client.api.core_v1_api.CoreV1Api()

    def get_pods(self, label='app=api-gw'):
        """return pods with status Ready and containing label"""

        podlist = []
        pods = self.v1.list_namespaced_pod(namespace=namespace,
                                           label_selector=label)
        for pod in pods.items:
            if pod.status.conditions is None:
                return podlist
            for condition in pod.status.conditions:
                # wait for 'Ready' state instead of 'ContainersReady' for backwards compatibility with k8s 1.10
                if condition.type == 'Ready' and condition.status == 'True':
                    podlist.append(dict(
                        addr=pod.status.pod_ip,
                        name=pod.metadata.name + "." + label.split("=")[1],
                        sessionID=pod.metadata.labels.get('sessionID', ''),
                        assigned=pod.metadata.labels.get('assigned', '')))
                    break
        return podlist

    def get_labels(self, pod_name):
        """return labels of pod"""
        try:
            pod = self.v1.read_namespaced_pod(
                name=pod_name.split('.')[0], namespace=namespace)
        except client.exceptions.ApiException as e:
            if e.status == 404:
                logger.warning(
                    "{'name': '%s', 'msg': 'pod not found'}", pod_name)
                return {}  # not found
            raise (e)
        return pod.metadata.labels

    def create_pod(self, nameprefix, manifest):
        name = '{}-{}'.format(nameprefix, uuid.uuid4().hex[:8])
        ip = ''
        msg = ''
        try:
            manifest['metadata']['name'] = name

            resp = self.v1.create_namespaced_pod(body=manifest,
                                                 namespace=namespace)
            while True:
                resp = self.v1.read_namespaced_pod(name=name,
                                                   namespace=namespace)
                # logger.info(resp.status)
                if resp.status.phase != 'Pending':
                    logger.debug("Status %s", resp.status.phase)
                    break
                time.sleep(1)
            ip = resp.status.pod_ip
            logger.info("{'name': '%s', 'action': 'created'}", name)
            return dict(name=name, addr=ip)

        except Exception as e:
            logger.error(e, exc_info=True)
            raise Exception('create_pod: ' + e.body)

    def find_unassigned_pods(self, labels):
        return [p for p in self.get_pods(labels)
                if not p['assigned']]

    def down_scale_queue(self, num_idling_containers, stateful_set_name):
        if stateful_set_name in self.scale_timers:
            self.scale_timers[stateful_set_name].cancel()
        self.scale_timers[stateful_set_name] = Timer(25, self.down_scale_stateful_set, args=[num_idling_containers, stateful_set_name])
        self.scale_timers[stateful_set_name].start()

    def down_scale_stateful_set(self, num_idling_containers, stateful_set_name):
        s = self.apps_v1.read_namespaced_stateful_set(
            name=stateful_set_name, namespace=namespace)
        # search pods using label
        labels = [f'{k}={s.spec.template.metadata.labels[k]}'
                  for k in s.spec.template.metadata.labels][0]
        scale = self.apps_v1.read_namespaced_stateful_set_scale(
            name=stateful_set_name, namespace=namespace)
        replicas = scale.spec.replicas-1
        upods = sorted([(int(p['name'].split('.')[0].split('-')[-1]), p)
                        for p in self.find_unassigned_pods(labels)],
                       reverse=True)
        logger.info("{'unassigned': %s}", [p[0] for p in upods])
        for p in upods:  # get all unassigned pods
            if replicas-1 != p[0] or len(upods) <= num_idling_containers:
                break
            replicas -= 1
        if len(upods) > num_idling_containers:
            patch = {'spec': {'replicas': replicas}}
            try:
                resp = self.apps_v1.patch_namespaced_stateful_set_scale(
                    stateful_set_name, namespace, patch)
                logger.info("{'statefulset': '%s', 'action': 'scale', 'replicas': %d}",
                            stateful_set_name, replicas)
                # logger.debug("delete response: %s", resp)
            except Exception as e:
                logger.error(e, exc_info=True)
        else:
            logger.info("{'statefulset': '%s', 'action': 'ignored, 'replicas': %d}",
                        stateful_set_name, replicas)

    def scale_stateful_set(self, num_idling_containers, stateful_set_name, sessionID):
        msg = ''
        try:
            s = self.apps_v1.read_namespaced_stateful_set(
                name=stateful_set_name, namespace=namespace)
            # search pods using label
            labels = [f'{k}={s.spec.template.metadata.labels[k]}'
                      for k in s.spec.template.metadata.labels][0]
            pods = self.find_unassigned_pods(labels)
            if len(pods)-1 < num_idling_containers:
                # not enough unassigned pods found
                patch = {'spec': {'replicas': s.spec.replicas+1}}
                s = self.apps_v1.patch_namespaced_stateful_set_scale(
                    stateful_set_name, namespace, patch)
                logger.info("{'statefuleset': '%s', 'replicas': %d}",
                            stateful_set_name, s.spec.replicas)
                name = f"{stateful_set_name}-{s.spec.replicas-1}"
                if len(pods) < 1:
                    time.sleep(1)
                    while True:
                        try:
                            resp = self.v1.read_namespaced_pod(
                                name=name, namespace=namespace)
                            # logger.info(resp.status)
                            if resp.status.phase != 'Pending':
                                logger.debug("Status %s", resp.status.phase)
                                break
                        except client.exceptions.ApiException as e:
                            if e.status != 404:  # not found
                                raise e
                        logger.info("{'status': '%s', 'msg': 'Retrying ..'}",
                                    resp.status.phase)
                        time.sleep(1)
                    pods.append(resp)

            creation_ts = str(int(time.time()))
            p = self.v1.patch_namespaced_pod(
                pods[0]['name'].split('.')[0], namespace,
                {'metadata': {'labels': {
                    'assigned': creation_ts, 'sessionID': sessionID}}})
            logger.info("{'pod': '%s', 'addr': '%s',  'labels': %s}",
                        p.metadata.name,
                        p.status.pod_ip,
                        p.metadata.labels)
            return dict(name=pods[0]['name'],
                        addr=p.status.pod_ip)

        except Exception as e:
            logger.error(e, exc_info=True)
            raise Exception('scale_stateful_set: ' + str(e))

    def delete_pod(self, num_idling_containers, name):
        try:
            podname = name.split('.')[0]
            pod = self.v1.read_namespaced_pod(
                name=podname, namespace=namespace)
            try:
                if 'statefulset.kubernetes.io/pod-name' in pod.metadata.labels:
                    if 'assigned' in pod.metadata.labels:

                        resp = self.v1.delete_namespaced_pod(
                            name=podname, namespace=namespace)
                        logger.info(
                            "{'pod': '%s', 'msg': 'released'}", pod.metadata.name)
                    self.down_scale_queue(num_idling_containers,
                                                 pod.metadata.owner_references[0].name)
                    return dict(status='OK', message=f'{pod.metadata.name} released')

                if resp.metadata.labels.get('parts', ''):
                    return [self.delete_pod(p).to_dict()
                            for p in resp.metadata.labels.get('parts', '').split(',')]
            except AttributeError as e:
                logger.warning(e, exc_info=True)
                pass
            resp = self.v1.delete_namespaced_pod(
                name=podname, namespace=namespace)
            logger.debug("delete response: %s", resp)
            return resp.to_dict()

        except client.rest.ApiException as e:
            logger.error(e, exc_info=True)
            import json
            return json.loads(e.body)
