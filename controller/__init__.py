from controller.routes import bp
import platform
import logging
from config import Config, name as appname
from fastapi import FastAPI


logger = logging.getLogger(__name__)

# create and configure the app
app = FastAPI()


logger.info("{'name': '%s',  'version': '%s'}", appname, Config.VCS_INFO)


@app.get('/info')
def get_info():
    """return info"""
    info = dict(status='UP', hostname=platform.node(), rev=Config.VCS_INFO)
    return info


app.include_router(bp)
