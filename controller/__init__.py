import platform
import logging
import os
import flask
import werkzeug
# from flask_session import Session
import pathlib
import config
import atexit

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(message)s')

kube = None
dock = None


def create_app(test_config=None):
    global kube
    global dock

    # create and configure the app
    app = flask.Flask(__name__, instance_relative_config=True)
    app.config.from_object(config.Config())

    if test_config is None:
        # load the instance config, if it exists, when not testing
        app.config.from_pyfile('config.py', silent=True)
        if pathlib.Path('/var/run/docker.sock').is_socket() and os.environ.get('DOCKER'):
            import controller.docker_api
            dock = controller.docker_api.DockerApi(app.config['BASE_DIR'])
            from controller.routes import get_templates, create_instance
            if app.config['MIN_NUM_IDLING_CONTAINERS'] > 0:
                for template in get_templates(app.config['CONFIG_DIR']):
                    create_instance(app.config['MIN_NUM_IDLING_CONTAINERS'],
                                    app.config['CONFIG_DIR'], template, "0",
                                    app.logger)
        else:
            try:
                import controller.kubernetes_api
                controller.kubernetes_api.load_config()
                kube = controller.kubernetes_api.KubernetesApi()
            except:
                kube = None
                app.logger.warning("Kubernetes Client", exc_info=True)

    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)
        kube = test_config['KUBE']
        dock = test_config['DOCK']

    app.logger.info("{'name': '%s',  'version': '%s'}",
                    config.name, app.config['VCS_INFO'])
    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    @app.errorhandler(werkzeug.exceptions.BadRequest)
    def badrequest(error):
        return (flask.jsonify(dict(status='error', msg='bad request')),
                werkzeug.exceptions.BadRequest)

    @app.errorhandler(404)
    def not_found_error(error):
        return flask.jsonify(dict(status='error', msg='not found')), 404

    @app.errorhandler(500)
    def internal_error(error):
        return flask.jsonify(dict(status='error', msg='internal error')), 500

    @app.route('/info', methods=['GET'])
    def get_info():
        """return info"""
        info = dict(status='UP', hostname=platform.node(),
                    config_dir=app.config['CONFIG_DIR'],
                    rev=app.config['VCS_INFO'])
        return flask.jsonify(info)

    from controller.routes import bp
    app.register_blueprint(bp)

    return app

# Session(app)

# register exit function


def delete_containers():
    conf = config.Config()
    from .routes import delete_all_containers
    delete_all_containers(conf.CONFIG_DIR, conf.LABEL_KEY)


atexit.register(delete_containers)
