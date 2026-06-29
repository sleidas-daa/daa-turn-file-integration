"""Tests for the FastAPI UI endpoints."""
from __future__ import annotations

import io
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import ui.server as server
from ui.queue_store import QueueItem, UiQueue


@pytest.fixture()
def client(tmp_path, monkeypatch, ryanair_xlsx):
    upload_dir = tmp_path / "uploads"
    output_dir = tmp_path / "output"
    reports_dir = tmp_path / "reports"
    monkeypatch.setattr("ui.queue_store.UI_UPLOAD_DIR", upload_dir)
    monkeypatch.setattr("ui.server.UI_UPLOAD_DIR", upload_dir)
    monkeypatch.setattr("ui.server.UI_UPLOAD_DIR", upload_dir)
    monkeypatch.setattr("converter.processor.OUTPUT_DIR", output_dir)
    monkeypatch.setattr("converter.processor.REPORTS_DIR", reports_dir)
    monkeypatch.setattr("ui.server.OUTPUT_DIR", output_dir)
    server.queue = UiQueue()
    return TestClient(server.app), ryanair_xlsx, output_dir


class TestUiApi:
    def test_index(self, client):
        test_client, _, _ = client
        response = test_client.get("/")
        assert response.status_code == 200
        assert "AOS" in response.text or "html" in response.text.lower()

    def test_upload_list_delete_flow(self, client):
        test_client, ryanair_xlsx, _ = client
        with ryanair_xlsx.open("rb") as handle:
            response = test_client.post(
                "/api/queue/upload",
                files={"files": (ryanair_xlsx.name, handle, "application/octet-stream")},
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] == 1
        item_id = payload["added"][0]["id"]

        listed = test_client.get("/api/queue")
        assert listed.json()["count"] == 1

        deleted = test_client.delete(f"/api/queue/{item_id}")
        assert deleted.status_code == 200
        assert deleted.json()["count"] == 0

    def test_preview_and_convert(self, client):
        test_client, ryanair_xlsx, output_dir = client
        with ryanair_xlsx.open("rb") as handle:
            upload = test_client.post(
                "/api/queue/upload",
                files={"files": (ryanair_xlsx.name, handle, "application/octet-stream")},
            )
        item_id = upload.json()["added"][0]["id"]

        preview = test_client.post(
            f"/api/preview/{item_id}",
            json={"template": "ryanair"},
        )
        assert preview.status_code == 200
        assert preview.json()["ok"] is True

        converted = test_client.post("/api/convert", json={"template": "ryanair"})
        assert converted.status_code == 200
        result = converted.json()["results"][0]
        assert result["status"] == "completed"
        assert result["record_count"] > 0

        download = test_client.get(f"/api/download/{item_id}")
        assert download.status_code == 200
        assert download.headers["content-type"].startswith("text/csv")

    def test_convert_empty_queue(self, client):
        test_client, _, _ = client
        response = test_client.post("/api/convert", json={"template": "auto"})
        assert response.status_code == 400

    def test_clear_queue(self, client):
        test_client, ryanair_xlsx, _ = client
        with ryanair_xlsx.open("rb") as handle:
            test_client.post(
                "/api/queue/upload",
                files={"files": (ryanair_xlsx.name, handle, "application/octet-stream")},
            )
        cleared = test_client.delete("/api/queue")
        assert cleared.status_code == 200
        assert cleared.json()["count"] == 0

    def test_download_missing_output(self, client):
        test_client, _, _ = client
        item_id = str(uuid.uuid4())
        server.queue._items[item_id] = QueueItem(
            id=item_id,
            file_name="orphan.xlsx",
            file_path=str(Path("queue/ui_uploads/orphan.xlsx")),
            file_size=1,
            added_at="2026-01-01T00:00:00+00:00",
            output_file_path="",
        )
        response = test_client.get(f"/api/download/{item_id}")
        assert response.status_code == 404
