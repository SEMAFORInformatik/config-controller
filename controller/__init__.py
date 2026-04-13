import logging
import platform

from fastapi import FastAPI

from config import Config
from config import name as appname
from controller.routes import bp

logger = logging.getLogger(__name__)

# create and configure the app
app = FastAPI()


logger.info("{'name': '%s',  'version': '%s'}", appname, Config.VCS_INFO)


@app.get('/info')
def get_info():
    """return info"""
    info = {'status': 'UP', 'hostname': platform.node(), 'rev': Config.VCS_INFO}
    return info


app.include_router(bp)
