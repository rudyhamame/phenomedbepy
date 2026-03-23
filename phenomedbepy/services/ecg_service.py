from .open_ecg_digitizer import OPEN_ECG_METHOD, build_analysis, build_toolchain_status
from .pdf_to_image import render_pdf_page

LOCAL_METHOD = OPEN_ECG_METHOD


def analyze_ecg_payload(payload):
    toolchain = build_toolchain_status()
    if toolchain["status"] != "healthy":
        raise ValueError(
            f"Local ECG toolchain is unavailable. Missing Python modules: {', '.join(toolchain['missingModules'])}."
        )

    acquisition_note = str(payload.get("acquisitionNote") or "").strip()
    observed_text = str(payload.get("observedText") or "").strip()
    mime_type = str(payload.get("mimeType") or "").strip()
    file_name = str(payload.get("fileName") or "").strip()
    base64_data = str(payload.get("fileData") or "").strip()
    pdf_page = max(1, int(payload.get("pdfPage") or 1))

    if not base64_data and not observed_text:
        raise ValueError("Provide an ECG file or observedText for analysis.")

    source_type = "pdf" if mime_type == "application/pdf" else ("image" if base64_data else "text")

    if source_type == "text":
        raise ValueError(
            "Local ECG digitization currently needs an ECG image upload. Text-only local analysis is not implemented."
        )

    if source_type == "pdf":
        rasterized = render_pdf_page(
            {
                "base64Data": base64_data,
                "pdfPage": pdf_page,
            }
        )
        analysis = build_analysis(
            {
            "base64Data": rasterized["base64Data"],
            "acquisitionNote": acquisition_note
                or f"PDF ECG page {rasterized['selectedPage']} rasterized before Open-ECG-Digitizer reconstruction.",
            "observedText": observed_text,
        }
    )
        return {
            "mode": "non-diagnostic",
            "sourceType": "pdf",
            "method": f"{LOCAL_METHOD}_via_pdf_rasterization",
            "analysis": analysis,
            "pdfPage": rasterized["selectedPage"],
            "pdfPageCount": rasterized["pageCount"],
            "fileName": file_name,
        }

    analysis = build_analysis(
        {
            "base64Data": base64_data,
            "acquisitionNote": acquisition_note,
            "observedText": observed_text,
        }
    )
    return {
        "mode": "non-diagnostic",
        "sourceType": "image",
        "method": LOCAL_METHOD,
        "analysis": analysis,
        "fileName": file_name,
    }
