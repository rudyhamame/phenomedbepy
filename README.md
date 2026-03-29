# phenomedbepy

`phenomedbepy` is a standalone Python backend for PhenoMed.

It starts as the home for ECG digitization, but the structure is meant to grow into a broader Python service layer for PhenoMed features that are better handled outside the Node backend.

## Current modules

- `GET /health`
- `GET /api/ecg/health`
- `POST /api/ecg/analyze`
- `POST /api/ecg/jobs`

`POST /api/ecg/analyze` and `POST /api/ecg/jobs` are now digital-trace only. Send device ECG traces using `digitalTraces`, `leadTraces`, `traces`, or `leads` in the JSON body.

## PTB-XL import

You can convert a PTB-XL digital ECG record into the same JSON shape with:

```bash
python scripts/ptbxl_to_digital_traces.py --dataset-dir /path/to/ptb-xl --ecg-id 1 --resolution hr --output ptbxl-1.json
```

Or by direct WFDB record path:

```bash
python scripts/ptbxl_to_digital_traces.py --record-path /path/to/ptb-xl/records500/00000/00001_hr
```

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
