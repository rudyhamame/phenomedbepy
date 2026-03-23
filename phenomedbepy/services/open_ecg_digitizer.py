import base64
import io
import os
import sys
import threading
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from scipy.signal import find_peaks

LEAD_NAMES = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
OPEN_ECG_METHOD = "open_ecg_digitizer"
_WRAPPER_LOCK = threading.Lock()
_INFERENCE_WRAPPER = None
_INIT_ERROR = None


def _required_vendor_files(vendor_repo):
    return [
        vendor_repo / "src" / "config" / "inference_wrapper.yml",
        vendor_repo / "weights" / "unet_weights_07072025.pt",
        vendor_repo / "weights" / "lead_name_unet_weights_07072025.pt",
    ]


def _has_required_vendor_files(vendor_repo):
    return all(path.exists() for path in _required_vendor_files(vendor_repo))


def _vendor_repo_path():
    env_override = os.environ.get("OPEN_ECG_DIGITIZER_DIR")
    candidates = []

    if env_override:
        candidates.append(Path(env_override).expanduser().resolve())

    current_file = Path(__file__).resolve()
    for ancestor in current_file.parents:
        candidates.append(ancestor / "vendor" / "Open-ECG-Digitizer")

    unique_candidates = []
    seen = set()
    for candidate in candidates:
        candidate_str = str(candidate)
        if candidate_str in seen:
            continue
        seen.add(candidate_str)
        unique_candidates.append(candidate)

    for candidate in unique_candidates:
        if _has_required_vendor_files(candidate):
            return candidate

    for candidate in unique_candidates:
        if candidate.exists():
            return candidate

    return unique_candidates[0]


def _ensure_matplotlib_cache_dir():
    cache_dir = Path(__file__).resolve().parents[3] / ".cache" / "matplotlib"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))


def _ensure_vendor_on_path():
    _ensure_matplotlib_cache_dir()
    vendor_repo = _vendor_repo_path()
    vendor_str = str(vendor_repo)
    if vendor_str not in sys.path:
        sys.path.insert(0, vendor_str)
    return vendor_repo


def _patch_config_paths(cfg, vendor_repo):
    model_cfg = cfg.MODEL.KWARGS.config
    model_cfg.SEGMENTATION_MODEL.weight_path = str(vendor_repo / "weights" / "unet_weights_07072025.pt")
    model_cfg.LAYOUT_IDENTIFIER.config_path = str(vendor_repo / "src" / "config" / "lead_layouts_reduced.yml")
    model_cfg.LAYOUT_IDENTIFIER.unet_config_path = str(vendor_repo / "src" / "config" / "lead_name_unet.yml")
    model_cfg.LAYOUT_IDENTIFIER.unet_weight_path = str(
        vendor_repo / "weights" / "lead_name_unet_weights_07072025.pt"
    )
    cfg.MODEL.KWARGS.device = "cpu"
    cfg.MODEL.KWARGS.enable_timing = False
    cfg.MODEL.KWARGS.apply_dewarping = False
    model_cfg.LAYOUT_IDENTIFIER.KWARGS.device = "cpu"
    return cfg


def get_inference_wrapper():
    global _INFERENCE_WRAPPER, _INIT_ERROR

    if _INFERENCE_WRAPPER is not None:
        return _INFERENCE_WRAPPER
    if _INIT_ERROR is not None:
        raise RuntimeError(_INIT_ERROR)

    with _WRAPPER_LOCK:
        if _INFERENCE_WRAPPER is not None:
            return _INFERENCE_WRAPPER
        if _INIT_ERROR is not None:
            raise RuntimeError(_INIT_ERROR)

        try:
            vendor_repo = _ensure_vendor_on_path()
            from src.config.default import get_cfg
            from src.model.inference_wrapper import InferenceWrapper

            cfg = get_cfg(str(vendor_repo / "src" / "config" / "inference_wrapper.yml"))
            cfg = _patch_config_paths(cfg, vendor_repo)
            _INFERENCE_WRAPPER = InferenceWrapper(**cfg.MODEL.KWARGS)
            return _INFERENCE_WRAPPER
        except Exception as exc:
            _INIT_ERROR = str(exc)
            raise RuntimeError(_INIT_ERROR) from exc


