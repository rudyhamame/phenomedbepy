from flask import Flask, jsonify

from .routes.ecg import ecg_blueprint
from .routes.health import health_blueprint


def create_app():
    app = Flask(__name__)

    app.register_blueprint(health_blueprint)
    app.register_blueprint(ecg_blueprint, url_prefix="/api/ecg")

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({"message": "Route not found."}), 404

    @app.errorhandler(500)
    def server_error(error):
        return jsonify({"message": "Internal server error."}), 500

    return app
