"""Staging validator — validate pre-parsed AOS CSV files without running parsers.

Place AOS-format CSVs (6 columns, no header) in the staging/ folder at the
project root, then run staging_runner.py to get validation reports.
"""
import csv
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .dataclasses import JobRecord, TurnRecord
from .reporter import generate_report, write_report
from .validation import validate_records

_COLUMNS = [
    "arrival_flight", "departure_flight", "overnight",
    "effective_date", "discontinue_date", "frequency",
]


def read_staging_csv(path: Path) -> Tuple[List[TurnRecord], List[Dict[str, Any]]]:
    """Read an AOS CSV (headerless or headered) into TurnRecord objects.

    Returns (records, read_errors) where read_errors lists rows that could not
    be converted, using the same {row, field, reason} dict format as parser
    parse_errors.
    """
    records: List[TurnRecord] = []
    read_errors: List[Dict[str, Any]] = []

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if not row or all(c.strip() == "" for c in row):
                continue
            # Skip header row when present
            if i == 0 and row[0].strip().lower() == "arrival_flight":
                continue
            if len(row) < 6:
                read_errors.append({
                    "row": i + 1,
                    "field": "row",
                    "reason": f"Only {len(row)} column(s) found, expected 6",
                })
                continue
            try:
                ovn_raw = row[2].strip()
                overnight = int(ovn_raw) if ovn_raw.lstrip("-").isdigit() else 0
                records.append(TurnRecord(
                    arrival_flight=row[0].strip(),
                    departure_flight=row[1].strip(),
                    overnight=overnight,
                    effective_date=row[3].strip(),
                    discontinue_date=row[4].strip(),
                    frequency=row[5].strip(),
                ))
            except (ValueError, IndexError) as exc:
                read_errors.append({
                    "row": i + 1,
                    "field": "row",
                    "reason": f"Could not parse row: {exc}",
                })

    return records, read_errors


def validate_staging_file(
    path: Path,
    reports_dir: Path,
) -> JobRecord:
    """Validate one staging CSV, write a report, and return the JobRecord."""
    job = JobRecord(
        id=str(uuid.uuid4()),
        file_name=path.name,
        file_path=str(path),
        file_size=path.stat().st_size,
        detected_template="staging (pre-parsed)",
        confidence=1.0,
        timestamp=datetime.now(UTC).isoformat(),
    )

    validation_errors = []
    read_errors: List[Dict[str, Any]] = []

    try:
        records, read_errors = read_staging_csv(path)
        job.records_parsed = len(records)
        job.records_rejected = len(read_errors)

        validation_errors = validate_records(records)
        error_count = sum(1 for e in validation_errors if e.severity == "error")
        job.validation_status = "passed" if (error_count == 0 and not read_errors) else "failed"
        job.records_ok = len(records)
        job.processing_status = "completed"

    except Exception as exc:
        job.processing_status = "failed"
        job.error_messages.append(str(exc))

    reports_dir.mkdir(parents=True, exist_ok=True)
    report_data = generate_report(job, validation_errors, parse_errors=read_errors)
    report_path = reports_dir / f"STAGING_REPORT_{path.stem}.txt"
    write_report(report_data, str(report_path))
    job.report_path = str(report_path)

    return job
