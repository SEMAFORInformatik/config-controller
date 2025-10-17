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
    LABEL_KEY = os.environ.get('LABEL_KEY') or 'app'
    MIN_NUM_IDLING_CONTAINERS = int(
        os.environ.get('MIN_NUM_IDLING_CONTAINERS') or 1)
    BASE_DIR = os.environ.get('BASE_DIR')
    CONFIG_DIR = os.environ.get('CONFIG_DIR') or '/etc/config-controller'
    VCS_INFO = vcs_info()
