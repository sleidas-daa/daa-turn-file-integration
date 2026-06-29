"""Security checks for UI path handling."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from ui.queue_store import QueueItem, UiQueue
from ui.security import (
    InvalidQueueItemIdError,
    PathTraversalError,
    parse_queue_item_id,
    resolve_path_under_base,
)
from ui.server import OUTPUT_DIR, _require_path_under_base, _require_queue_item_id


def test_parse_queue_item_id_accepts_uuid() -> None:
    item_id = str(uuid.uuid4())
    assert parse_queue_item_id(item_id) == item_id


@pytest.mark.parametrize(
    "item_id",
    [
        "../../../etc/passwd",
        "not-a-uuid",
        "123",
        f"{uuid.uuid4()}/../secret",
    ],
)
def test_parse_queue_item_id_rejects_unsafe_values(item_id: str) -> None:
    with pytest.raises(InvalidQueueItemIdError):
        parse_queue_item_id(item_id)


def test_resolve_path_under_base_allows_child(tmp_path: Path) -> None:
    child = tmp_path / "nested" / "file.txt"
    child.parent.mkdir(parents=True)
    child.write_text("ok", encoding="utf-8")
    assert resolve_path_under_base(child, tmp_path) == child.resolve()


def test_resolve_path_under_base_blocks_traversal(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    with pytest.raises(PathTraversalError):
        resolve_path_under_base(outside, tmp_path)


def test_queue_remove_skips_paths_outside_upload_dir(tmp_path: Path, monkeypatch) -> None:
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr("ui.queue_store.UI_UPLOAD_DIR", upload_dir)

    outside = tmp_path / "victim.txt"
    outside.write_text("keep me", encoding="utf-8")

    queue = UiQueue()
    item_id = str(uuid.uuid4())
    queue._items[item_id] = QueueItem(
        id=item_id,
        file_name="victim.txt",
        file_path=str(outside),
        file_size=6,
        added_at="2026-01-01T00:00:00+00:00",
    )

    assert queue.remove(item_id) is True
    assert outside.read_text(encoding="utf-8") == "keep me"


def test_require_queue_item_id_rejects_invalid() -> None:
    with pytest.raises(Exception) as exc_info:
        _require_queue_item_id("not-a-valid-id")
    assert exc_info.value.status_code == 400


def test_require_path_under_base_rejects_output_traversal(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    monkeypatch.setattr("ui.server.OUTPUT_DIR", output_dir)

    outside = tmp_path / "secret.csv"
    outside.write_text("data", encoding="utf-8")

    with pytest.raises(Exception) as exc_info:
        _require_path_under_base(str(outside), OUTPUT_DIR)
    assert exc_info.value.status_code == 403
