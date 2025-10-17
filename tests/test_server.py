import pytest

from controller import create_app


@pytest.fixture
def client():

    class KubeApi:
        def __init__(self):
            pass

        def get_job(self, type, name):
            assert type == 'type'
            assert name == 'name'
            return '0.0.0.0'

        def list_templates(self):
            return ['type']

        def get_jobs(self, type):
            assert type == 'type'
            return [dict(name=type, ip='0.0.0.0')]

    app = create_app({
        'TESTING': True,
        'KUBE': KubeApi(),
    })
    with app.test_client() as client:
        yield client


def test_not_found(client):
    rv = client.get('/')
    assert b'{"msg":"not found","status":"error"}\n' in rv.data


def test_list_containers(client):
    rv = client.get('/app/type')
    assert b'[{"ip":"0.0.0.0","name":"type"}]\n' == rv.data


def test_create_container(client):
    rv = client.get('/app')
    assert b'["type"]\n' in rv.data

    rv = client.get('/app/type/name')
    assert b'{"ip":"0.0.0.0"}\n' in rv.data
