import os
import pathlib

name = os.environ.get('FLASK_APP') or 'config-controller'


def vcs_info():
    g = pathlib.Path(__file__).parent / 'vcs.info'
    if g.exists():
        return g.read_text().strip()
    import subprocess
    try:
        p = subprocess.run(['git', 'describe'], capture_output=True)
        if p.returncode == 0:
            return p.stdout.decode().strip()
    except:
        pass
    return name.strip()


class Config(object):
    VCS_INFO = vcs_info()
    NAMESPACE = os.environ.get('JOB_NAMESPACE', 'default')
    CONFIG_MAP_SELECTOR = os.environ.get(
        'CONFIGMAP_SELECTOR', 'config-controller.semafor.ch/template')
