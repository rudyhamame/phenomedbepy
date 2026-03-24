from .digital_trace_analysis import build_analysis as build_digital_trace_analysis
from copy import deepcopy

LOCAL_METHOD = DIGITAL_TRACE_METHOD = "digital_trace_ingest"


def build_toolchain_status():
    return {
        "status": "healthy",
        "python": "ok",
        "missingModules": [],
        "missingFiles": [],
        "initError": None,
        "engine": DIGITAL_TRACE_METHOD,
    }


def _emit_progress(progress_callback, *, status, progress, message, partial_result=None):
    if not callable(progress_callback):
        return

    progress_callback(
        {
            "status": status,
            "progress": progress,
            "message": message,
            "partialResult": partial_result,
        }
    )


def _build_partial_result(
    *,
    source_type,
    method,
    acquisition_note,
    observed_text,
    preview_base64="",
    preview_mime_type="image/png",
    file_name="",
    pdf_page=None,
    pdf_page_count=None,
):
    return {
        "mode": "non-diagnostic",
        "sourceType": source_type,
        "method": method,
        "fileName": file_name,
        "pdfPage": pdf_page,
        "pdfPageCount": pdf_page_count,
        "analysis": {
            "sourceType": source_type,
            "summary": "",
            "acquisitionNote": acquisition_note,
            "qualityAssessment": {
                "readability": "processing",
                "gridVisible": None,
                "calibrationVisible": None,
                "limitations": [],
            },
            "measurements": [],
            "waveformPoints": [],
            "traceSamples": [],
            "leadTraces": {},
            "leadFindings": [],
            "rhythmFeatures": [],
            "trends": {
                "increases": [],
                "decreases": [],
                "stableOrNeutral": [],
            },
            "extractedText": [observed_text] if observed_text else [],
            "displayLead": "",
            "detectedLeads": [],
            "nonDiagnosticNotice": "ECG extraction is in progress. Partial preview only.",
            "previewImageBase64": preview_base64,
            "previewImageMimeType": preview_mime_type,
            "rotationApplied": "0",
        },
        "partial": True,
    }


def _merge_partial_analysis(base_partial_result, analysis_updates):
    merged = deepcopy(base_partial_result)
    merged_analysis = merged.get("analysis") or {}
    merged_analysis.update(analysis_updates or {})
    merged["analysis"] = merged_analysis
    merged["partial"] = True
    return merged


def analyze_ecg_payload(payload, progress_callback=None):
    acquisition_note = str(payload.get("acquisitionNote") or "").strip()
    observed_text = str(payload.get("observedText") or "").strip()
    mime_type = str(payload.get("mimeType") or "").strip()
    file_name = str(payload.get("fileName") or "").strip()
    base64_data = str(payload.get("fileData") or "").strip()
    pdf_page = max(1, int(payload.get("pdfPage") or 1))
    has_digital_traces = any(
        payload.get(key) not in (None, "", [], {})
        for key in ("digitalTraces", "leadTraces", "deviceTraces", "traces", "leadSignals", "leads")
    )

    if has_digital_traces:
        partial_result = _build_partial_result(
            source_type="device",
            method=DIGITAL_TRACE_METHOD,
            acquisition_note=acquisition_note,
            observed_text=observed_text,
            file_name=file_name,
        )
        _emit_progress(
            progress_callback,
            status="running",
            progress=0.22,
            message="Digital traces received. Preparing lead analysis.",
            partial_result=partial_result,
        )
        analysis = build_digital_trace_analysis(payload)
        _emit_progress(
            progress_callback,
            status="running",
            progress=0.74,
            message="Lead findings recovered from device traces. Finalizing ECG analysis.",
            partial_result=_merge_partial_analysis(partial_result, analysis),
        )
        return {
            "mode": "non-diagnostic",
            "sourceType": "device",
            "method": DIGITAL_TRACE_METHOD,
            "analysis": analysis,
            "fileName": file_name,
        }

    if base64_data or mime_type or pdf_page or observed_text:
        raise ValueError("Image, PDF, and text-only ECG submissions are no longer supported. Send device digital traces instead.")

    raise ValueError("Provide digital ECG traces from the device in digitalTraces, leadTraces, traces, or leads.")
