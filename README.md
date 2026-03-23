# phenomedbepy

`phenomedbepy` is a standalone Python backend for PhenoMed.

It starts as the home for ECG digitization, but the structure is meant to grow into a broader Python service layer for PhenoMed features that are better handled outside the Node backend.

## Current modules

- `GET /health`
- `GET /api/ecg/health`
- `POST /api/ecg/analyze`

## Local run

```bash
pip install -r requirements.txt
python app.py
```

Default port: `8000`

## Suggested Render setup

- Create a new Python web service from this folder/repo
- Build command: `pip install -r requirements.txt`
- Start command: `python app.py`

Then point the Node backend env var `ECG_PYTHON_SERVICE_URL` at the deployed `phenomedbepy` URL.
