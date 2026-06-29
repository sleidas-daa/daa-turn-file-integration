"""
Generate human-readable processing reports.

A report is written to reports/ whenever a job has:
  - parse errors (rows in the source file that could not be converted)
  - validation warnings or errors on the output records
  - a system error that aborted processing
  - any rejected rows

Clean jobs (no warnings, no errors, no rejections) produce no report file —
this keeps the reports/ folder meaningful: a file there means something needed
human attention.

Report format
-------------
Plain UTF-8 text, one section per finding type.  Designed to be readable in
any text editor, email attachment, or copy-paste into a ticket system.
Truncated at 100 parse errors, 50 validation errors, and 30 warnings to avoid
enormous files from corrupt inputs.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .dataclasses import JobRecord, ValidationError


def generate_report(
    job: JobRecord,
    validation_errors: List[ValidationError],
    parse_errors: Optional[List[Dict[str, Any]]] = None,
) -> dict:
    """Assemble a report dict from a completed (or failed) job.

    Separates errors (severity='error') from warnings (severity='warning') so
    the report can show counts and sections for each independently.
    """
    errors = [e for e in validation_errors if e.severity == "error"]
    warnings = [e for e in validation_errors if e.severity == "warning"]

    return {
        "original_file_name": job.file_name,
        "detected_template": job.detected_template,
        "confidence_score": job.confidence,
        "records_parsed": job.records_parsed,
        "records_successful": job.records_ok,
        "records_rejected": job.records_rejected,
        "parse_errors": parse_errors or [],
        "validation_errors": [
            {"row": e.row_index, "field": e.field, "message": e.message}
            for e in errors
        ],
        "warnings": [
            {"row": e.row_index, "field": e.field, "message": e.message}
            for e in warnings
        ],
        "output_file": job.output_file_path,
        "processing_duration_s": round(job.processing_duration_s, 3),
        "processing_status": job.processing_status,
        "validation_status": job.validation_status,
        "system_errors": job.error_messages,
    }


def write_report(report: dict, report_path: str) -> Path:
    """Write the report as a human-readable text file.

    Sections are omitted when empty so the output stays concise.
    """
    out = Path(report_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "=" * 60,
        "AOS SCHEDULE CONVERSION REPORT",
        "=" * 60,
        f"File          : {report['original_file_name']}",
        f"Template      : {report['detected_template']} "
        f"(confidence: {report['confidence_score']:.0%})",
        f"Status        : {report['processing_status']}",
        f"Validation    : {report['validation_status']}",
        f"Duration      : {report['processing_duration_s']:.3f}s",
        "",
        "RECORDS",
        f"  Parsed      : {report['records_parsed']}",
        f"  Successful  : {report['records_successful']}",
        f"  Rejected    : {report['records_rejected']}",
        "",
        f"Output file   : {report['output_file']}",
    ]

    # System errors (Python exceptions that aborted or degraded processing)
    if report["system_errors"]:
        lines += ["", "SYSTEM ERRORS"] + [f"  - {e}" for e in report["system_errors"]]

    # Parse errors: rows in the source file that could not be converted at all.
    # These are structural problems (missing columns, wrong format, etc.)
    # Capped at 100 to avoid multi-MB reports from completely wrong file formats.
    if report.get("parse_errors"):
        lines += [
            "",
            f"PARSE ERRORS ({len(report['parse_errors'])}) "
            "-- rows that could not be converted to turn records:",
        ]
        for e in report["parse_errors"][:100]:
            row_str = f"row {e.get('row', '?')}" if e.get("row") is not None else "row ?"
            field = e.get("field", "parse")
            reason = e.get("reason", "unknown error")
            lines.append(f"  [{row_str}] {field}: {reason}")
        if len(report["parse_errors"]) > 100:
            lines.append(f"  ... and {len(report['parse_errors']) - 100} more")

    # Validation errors: records that were extracted but fail data quality rules.
    # These block a clean 'validation: passed' status.
    if report["validation_errors"]:
        lines += [
            "",
            f"VALIDATION ERRORS ({len(report['validation_errors'])})",
        ]
        for e in report["validation_errors"][:50]:
            row_str = f"row {e['row']}" if e["row"] is not None else "file"
            lines.append(f"  [{row_str}] {e['field']}: {e['message']}")
        if len(report["validation_errors"]) > 50:
            lines.append(f"  ... and {len(report['validation_errors']) - 50} more")

    # Warnings: data quality notes that do not block export.
    # Includes overnight > 1 notices (configurable via config.WARN_OVERNIGHT_GT_1).
    if report["warnings"]:
        lines += [
            "",
            f"WARNINGS ({len(report['warnings'])})",
        ]
        for w in report["warnings"][:30]:
            row_str = f"row {w['row']}" if w["row"] is not None else "file"
            lines.append(f"  [{row_str}] {w['field']}: {w['message']}")

    lines += ["", "=" * 60]

    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return out


def should_write_report(report: dict) -> bool:
    """Return True only if there is something noteworthy to report.

    Clean successful jobs produce no report file.  This keeps the reports/
    folder signal-rich: any file there deserves human review.
    """
    return bool(
        report.get("parse_errors")
        or report["validation_errors"]
        or report["warnings"]
        or report["system_errors"]
        or report["records_rejected"] > 0
        or report["processing_status"] == "failed"
    )
