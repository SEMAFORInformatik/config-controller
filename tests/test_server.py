import os

import pytest

from controller import create_app

@pytest.fixture
def property_file():
    propfile = 'name.properties'
    with open(propfile, 'w') as fp:
        fp.write('env.env=value\n')
        fp.write('image=image_name\n')
    yield
    os.unlink(propfile)

@pytest.fixture
def client():

    class KubeApi:
        def __init__(self):
            pass
        def create_pod(self, nameprefix, manifest):
            assert nameprefix=='name'
            return dict(name=nameprefix, addr='0.0.0.0')
        def get_pods(self, label):
            assert label=='app=label'
            return [dict(name=label, addr='0.0.0.0')]
    
    app = create_app({
        'TESTING': True,
        'LABEL_KEY': 'app',
        'CONFIG_DIR': '.',
        'KUBE': KubeApi(),
        'DOCK': 0
    })
    with app.test_client() as client:
        yield client


def test_not_found(client):
    rv = client.get('/')
    assert b'{"msg":"not found","status":"error"}\n' in rv.data

def test_list_containers(client):
    rv = client.get('/api/label')
    assert b'[{"addr":"0.0.0.0","hostname":"app=label"}]\n' == rv.data

def test_create_container(client, property_file):
    rv = client.get('/templates')
    assert b'["name"]\n' in rv.data
    
    rv = client.get('/create/name')
    assert b'{"addr":"0.0.0.0","hostname":"name"}\n' in rv.data
