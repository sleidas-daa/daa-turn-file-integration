"""Tests for the staging validator (pre-parsed AOS CSV validation)."""
import csv
from pathlib import Path

import pytest
from converter.staging import read_staging_csv, validate_staging_file


def _write_csv(path: Path, rows, header: bool = False) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if header:
            writer.writerow([
                "arrival_flight", "departure_flight", "overnight",
                "effective_date", "discontinue_date", "frequency",
            ])
        for row in rows:
            writer.writerow(row)


VALID_ROW = ["FR11", "FR10", "0", "02042026", "22102026", "4"]
OVERNIGHT_ROW = ["EI3221", "EI3222", "1", "29032026", "24102026", "1234567"]


class TestReadStagingCsv:
    def test_reads_valid_headerless_csv(self, tmp_path):
        p = tmp_path / "test.csv"
        _write_csv(p, [VALID_ROW, OVERNIGHT_ROW])
        records, errors = read_staging_csv(p)
        assert len(records) == 2
        assert len(errors) == 0
        assert records[0].arrival_flight == "FR11"
        assert records[1].overnight == 1

    def test_skips_explicit_header_row(self, tmp_path):
        p = tmp_path / "with_header.csv"
        _write_csv(p, [VALID_ROW], header=True)
        records, errors = read_staging_csv(p)
        assert len(records) == 1
        assert records[0].arrival_flight == "FR11"

    def test_short_row_becomes_read_error(self, tmp_path):
        p = tmp_path / "short.csv"
        _write_csv(p, [["FR11", "FR10"]])  # only 2 columns
        records, errors = read_staging_csv(p)
        assert len(records) == 0
        assert len(errors) == 1
        assert "2 column" in errors[0]["reason"]

    def test_empty_csv_returns_empty(self, tmp_path):
        p = tmp_path / "empty.csv"
        p.write_text("", encoding="utf-8")
        records, errors = read_staging_csv(p)
        assert records == []
        assert errors == []

    def test_overnight_integer_preserved(self, tmp_path):
        p = tmp_path / "ovn.csv"
        _write_csv(p, [["FR11", "FR10", "3", "02042026", "22102026", "4"]])
        records, errors = read_staging_csv(p)
        assert len(records) == 1
        assert records[0].overnight == 3


class TestValidateStagingFile:
    def test_valid_file_passes(self, tmp_path):
        p = tmp_path / "valid.csv"
        _write_csv(p, [VALID_ROW])
        job = validate_staging_file(p, reports_dir=tmp_path / "reports")
        assert job.processing_status == "completed"
        assert job.validation_status == "passed"
        assert job.records_parsed == 1
        assert job.records_ok == 1

    def test_report_is_written(self, tmp_path):
        p = tmp_path / "valid.csv"
        _write_csv(p, [VALID_ROW])
        reports_dir = tmp_path / "reports"
        job = validate_staging_file(p, reports_dir=reports_dir)
        assert job.report_path
        assert Path(job.report_path).exists()

    def test_invalid_records_set_validation_failed(self, tmp_path):
        p = tmp_path / "bad.csv"
        # effective_date format is wrong
        _write_csv(p, [["FR11", "FR10", "0", "2026-04-02", "22102026", "4"]])
        job = validate_staging_file(p, reports_dir=tmp_path / "reports")
        assert job.validation_status == "failed"

    def test_short_row_sets_rejected_count(self, tmp_path):
        p = tmp_path / "short.csv"
        _write_csv(p, [["FR11", "FR10"]])
        job = validate_staging_file(p, reports_dir=tmp_path / "reports")
        assert job.records_rejected == 1
        assert job.validation_status == "failed"

    def test_overnight_gt_1_is_warning_not_failure(self, tmp_path):
        p = tmp_path / "high_ovn.csv"
        _write_csv(p, [["FR11", "FR10", "3", "02042026", "22102026", "4"]])
        job = validate_staging_file(p, reports_dir=tmp_path / "reports")
        # overnight=3 → warning only, validation should pass
        assert job.processing_status == "completed"
        # validation_status is "passed" because there are no errors (only a warning)
        assert job.validation_status == "passed"

    def test_report_contains_parse_error_section(self, tmp_path):
        p = tmp_path / "short.csv"
        _write_csv(p, [["FR11", "FR10"]])  # too few columns
        reports_dir = tmp_path / "reports"
        job = validate_staging_file(p, reports_dir=reports_dir)
        content = Path(job.report_path).read_text(encoding="utf-8")
        assert "PARSE ERRORS" in content
