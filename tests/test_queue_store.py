"""Tests for the UI upload queue."""
import uuid
from pathlib import Path

import pytest

from ui.queue_store import QueueItem, UiQueue


def test_add_upload_and_list(tmp_path, monkeypatch) -> None:
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr("ui.queue_store.UI_UPLOAD_DIR", upload_dir)

    queue = UiQueue()
    item = queue.add_upload("schedule.xlsx", b"excel-bytes")
    assert item.file_name == "schedule.xlsx"
    assert Path(item.file_path).is_file()
    assert len(queue.list_items()) == 1


def test_add_upload_rejects_unsupported_extension(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("ui.queue_store.UI_UPLOAD_DIR", tmp_path / "uploads")
    queue = UiQueue()
    with pytest.raises(ValueError, match="Unsupported"):
        queue.add_upload("notes.pdf", b"data")


def test_remove_deletes_uploaded_file(tmp_path, monkeypatch) -> None:
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr("ui.queue_store.UI_UPLOAD_DIR", upload_dir)

    queue = UiQueue()
    item = queue.add_upload("schedule.xlsx", b"excel-bytes")
    file_path = Path(item.file_path)
    assert queue.remove(item.id) is True
    assert not file_path.exists()
    assert queue.get(item.id) is None


def test_clear_removes_all_items(tmp_path, monkeypatch) -> None:
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr("ui.queue_store.UI_UPLOAD_DIR", upload_dir)

    queue = UiQueue()
    queue.add_upload("a.xlsx", b"a")
    queue.add_upload("b.xlsx", b"b")
    removed = queue.clear()
    assert removed == 2
    assert queue.list_items() == []


def test_update_round_trip(tmp_path, monkeypatch) -> None:
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr("ui.queue_store.UI_UPLOAD_DIR", upload_dir)

    queue = UiQueue()
    item = queue.add_upload("schedule.xlsx", b"excel-bytes")
    item.status = "completed"
    queue.update(item)
    assert queue.get(item.id).status == "completed"
    assert item.to_dict()["status"] == "completed"
