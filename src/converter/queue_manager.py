"""File-based job queue for schedule processing."""
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, List, Optional

from .config import QUEUE_DIR, QUEUE_STATE_FILE, SUPPORTED_EXTENSIONS
from .dataclasses import JobRecord


class QueueManager:
    def __init__(self):
        QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        self._jobs: Dict[str, JobRecord] = {}
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def scan_for_new_files(self) -> List[JobRecord]:
        """Check the queue folder for files not yet tracked and add them."""
        new_jobs: List[JobRecord] = []
        tracked_paths = {j.file_path for j in self._jobs.values()}

        for p in sorted(QUEUE_DIR.iterdir()):
            if p.name.startswith("."):
                continue
            if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if str(p) in tracked_paths:
                continue
            job = self._make_job(p)
            self._jobs[job.id] = job
            new_jobs.append(job)

        if new_jobs:
            self._save()
        return new_jobs

    def pending_jobs(self) -> List[JobRecord]:
        return [j for j in self._jobs.values() if j.processing_status == "queued"]

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        return self._jobs.get(job_id)

    def update(self, job: JobRecord) -> None:
        self._jobs[job.id] = job
        self._save()

    def all_jobs(self) -> List[JobRecord]:
        return list(self._jobs.values())

    # ------------------------------------------------------------------
    def _make_job(self, path: Path) -> JobRecord:
        return JobRecord(
            id=str(uuid.uuid4()),
            file_name=path.name,
            file_path=str(path),
            file_size=path.stat().st_size,
            timestamp=datetime.now(UTC).isoformat(),
        )

    def _save(self) -> None:
        QUEUE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(QUEUE_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {jid: job.to_dict() for jid, job in self._jobs.items()},
                f,
                indent=2,
            )

    def _load(self) -> None:
        if not QUEUE_STATE_FILE.exists():
            return
        try:
            with open(QUEUE_STATE_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self._jobs = {jid: JobRecord.from_dict(d) for jid, d in raw.items()}
        except Exception:
            self._jobs = {}
