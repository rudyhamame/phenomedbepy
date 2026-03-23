from flask import Blueprint, jsonify, request

from ..services.ecg_jobs import create_analysis_job, get_job
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


@ecg_blueprint.post("/jobs")
def create_job():
    payload = request.get_json(silent=True) or {}

    try:
        job = create_analysis_job(payload)
        return (
            jsonify(
                {
                    "jobId": job["jobId"],
                    "status": job["status"],
                    "progress": job["progress"],
                    "message": job["message"],
                    "method": LOCAL_METHOD,
                }
            ),
            202,
        )
    except Exception as exc:
        return jsonify({"message": str(exc)}), 500


@ecg_blueprint.get("/jobs/<job_id>")
def get_job_status(job_id):
    job = get_job(job_id)
    if job is None:
        return jsonify({"message": "ECG analysis job not found."}), 404

    payload = {
        "jobId": job["jobId"],
        "status": job["status"],
        "progress": job["progress"],
        "message": job["message"],
        "createdAt": job["createdAt"],
        "updatedAt": job["updatedAt"],
        "completedAt": job["completedAt"],
        "method": LOCAL_METHOD,
    }
    if job["status"] == "completed" and job["result"] is not None:
        payload.update(job["result"])
    if job["status"] == "failed" and job["error"]:
        payload["error"] = job["error"]

    return jsonify(payload)
