# DAA Turn File Converter — Web UI Integration

## Current state

A FastAPI web server already exists in `ui/server.py` and is launched via `ui_app.py`. It serves a minimal HTML/CSS/JS front-end from `ui/static/` that provides:

- File upload (drag-and-drop or file picker)
- Queue management (list jobs, view status, re-process)
- Per-job details (records parsed, validation warnings, download output CSV)
- API key authentication via `ui/security.py`

This section describes how the existing backend is structured, what the REST API exposes, and how a full-featured front-end (React, Vue, or plain JS) would integrate cleanly.

---

## System boundary diagram

```
                          Browser / Front-end
                         ┌────────────────────────────┐
                         │   React / Vue / Next.js app │
                         │   (or existing static HTML) │
                         └──────────┬─────────────────┘
                                    │  HTTP (REST JSON)
                                    │  Multipart form-data (file upload)
                                    ▼
                         ┌──────────────────────┐
                         │  FastAPI server       │  ui/server.py
                         │  (ui_app.py)          │  ui/security.py
                         └──────────┬───────────┘
                                    │
                         ┌──────────▼───────────┐
                         │  converter package    │  src/converter/
                         │  (processor.py)       │
                         └──────────┬───────────┘
                                    │
               ┌────────────────────┼────────────────────┐
               ▼                    ▼                    ▼
         queue/ folder        output/ folder       reports/ folder
```

The FastAPI server is the single integration point between the browser and the converter engine. The converter package itself has no knowledge of HTTP — it is pure Python and can equally be driven by the CLI (`run.py`), the queue watcher (`staging_runner.py`), or the API.

---

## REST API overview

| Method | Endpoint                    | Description                                    |
|--------|-----------------------------|------------------------------------------------|
| POST   | `/upload`                   | Upload a schedule file; returns a job ID       |
| GET    | `/jobs`                     | List all jobs with current status              |
| GET    | `/jobs/{job_id}`            | Full detail for one job                        |
| POST   | `/jobs/{job_id}/process`    | Trigger (re-)processing of a queued job        |
| GET    | `/jobs/{job_id}/download`   | Download the output CSV                        |
| GET    | `/jobs/{job_id}/report`     | Download the validation report (if it exists)  |
| DELETE | `/jobs/{job_id}`            | Remove a job from the queue                    |
| GET    | `/health`                   | Liveness check; returns `{"status": "ok"}`     |

All endpoints except `/health` require an `X-API-Key` header (configured in `ui/security.py`).

Responses are JSON. Job objects mirror the `JobRecord` dataclass fields:

```json
{
  "id": "abc123",
  "file_name": "W23FINAL.txt",
  "detected_template": "aer_lingus",
  "confidence": 0.95,
  "processing_status": "completed",
  "validation_status": "passed",
  "records_parsed": 14714,
  "records_ok": 14714,
  "records_rejected": 0,
  "warnings": ["[row 12] overnight: Overnight value 3 is greater than 1 ..."],
  "output_file_path": "output/OUTPUT_W23FINAL.csv",
  "report_path": "reports/REPORT_W23FINAL.txt",
  "processing_duration_s": 4.2
}
```

---

## Integrating a React / Vue front-end

The existing `ui/static/` front-end is vanilla JS. Replacing or supplementing it with a React or Vue SPA requires only three changes:

### 1. Build output goes into `ui/static/`

Configure the front-end bundler (Vite, Create React App, Webpack) so that `npm run build` outputs to `ui/static/`. FastAPI mounts this directory as a static file server, so no changes to the Python side are needed.

```js
// vite.config.js
export default {
  build: { outDir: '../ui/static' }
}
```

### 2. Proxy API calls during development

During local development the front-end dev server (Vite: port 5173) and the FastAPI server (port 8000) are on different ports. Configure a proxy so API calls are forwarded:

```js
// vite.config.js
export default {
  server: {
    proxy: {
      '/upload': 'http://localhost:8000',
      '/jobs':   'http://localhost:8000',
      '/health': 'http://localhost:8000',
    }
  }
}
```

