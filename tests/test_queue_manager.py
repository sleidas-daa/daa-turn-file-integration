"""Tests for the file-based queue manager."""
from __future__ import annotations

import shutil

import pytest

from converter.queue_manager import QueueManager


@pytest.fixture()
def queue_env(tmp_path, monkeypatch):
    qdir = tmp_path / "queue"
    qdir.mkdir()
    state = qdir / ".queue_state.json"
    monkeypatch.setattr("converter.queue_manager.QUEUE_DIR", qdir)
    monkeypatch.setattr("converter.queue_manager.QUEUE_STATE_FILE", state)
    return qdir, state


class TestQueueManager:
    def test_scan_and_persist(self, queue_env, ryanair_xlsx):
        qdir, _ = queue_env
        shutil.copy(ryanair_xlsx, qdir / ryanair_xlsx.name)

        q1 = QueueManager()
        new_jobs = q1.scan_for_new_files()
        assert len(new_jobs) == 1
        assert len(q1.pending_jobs()) == 1

        q2 = QueueManager()
        assert len(q2.all_jobs()) == 1

    def test_update_persists_status(self, queue_env, ryanair_xlsx):
        qdir, _ = queue_env
        shutil.copy(ryanair_xlsx, qdir / "job.xlsx")

        q = QueueManager()
        q.scan_for_new_files()
        job = q.pending_jobs()[0]
        job.processing_status = "completed"
        q.update(job)

        reloaded = QueueManager()
        assert reloaded.get_job(job.id).processing_status == "completed"

    def test_ignores_unsupported_extensions(self, queue_env):
        qdir, _ = queue_env
        (qdir / "readme.md").write_text("skip", encoding="utf-8")

        q = QueueManager()
        assert q.scan_for_new_files() == []

    def test_load_invalid_state_starts_empty(self, queue_env):
        _, state = queue_env
        state.write_text("{not-json", encoding="utf-8")
        q = QueueManager()
        assert q.all_jobs() == []
