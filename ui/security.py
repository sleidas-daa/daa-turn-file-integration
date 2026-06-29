"""Path and identifier validation for the web UI."""
from __future__ import annotations

import re
from pathlib import Path

QUEUE_ITEM_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class InvalidQueueItemIdError(ValueError):
    pass


class PathTraversalError(ValueError):
    pass


def parse_queue_item_id(item_id: str) -> str:
    """Reject malformed queue ids before they reach file operations."""
    if not QUEUE_ITEM_ID_RE.fullmatch(item_id):
        raise InvalidQueueItemIdError("Invalid queue item id")
    return item_id


def resolve_path_under_base(raw_path: str | Path, base_dir: Path) -> Path:
    """Resolve a path and ensure it stays inside base_dir."""
    base = base_dir.resolve()
    path = Path(raw_path).resolve()
    if not path.is_relative_to(base):
        raise PathTraversalError("Path is outside allowed directory")
    return path
