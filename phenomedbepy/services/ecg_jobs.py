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
        job["status"] = "running"
        job["progress"] = 0.1
        job["message"] = "ECG analysis is running."
        job["updatedAt"] = _timestamp()

    try:
        result = analyze_ecg_payload(payload)
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
