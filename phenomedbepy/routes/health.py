from flask import Blueprint, jsonify

from ..services.ecg_service import build_toolchain_status

health_blueprint = Blueprint("health", __name__)


@health_blueprint.get("/health")
def health():
    toolchain = build_toolchain_status()
    return (
        jsonify(
            {
                "status": "healthy",
                "service": "phenomedbepy",
                "modules": {
                    "ecg": toolchain,
                },
            }
        ),
        200,
    )