def build_toolchain_status():
    missing = []
    try:
        import cv2  # noqa: F401
    except Exception:
        missing.append("cv2")
    try:
        import numpy  # noqa: F401
    except Exception:
        missing.append("numpy")
    try:
        import PIL  # noqa: F401
    except Exception:
        missing.append("PIL")
    try:
        import scipy  # noqa: F401
    except Exception:
        missing.append("scipy")
    try:
        import torch  # noqa: F401
    except Exception:
        missing.append("torch")
    try:
        import torchvision  # noqa: F401
    except Exception:
        missing.append("torchvision")
    try:
        import yacs  # noqa: F401
    except Exception:
        missing.append("yacs")
    try:
        import yaml  # noqa: F401
    except Exception:
        missing.append("yaml")
    try:
        import skimage  # noqa: F401
    except Exception:
        missing.append("scikit-image")
    try:
        import torch_tps  # noqa: F401
    except Exception:
        missing.append("torch-tps")

    vendor_repo = _vendor_repo_path()
    required_files = _required_vendor_files(vendor_repo)
    missing_files = [str(path.name) for path in required_files if not path.exists()]

    init_error = None
    if not missing and not missing_files:
        try:
            get_inference_wrapper()
        except Exception as exc:
            init_error = str(exc)

    status = "healthy"
    if missing or missing_files or init_error:
        status = "degraded"

    return {
        "status": status,
        "python": "ok",
        "missingModules": missing,
        "missingFiles": missing_files,
        "initError": init_error,
        "engine": OPEN_ECG_METHOD,
    }


def _decode_image_to_tensor(base64_data):
    image_bytes = base64.b64decode(base64_data, validate=False)
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    image_np = np.asarray(image, dtype=np.float32) / 255.0
    return torch.from_numpy(np.transpose(image_np, (2, 0, 1))).unsqueeze(0)


def _encode_tensor_image(image_tensor):
    image = image_tensor.detach().cpu()
    if image.dim() == 4:
        image = image[0]
    image = image.permute(1, 2, 0).numpy()
    image = np.clip(image * 255.0, 0, 255).astype(np.uint8)
    output = io.BytesIO()
    Image.fromarray(image).save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


def _downsample_trace(trace, max_points=1400):
    if trace.size == 0:
        return []
    if trace.size <= max_points:
        return [round(float(value), 4) for value in trace]
    indices = np.linspace(0, trace.size - 1, max_points).astype(np.int32)
    return [round(float(trace[index]), 4) for index in indices]


def _normalize_trace(trace):
    finite = trace[np.isfinite(trace)]
    if finite.size == 0:
        return np.array([], dtype=np.float32)
    minimum = float(np.min(finite))
    maximum = float(np.max(finite))
    spread = maximum - minimum
    if spread < 1e-6:
        return np.full(trace.shape, 0.5, dtype=np.float32)
    return ((trace - minimum) / spread).astype(np.float32)


