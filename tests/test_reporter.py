"""Tests for the reporter module."""
import pytest
from pathlib import Path
from converter.dataclasses import JobRecord, ValidationError
from converter.reporter import generate_report, write_report, should_write_report


def _make_job(**kwargs) -> JobRecord:
    defaults = dict(
        id="test-job-1",
        file_name="test.xlsx",
        file_path="/tmp/test.xlsx",
        file_size=1024,
        detected_template="ryanair",
        confidence=0.95,
        processing_status="completed",
        validation_status="passed",
        records_parsed=100,
        records_ok=98,
        records_rejected=2,
        processing_duration_s=1.23,
    )
    defaults.update(kwargs)
    return JobRecord(**defaults)


class TestGenerateReport:
    def test_basic_structure(self):
        job = _make_job()
        report = generate_report(job, [])
        assert report["original_file_name"] == "test.xlsx"
        assert report["detected_template"] == "ryanair"
        assert report["records_parsed"] == 100
        assert report["records_successful"] == 98
        assert report["records_rejected"] == 2

    def test_validation_errors_included(self):
        job = _make_job()
        errs = [
            ValidationError(1, "arrival_flight", "Missing flight", "error"),
            ValidationError(2, "overnight", "Must be 0 or 1", "warning"),
        ]
        report = generate_report(job, errs)
        assert len(report["validation_errors"]) == 1
        assert len(report["warnings"]) == 1

    def test_no_errors_empty_lists(self):
        job = _make_job()
        report = generate_report(job, [])
        assert report["validation_errors"] == []
        assert report["warnings"] == []


class TestShouldWriteReport:
    def test_no_issues_no_report(self):
        job = _make_job(records_rejected=0)
        report = generate_report(job, [])
        assert should_write_report(report) is False

    def test_validation_errors_trigger_report(self):
        job = _make_job()
        errs = [ValidationError(1, "f", "err", "error")]
        report = generate_report(job, errs)
        assert should_write_report(report) is True

    def test_failed_status_triggers_report(self):
        job = _make_job(processing_status="failed")
        report = generate_report(job, [])
        assert should_write_report(report) is True

    def test_rejected_rows_trigger_report(self):
        job = _make_job(records_rejected=3)
        report = generate_report(job, [])
        assert should_write_report(report) is True


class TestWriteReport:
    def test_writes_file(self, tmp_path):
        job = _make_job()
        report = generate_report(job, [])
        out = tmp_path / "report.txt"
        write_report(report, str(out))
        assert out.exists()
        content = out.read_text()
        assert "test.xlsx" in content
        assert "ryanair" in content

    def test_content_sections(self, tmp_path):
        job = _make_job()
        errs = [ValidationError(5, "frequency", "Bad freq", "error")]
        report = generate_report(job, errs)
        out = tmp_path / "report.txt"
        write_report(report, str(out))
        content = out.read_text()
        assert "VALIDATION ERRORS" in content
        assert "Bad freq" in content
