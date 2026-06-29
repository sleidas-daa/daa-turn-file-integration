"""In-memory upload queue for the web UI."""
from __future__ import annotations

import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import List, Optional

from converter.config import ROOT_DIR, SUPPORTED_EXTENSIONS
from ui.security import PathTraversalError, resolve_path_under_base

UI_UPLOAD_DIR = ROOT_DIR / "queue" / "ui_uploads"


@dataclass
class QueueItem:
    id: str
    file_name: str
    file_path: str
    file_size: int
    added_at: str
    status: str = "queued"  # queued | completed | failed
    detected_template: str = ""
    output_file_path: str = ""
    error: str = ""
    record_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class UiQueue:
    def __init__(self) -> None:
        UI_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self._items: dict[str, QueueItem] = {}

    def list_items(self) -> List[QueueItem]:
        return sorted(self._items.values(), key=lambda i: i.added_at)

    def get(self, item_id: str) -> Optional[QueueItem]:
        return self._items.get(item_id)

    def add_upload(self, filename: str, data: bytes) -> QueueItem:
        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {ext or '(none)'}")

        item_id = str(uuid.uuid4())
        safe_name = Path(filename).name
        dest = UI_UPLOAD_DIR / f"{item_id}_{safe_name}"
        dest.write_bytes(data)

        item = QueueItem(
            id=item_id,
            file_name=safe_name,
            file_path=str(dest),
            file_size=len(data),
            added_at=datetime.now(UTC).isoformat(),
        )
        self._items[item_id] = item
        return item

    def remove(self, item_id: str) -> bool:
        item = self._items.pop(item_id, None)
        if not item:
            return False
        try:
            path = resolve_path_under_base(item.file_path, UI_UPLOAD_DIR)
        except PathTraversalError:
            return True
        if path.is_file():
            path.unlink()
        return True

    def clear(self) -> int:
        count = len(self._items)
        for item_id in list(self._items):
            self.remove(item_id)
        return count

    def update(self, item: QueueItem) -> None:
        self._items[item.id] = item