def _summarize_segments(trace, count=8):
    segments = []
    segment_size = max(1, len(trace) // count)
    for idx in range(count):
        start = idx * segment_size
        end = len(trace) if idx == count - 1 else (idx + 1) * segment_size
        chunk = trace[start:end]
        if chunk.size == 0:
            continue
        slope = float(chunk[-1] - chunk[0])
        x_start = round((start / max(len(trace) - 1, 1)) * 100, 1)
        x_end = round(((end - 1) / max(len(trace) - 1, 1)) * 100, 1)
        if slope > 0.035:
            trend = "increase"
        elif slope < -0.035:
            trend = "decrease"
        else:
            trend = "stable"
        segments.append({"trend": trend, "start": x_start, "end": x_end, "delta": round(slope, 3)})
    return segments


def _detect_key_points(trace, max_points=8):
    if trace.size < 3:
        return []
    prominence = max(0.03, float(np.std(trace) * 0.6))
    peaks, _ = find_peaks(trace, prominence=prominence, distance=max(20, len(trace) // 15))
    troughs, _ = find_peaks(-trace, prominence=prominence, distance=max(20, len(trace) // 15))
    entries = [("peak", idx, float(trace[idx])) for idx in peaks]
    entries.extend(("trough", idx, float(trace[idx])) for idx in troughs)
    entries.sort(key=lambda item: abs(item[2] - float(np.median(trace))), reverse=True)
    entries = entries[:max_points]
    entries.sort(key=lambda item: item[1])
    return entries


def _pick_display_lead(canonical_lines):
    preferred_order = ["II", "V5", "V2", "I", "V1"]
    scores = {}
    for lead_name, lead_index in zip(LEAD_NAMES, range(len(LEAD_NAMES))):
        line = canonical_lines[lead_index]
        valid = np.isfinite(line)
        if not np.any(valid):
            continue
        finite = line[valid]
        amplitude = float(np.nanmax(finite) - np.nanmin(finite))
        coverage = float(np.mean(valid))
        scores[lead_name] = amplitude * 0.7 + coverage * 0.3

    if not scores:
        return None, np.array([], dtype=np.float32)

    for preferred in preferred_order:
        if preferred in scores:
            best_name = preferred
            break
    else:
        best_name = max(scores, key=scores.get)

    best_index = LEAD_NAMES.index(best_name)
    return best_name, canonical_lines[best_index]


def _build_lead_traces(canonical_lines):
    lead_traces = {}
    for lead_index, lead_name in enumerate(LEAD_NAMES[: canonical_lines.shape[0]]):
        line = canonical_lines[lead_index]
        valid = np.isfinite(line)
        if not np.any(valid):
            continue
        normalized = _normalize_trace(line.astype(np.float32))
        if normalized.size == 0:
            continue
        lead_traces[lead_name] = _downsample_trace(normalized)
    return lead_traces


def _build_measurements(layout_name, layout_cost, lines, pixel_spacing):
    measurements = [
        {
            "label": "Detected lead rows",
            "value": int(lines.shape[0]),
            "unit": "rows",
            "lead": "",
            "qualifier": "segmented signal rows",
            "evidence": "Returned by the Open-ECG-Digitizer signal extractor.",
        },
        {
            "label": "Samples per lead",
            "value": int(lines.shape[1]),
            "unit": "samples",
            "lead": "",
            "qualifier": "canonical time series width",
            "evidence": "Interpolated by the lead identifier output.",
        },
        {
            "label": "Layout matching cost",
            "value": round(float(layout_cost), 4),
            "unit": "",
            "lead": "",
            "qualifier": layout_name or "unknown layout",
            "evidence": "Lower values indicate a stronger layout match.",
        },
        {
            "label": "Average pixels per mm",
            "value": round(float(pixel_spacing.get("average_pixel_per_mm", 0.0)), 3),
            "unit": "px/mm",
            "lead": "",
            "qualifier": "grid-derived scaling",
            "evidence": "Estimated from the segmented ECG grid.",
        },
    ]
    return measurements


def build_analysis(payload):
    base64_data = str(payload.get("base64Data") or "").strip()
    if not base64_data:
        raise ValueError("No ECG image data was provided to the Open ECG digitizer.")

    acquisition_note = str(payload.get("acquisitionNote") or "").strip()
    observed_text = str(payload.get("observedText") or "").strip()

    wrapper = get_inference_wrapper()
    image_tensor = _decode_image_to_tensor(base64_data)
    with torch.no_grad():
        result = wrapper(image_tensor, layout_should_include_substring=None)

    signal = result.get("signal") or {}
    canonical_tensor = signal.get("canonical_lines")
    if canonical_tensor is None:
        raise ValueError("Open ECG Digitizer did not return canonical lead waveforms.")

    canonical_lines = canonical_tensor.detach().cpu().numpy()
    if canonical_lines.ndim != 2 or canonical_lines.shape[1] == 0:
        raise ValueError("Open ECG Digitizer returned an invalid waveform tensor.")

    display_lead, display_trace = _pick_display_lead(canonical_lines)
    if display_lead is None:
        raise ValueError("Open ECG Digitizer could not recover a usable lead trace from the image.")

    normalized_trace = _normalize_trace(display_trace.astype(np.float32))
    key_points = _detect_key_points(normalized_trace)
    segments = _summarize_segments(normalized_trace)

    increases = []
    decreases = []
    stable = []
    for segment in segments:
        label = f"{segment['start']}%-{segment['end']}% of the displayed lead"
        if segment["trend"] == "increase":
            increases.append(f"{label}: upward shift ({segment['delta']:+.3f} normalized units)")
        elif segment["trend"] == "decrease":
            decreases.append(f"{label}: downward shift ({segment['delta']:+.3f} normalized units)")
        else:
            stable.append(f"{label}: relatively stable ({segment['delta']:+.3f} normalized units)")

    waveform_points = []
    for index, (kind, position, amplitude) in enumerate(key_points):
        waveform_points.append(
            {
                "structure": f"{display_lead} {kind} {index + 1}",
                "observedState": f"{kind} at {round((position / max(len(normalized_trace) - 1, 1)) * 100, 1)}% of horizontal span",
                "leads": [display_lead],
                "evidence": f"Normalized amplitude {amplitude:.3f}",
            }
        )

    valid_mask = np.isfinite(canonical_lines)
    lead_traces = _build_lead_traces(canonical_lines)
    valid_leads = [
        LEAD_NAMES[index]
        for index in range(min(canonical_lines.shape[0], len(LEAD_NAMES)))
        if np.mean(valid_mask[index]) > 0.2 and LEAD_NAMES[index] in lead_traces
    ]
    layout_name = str(result.get("layout_name") or "unknown")
    layout_cost = float(signal.get("layout_matching_cost") or 0.0)
    pixel_spacing = result.get("pixel_spacing_mm") or {}
    aligned = result.get("aligned") or {}
    aligned_image = aligned.get("image")

    finite_display = display_trace[np.isfinite(display_trace)]
    amplitude_uv = float(np.nanmax(finite_display) - np.nanmin(finite_display)) if finite_display.size else 0.0
    readability = "good" if len(valid_leads) >= 8 else ("fair" if len(valid_leads) >= 4 else "limited")

    limitations = []
    if len(valid_leads) < 12:
        limitations.append(f"Only {len(valid_leads)} lead traces were recovered with usable coverage.")
    if layout_cost > 0.25:
        limitations.append("Layout matching cost is elevated, so lead placement should be inspected carefully.")
    if observed_text:
        limitations.append("Typed ECG notes were preserved alongside the reconstructed waveform.")

    summary = (
        f"Open-ECG-Digitizer recovered {len(valid_leads)} usable leads using the '{layout_name}' layout. "
        f"Lead {display_lead} is displayed for close waveform study with an estimated amplitude span of "
        f"{amplitude_uv:.1f} microvolts."
    )

    lead_findings = [
        {
            "lead": display_lead,
            "phenomenon": "displayed lead chosen for graph study",
            "direction": "selected",
            "magnitude": f"{len(normalized_trace)} samples",
            "evidence": f"Chosen from recovered leads: {', '.join(valid_leads[:12]) or 'none'}.",
        }
    ]

    rhythm_features = [
        {
            "feature": "Recovered leads",
            "observedState": f"{len(valid_leads)} usable leads",
            "evidence": ", ".join(valid_leads) if valid_leads else "No leads recovered.",
        },
        {
            "feature": "Displayed lead",
            "observedState": display_lead,
            "evidence": "Selected for visualization based on lead preference and usable waveform coverage.",
        },
    ]

    return {
        "sourceType": "image",
        "summary": summary,
        "acquisitionNote": acquisition_note or "Image-based Open-ECG-Digitizer reconstruction.",
        "qualityAssessment": {
            "readability": readability,
            "gridVisible": True,
            "calibrationVisible": None,
            "limitations": limitations,
        },
        "measurements": _build_measurements(layout_name, layout_cost, canonical_lines, pixel_spacing),
        "waveformPoints": waveform_points,
        "traceSamples": _downsample_trace(normalized_trace),
        "leadTraces": lead_traces,
        "leadFindings": lead_findings,
        "rhythmFeatures": rhythm_features,
        "trends": {
            "increases": increases,
            "decreases": decreases,
            "stableOrNeutral": stable,
        },
        "extractedText": [observed_text] if observed_text else [],
        "nonDiagnosticNotice": (
            "Observable ECG findings only. The waveform is reconstructed from an image with Open-ECG-Digitizer "
            "and should be visually checked against the source."
        ),
        "previewImageBase64": _encode_tensor_image(aligned_image if aligned_image is not None else image_tensor),
        "previewImageMimeType": "image/png",
        "rotationApplied": "perspective-corrected",
        "displayLead": display_lead,
        "detectedLeads": valid_leads,
        "layoutName": layout_name,
        "layoutMatchingCost": round(layout_cost, 4),
    }
