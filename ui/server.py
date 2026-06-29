"""FastAPI backend for the schedule converter UI."""
from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from converter.config import OUTPUT_DIR  # noqa: E402
from converter.dataclasses import JobRecord  # noqa: E402
from converter.preview import preview_file  # noqa: E402
from converter.processor import process_job  # noqa: E402
from ui.queue_store import QueueItem, UI_UPLOAD_DIR, UiQueue  # noqa: E402
from ui.security import (  # noqa: E402
    InvalidQueueItemIdError,
    PathTraversalError,
    parse_queue_item_id,
    resolve_path_under_base,
)

STATIC_DIR = Path(__file__).parent / "static"
queue = UiQueue()

app = FastAPI(title="AOS Schedule Converter", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class PreviewRequest(BaseModel):
    template: str = "auto"


class ConvertRequest(BaseModel):
    template: str = "auto"


def _template_override(value: str) -> Optional[str]:
    if not value or value == "auto":
        return None
    return value


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/api/queue")
def list_queue() -> dict:
    items = queue.list_items()
    return {"count": len(items), "items": [i.to_dict() for i in items]}


@app.post("/api/queue/upload")
async def upload_files(files: List[UploadFile] = File(...)) -> dict:
    added = []
    errors = []
    for upload in files:
        data = await upload.read()
        name = upload.filename or "upload"
        try:
            item = queue.add_upload(name, data)
            added.append(item.to_dict())
        except ValueError as exc:
            errors.append({"file": name, "error": str(exc)})
    return {"added": added, "errors": errors, "count": len(queue.list_items())}


def _require_queue_item_id(item_id: str) -> str:
    try:
        return parse_queue_item_id(item_id)
    except InvalidQueueItemIdError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _require_path_under_base(raw_path: str, base_dir: Path) -> Path:
    try:
        return resolve_path_under_base(raw_path, base_dir)
    except PathTraversalError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.delete("/api/queue/{item_id}")
def delete_item(item_id: str) -> dict:
    _require_queue_item_id(item_id)
    if not queue.remove(item_id):
        raise HTTPException(404, "Queue item not found")
    return {"count": len(queue.list_items())}


@app.delete("/api/queue")
def clear_queue() -> dict:
    removed = queue.clear()
    return {"removed": removed, "count": 0}


@app.post("/api/preview/{item_id}")
def preview_item(item_id: str, body: PreviewRequest) -> dict:
    _require_queue_item_id(item_id)
    item = queue.get(item_id)
    if not item:
        raise HTTPException(404, "Queue item not found")
    file_path = _require_path_under_base(item.file_path, UI_UPLOAD_DIR)
    result = preview_file(str(file_path), _template_override(body.template))
    return {"item_id": item_id, "file_name": item.file_name, **result}


@app.post("/api/convert")
def convert_all(body: ConvertRequest) -> dict:
    items = [i for i in queue.list_items() if i.status != "completed"]
    if not items:
        raise HTTPException(400, "No files in queue to convert")

    results = []
    override = _template_override(body.template)

    for item in items:
        file_path = _require_path_under_base(item.file_path, UI_UPLOAD_DIR)
        job = JobRecord(
            id=str(uuid.uuid4()),
            file_name=item.file_name,
            file_path=str(file_path),
            file_size=item.file_size,
            timestamp=datetime.now(UTC).isoformat(),
        )
        job = process_job(job, template_override=override)
        item.status = "completed" if job.processing_status == "completed" else "failed"
        item.detected_template = job.detected_template
        item.output_file_path = job.output_file_path or ""
        item.record_count = job.records_ok
        item.error = job.error_messages[0] if job.error_messages else ""
        queue.update(item)
        results.append({
            "id": item.id,
            "file_name": item.file_name,
            "status": item.status,
            "template": item.detected_template,
            "record_count": item.record_count,
            "output_file_path": item.output_file_path,
            "error": item.error,
            "report_path": job.report_path,
        })

    return {"converted": len(results), "results": results}


@app.get("/api/download/{item_id}")
def download_output(item_id: str) -> FileResponse:
    _require_queue_item_id(item_id)
    item = queue.get(item_id)
    if not item or not item.output_file_path:
        raise HTTPException(404, "Output file not available")
    path = _require_path_under_base(item.output_file_path, OUTPUT_DIR)
    if not path.is_file():
        raise HTTPException(404, "Output file not found on disk")
    return FileResponse(path, filename=path.name, media_type="text/csv")
