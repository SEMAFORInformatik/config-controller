import platform
import logging
import os
import flask
import werkzeug
import config

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(message)s')

kube = None


def create_app(test_config=None):
    global kube

    # create and configure the app
    app = flask.Flask(__name__, instance_relative_config=True)
    app.config.from_object(config.Config())

    if test_config is None:
        try:
            import controller.kubernetes_api
            controller.kubernetes_api.load_config()
            kube = controller.kubernetes_api.KubernetesApi()
        except:
            kube = None
            app.logger.error("Kubernetes Client", exc_info=True)
            exit(1)

    else:
        # load the test config if passed in
        app.config.from_mapping(test_config)
        kube = test_config['KUBE']

    app.logger.info("{'name': '%s',  'version': '%s'}",
                    config.name, app.config['VCS_INFO'])

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
                    rev=app.config['VCS_INFO'])
        return flask.jsonify(info)

    from controller.routes import bp
    app.register_blueprint(bp)

    return app
