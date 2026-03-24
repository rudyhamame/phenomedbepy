from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from .ecg_service import analyze_ecg_payload

_MAX_WORKERS = 1
_JOB_EXECUTOR = ThreadPoolExecutor(max_workers=_MAX_WORKERS)
_JOBS = {}
_JOBS_LOCK = Lock()


def _timestamp():
    return datetime.now(timezone.utc).isoformat()


def _clone_job(job):
    return deepcopy(job)


def _run_job(job_id, payload):
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        if job.get("cancelRequested"):
            job["status"] = "cancelled"
            job["progress"] = 1.0
            job["message"] = "ECG analysis cancelled."
            job["updatedAt"] = _timestamp()
            job["completedAt"] = _timestamp()
            return
        job["status"] = "running"
        job["progress"] = 0.1
        job["message"] = "ECG analysis is running."
        job["updatedAt"] = _timestamp()

    try:
        def _progress_callback(update):
            with _JOBS_LOCK:
                job = _JOBS.get(job_id)
                if not job:
                    return
                if job.get("cancelRequested"):
                    job["status"] = "cancelled"
                    job["progress"] = 1.0
                    job["message"] = "ECG analysis cancelled."
                    job["updatedAt"] = _timestamp()
                    job["completedAt"] = _timestamp()
                    raise RuntimeError("__ECG_JOB_CANCELLED__")
                job["status"] = str(update.get("status") or job["status"])
                job["progress"] = float(update.get("progress") or job["progress"])
                job["message"] = str(update.get("message") or job["message"])
                partial_result = update.get("partialResult")
                if partial_result is not None:
                    job["result"] = partial_result
                job["updatedAt"] = _timestamp()

        result = analyze_ecg_payload(payload, progress_callback=_progress_callback)
        with _JOBS_LOCK:
            job = _JOBS.get(job_id)
            if not job:
                return
            job["status"] = "completed"
            job["progress"] = 1.0
            job["message"] = "ECG analysis completed."
            job["result"] = result
            job["updatedAt"] = _timestamp()
            job["completedAt"] = _timestamp()
    except Exception as exc:
        with _JOBS_LOCK:
            job = _JOBS.get(job_id)
            if not job:
                return
            if job.get("cancelRequested") or str(exc) == "__ECG_JOB_CANCELLED__":
                job["status"] = "cancelled"
                job["progress"] = 1.0
                job["message"] = "ECG analysis cancelled."
                job["updatedAt"] = _timestamp()
                job["completedAt"] = _timestamp()
                return
            job["status"] = "failed"
            job["progress"] = 1.0
            job["message"] = str(exc)
            job["error"] = str(exc)
            job["updatedAt"] = _timestamp()
            job["completedAt"] = _timestamp()


def create_analysis_job(payload):
    job_id = uuid4().hex
    submitted_at = _timestamp()
    job = {
        "jobId": job_id,
        "status": "queued",
        "progress": 0.0,
        "message": "ECG analysis job queued.",
        "result": None,
        "error": None,
        "cancelRequested": False,
        "createdAt": submitted_at,
        "updatedAt": submitted_at,
        "completedAt": None,
    }

    with _JOBS_LOCK:
        _JOBS[job_id] = job

    _JOB_EXECUTOR.submit(_run_job, job_id, payload)
    return _clone_job(job)


def get_job(job_id):
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return None
        return _clone_job(job)


def cancel_job(job_id):
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return None
        if job["status"] in {"completed", "failed", "cancelled"}:
            return _clone_job(job)
        job["cancelRequested"] = True
        if job["status"] == "queued":
            job["status"] = "cancelled"
            job["progress"] = 1.0
            job["message"] = "ECG analysis cancelled."
            job["updatedAt"] = _timestamp()
            job["completedAt"] = _timestamp()
        else:
            job["message"] = "Cancelling ECG analysis..."
            job["updatedAt"] = _timestamp()
        return _clone_job(job)
