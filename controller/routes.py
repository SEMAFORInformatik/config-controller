import logging
import os
import time

from fastapi import APIRouter, HTTPException, Request, Response

if os.getenv('KUBERNETES_SERVICE_HOST'):
    import controller.kubernetes_api

    controller.kubernetes_api.load_config()
    api = controller.kubernetes_api.KubernetesApi()
else:
    import controller.docker_api

    controller.docker_api.load_config()
    api = controller.docker_api.DockerApi()

logger = logging.getLogger(__name__)
bp = APIRouter()


@bp.get('/app')
def templates():
    return api.list_templates()


@bp.get('/app/{type}')
def getAll(type: str):
    return api.get_jobs(type)


@bp.get('/api/{type}')
def getAll_(type: str):
    return api.get_jobs(type)


@bp.get('/app/{type}/{name}')
def get(type, name, req: Request, response: Response):
    try:
        job = api.get_job(type, name, template_variables=dict(req.query_params))
        success, instance = job.get_ip()
        if not success:
            response.status_code = 202
            return {'status': instance}

        meta_labels = job.get_meta_labels()
        logger.info('{"hostname": "%s"}', instance)
        return {'ip': instance} | meta_labels
    except Exception as e:
        logger.warning(e)
        response.status_code = 404
        return {'status': 'error', 'msg': str(e)}


@bp.patch('/app/{type}/{name}')
def patch(type, name, data: dict):
    try:
        job = api.get_job(type, name, create=False)
        if not job.exists:
            raise Exception('Job does ' + type + '/' + name + ' not exist')
        job.add_labels(data)
        return {'status': 'Success'}
    except Exception as e:
        logger.warning(e)
        raise HTTPException(status_code=404, detail={'status': 'error', 'msg': str(e)})


@bp.delete('/app/{type}/{name}')
def delete(type, name):
    resp = api.delete_job(type, name)
    if resp:
        return {'status': 'Success'}

    raise HTTPException(status_code=404, detail={'status': 'No job found'})


@bp.get('/create/{name}')
def create_old(name, sessionID: str, req: Request, response: Response):
    start_time = time.time()

    def get_app():
        try:
            job = api.get_job(type, name, template_variables=dict(req.query_params))
            success, instance = job.get_ip()
            if not success:
                return instance, 202

            logger.info('{"hostname": "%s"}', instance)
            return instance, 200
        except Exception as e:
            logger.warning(e)
            return str(e), 404

    while True:
        # if it takes too long, delete the pod it tried to provision and return
        if time.time() - start_time > 600:
            delete(name, sessionID)
            response.status_code = 408
            return {'status': 'Could not provision app'}

        reply = get_app()
        if reply[1] != 202:
            break

    ip = reply[0]
    return {'hostname': ip, 'addr': ip}


@bp.route('/release/{name}')
def release(name):
    for template in api.list_templates():
        for job in api.get_jobs(template):
            if job['name'] == name or job['sessionID'] == name:
                delete(template, job['name'])
                return {'status': 'Success'}

    raise HTTPException(status_code=404, detail={'status': 'Not found'})
