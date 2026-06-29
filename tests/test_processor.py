"""Tests for the full conversion pipeline."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from converter.dataclasses import JobRecord
from converter.processor import process_job


def _make_job(path: Path) -> JobRecord:
    return JobRecord(
        id=str(uuid.uuid4()),
        file_name=path.name,
        file_path=str(path),
        file_size=path.stat().st_size,
        timestamp=datetime.now(UTC).isoformat(),
    )


@pytest.fixture()
def pipeline_dirs(tmp_path, monkeypatch):
    out_dir = tmp_path / "output"
    reports_dir = tmp_path / "reports"
    monkeypatch.setattr("converter.processor.OUTPUT_DIR", out_dir)
    monkeypatch.setattr("converter.processor.REPORTS_DIR", reports_dir)
    return out_dir, reports_dir


class TestProcessJob:
    def test_ryanair_pipeline(self, ryanair_xlsx, pipeline_dirs):
        out_dir, _ = pipeline_dirs
        job = _make_job(ryanair_xlsx)
        job = process_job(job, template_override="ryanair")
        assert job.processing_status == "completed"
        assert job.records_ok > 0
        assert Path(job.output_file_path).is_file()
        assert job.output_file_path.startswith(str(out_dir))

    def test_emerald_pipeline(self, emerald_xlsx, pipeline_dirs):
        job = _make_job(emerald_xlsx)
        job = process_job(job, template_override="emerald")
        assert job.processing_status == "completed"
        assert job.records_ok > 0

    def test_aer_lingus_pipeline(self, aer_lingus_txt, pipeline_dirs):
        job = _make_job(aer_lingus_txt)
        job = process_job(job, template_override="aer_lingus")
        assert job.processing_status == "completed"
        assert job.records_ok > 0

    def test_include_header(self, ryanair_xlsx, pipeline_dirs):
        job = _make_job(ryanair_xlsx)
        job = process_job(job, template_override="ryanair", include_header=True)
        content = Path(job.output_file_path).read_text(encoding="utf-8")
        assert content.startswith("arrival_flight,")

    def test_unknown_template_fails(self, tmp_path, pipeline_dirs, monkeypatch):
        bad = tmp_path / "notes.txt"
        bad.write_text("hello", encoding="utf-8")
        monkeypatch.setattr(
            "converter.processor.detect_template",
            lambda _: ("unknown", 0.0),
        )
        job = _make_job(bad)
        job = process_job(job)
        assert job.processing_status == "failed"
        assert job.error_messages
