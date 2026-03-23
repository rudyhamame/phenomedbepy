from flask import Blueprint, jsonify, request

from ..services.ecg_service import LOCAL_METHOD, analyze_ecg_payload, build_toolchain_status

ecg_blueprint = Blueprint("ecg", __name__)


@ecg_blueprint.get("/")
def ecg_index():
    return jsonify(
        {
            "name": "PhenoMed ECG Python API",
            "status": "ready",
            "mode": "non-diagnostic",
            "method": LOCAL_METHOD,
        }
    )


@ecg_blueprint.get("/health")
def ecg_health():
    toolchain = build_toolchain_status()
    return (
        jsonify(
            {
                "status": toolchain["status"],
                "mode": "local-only",
                "method": LOCAL_METHOD,
                "toolchain": toolchain,
            }
        ),
        200 if toolchain["status"] == "healthy" else 503,
    )


@ecg_blueprint.post("/analyze")
def analyze():
    payload = request.get_json(silent=True) or {}

    try:
        result = analyze_ecg_payload(payload)
        return jsonify(result)
    except ValueError as exc:
        message = str(exc)
        status_code = 400
        if "not implemented" in message.lower():
            status_code = 501
        elif "unavailable" in message.lower() or "missing python modules" in message.lower():
            status_code = 503
        return jsonify({"message": message}), status_code
    except Exception as exc:
        return jsonify({"message": str(exc)}), 500