### 3. Pass the API key from the front-end

The API key is set in `ui/security.py`. In the SPA, store it as an environment variable (injected at build time via Vite's `import.meta.env`) and attach it as a header to every request:

```js
const API_KEY = import.meta.env.VITE_API_KEY;

async function fetchJobs() {
  const resp = await fetch('/jobs', {
    headers: { 'X-API-Key': API_KEY }
  });
  return resp.json();
}
```

In a production deployment the key should come from a secrets manager or be injected by the hosting environment, not committed to source.

---

## Recommended UI page structure

```
┌─────────────────────────────────────────────┐
│  Upload                                     │  Drop-zone + file picker
│  ─────────────────────────────────────────  │  POST /upload
│  Drag schedule file here or click to browse │  Shows detected template + confidence
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  Job Queue                                  │  GET /jobs (poll every 5s)
│  ─────────────────────────────────────────  │
│  ● W23FINAL.txt     completed  14,714 rows  │
│  ● S26 DUB TR.xlsx  processing ...          │  Spinner while processing
│  ● old_file.xlsx    failed     [details]    │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│  Job Detail (drawer or modal)               │  GET /jobs/{id}
│  ─────────────────────────────────────────  │
│  Template:   aer_lingus  (95% confidence)   │
│  Records:    14,714 OK / 0 rejected         │
│  Warnings:   2  [show list]                 │
│  Duration:   4.2 s                          │
│  [Download CSV]  [Download Report]          │  GET /jobs/{id}/download
└─────────────────────────────────────────────┘
```

---

## Processing flow from the UI's perspective

```
User uploads file
       │
       ▼
POST /upload
  └─ FastAPI saves file to queue/
  └─ Creates a JobRecord with status = "queued"
  └─ Returns { job_id: "abc123" }
       │
       ▼
Front-end polls GET /jobs/abc123
  └─ Shows status = "queued" / "processing"
       │
       ▼  (either automatically or via POST /jobs/abc123/process)
processor.process_job() runs in a background thread
  └─ detection → parse → validate → export → report
  └─ Updates JobRecord in the queue store
       │
       ▼
Status becomes "completed" or "failed"
Front-end stops polling and shows result
```

For production, replace the background thread with a proper task queue (Celery, RQ, or Python `concurrent.futures`) so the FastAPI event loop is not blocked during long file processing.

---

## Deployment considerations

### Minimal (single machine)

Run `ui_app.py` behind an Nginx reverse proxy. Nginx terminates TLS and proxies `/` and `/api` to `localhost:8000`. The `queue/`, `output/`, and `reports/` directories are on a shared NFS mount or local disk.

### Containerised

```
docker-compose up
  ├── converter   (python ui_app.py — FastAPI + converter engine)
  └── nginx       (reverse proxy + TLS termination)
```

Volumes:
- `./queue` → `/app/queue`
- `./output` → `/app/output`
- `./reports` → `/app/reports`

Environment variables control `API_KEY`, `ALLOWED_ORIGINS`, and path overrides.

### Scalability note

Because the converter writes to the local filesystem (`output/`, `reports/`), horizontal scaling (multiple FastAPI replicas) requires shared storage (NFS, S3-backed mount, or Azure File Share). The queue state JSON file (`queue/.queue_state.json`) would also need to move to a shared database or Redis. These are straightforward changes to `queue_manager.py` and `ui/queue_store.py`.

---

## Security notes

- The existing `ui/security.py` uses a single static API key. For a production deployment, replace this with per-user tokens or OAuth2.
- File uploads are not sanitised for malicious content beyond extension checking. In production, add virus scanning (e.g. ClamAV) before files are placed in the queue.
- The output CSVs contain no personal data (only flight identifiers and dates), so GDPR exposure is minimal.
- Do not expose the `/jobs/{id}/download` endpoint publicly without authentication — output files are generated from internal schedule data.
