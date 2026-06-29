"""
Orchestrates the five-stage pipeline for one schedule conversion job.

Pipeline stages
---------------
1. Detection  — detect_template() identifies which parser to use and returns a
               confidence score.  template_override bypasses this if the user
               specified --template on the CLI.

2. Parsing    — the appropriate parser reads the source file and returns a
               List[TurnRecord].  Any rows that could not be converted are
               stored in parser.parse_errors for the report.

3. Validation — validate_records() checks every TurnRecord for data quality:
               field formats, date ordering, overnight range, duplicates.
               Errors and warnings are collected but do not abort the job —
               the output CSV is still written so the user can review and
               re-submit after fixing the source file.

4. Export     — write_csv() writes the output CSV to output/.

5. Report     — generate_report() builds a summary dict; write_report() writes
               it to reports/ — but only when there is something to report
               (parse errors, validation findings, or a job failure).  Clean
               jobs produce no report file.

The job is mutated in place through all stages so the caller always gets back
the most up-to-date state.
"""
import time
from pathlib import Path
from typing import Optional

from . import config
from .config import OUTPUT_DIR, REPORTS_DIR
from .dataclasses import JobRecord
from .detection import detect_template
from .exporter import build_output_filename, write_csv
from .parsers.aer_lingus import AerLingusParser
from .parsers.emerald import EmeraldParser
from .parsers.ryanair import RyanairParser
from .reporter import generate_report, should_write_report, write_report
from .validation import validate_records

# Registry mapping template names to parser classes.
# Adding a new airline: add the class here and in config.AIRPORTS.
PARSERS = {
    "ryanair": RyanairParser,
    "emerald": EmeraldParser,
    "aer_lingus": AerLingusParser,
}


def process_job(
    job: JobRecord,
    template_override: Optional[str] = None,
    include_header: bool = False,
    config_path: Optional[str] = None,
) -> JobRecord:
    """Run the full pipeline for a single job.  Mutates and returns the job.

    Parameters
    ----------
    template_override : str or None
        If provided, skips auto-detection and uses this template directly.
        Valid values: 'ryanair', 'emerald', 'aer_lingus'.
    include_header : bool
        Write a column-name header row into the output CSV.
        AOS expects no header; enable only for debugging.
    config_path : str or None
        Path to an Emerald layout JSON sidecar.  Ignored for other parsers.
    """
    job.processing_status = "processing"
    t0 = time.perf_counter()

    parse_errors = []
    validation_errors = []

    try:
        # --- Stage 1: Detection ---
        if template_override:
            template = template_override
            confidence = 1.0   # user-supplied template is treated as certain
        else:
            template, confidence = detect_template(job.file_path)

        job.detected_template = template
        job.confidence = confidence

        if template == "unknown" or template not in PARSERS:
            raise ValueError(
                f"Could not identify template for '{job.file_name}'. "
                f"Use --template to specify manually."
            )

        # --- Stage 2: Parsing ---
        parser_cls = PARSERS[template]
        # Emerald is the only parser that accepts a layout config path;
        # passing config_path to others would cause a TypeError.
        if template == "emerald":
            parser = parser_cls(job.file_path, config_path=config_path)
        else:
            parser = parser_cls(job.file_path)
        records = parser.parse()
        parse_errors = parser.parse_errors   # rows that didn't produce TurnRecords
        job.records_parsed = len(records)
        job.records_rejected = len(parse_errors)

        # --- Stage 3: Validation ---
        validation_errors = validate_records(records)
        error_count = sum(1 for e in validation_errors if e.severity == "error")
        job.validation_status = "passed" if error_count == 0 else "failed"

        # Store only the human-readable strings on the job (the full objects
        # are passed separately to generate_report)
        job.validation_errors = [
            f"[row {e.row_index or 'file'}] {e.field}: {e.message}"
            for e in validation_errors
            if e.severity == "error"
        ]
        job.warnings = [
            f"[row {e.row_index or 'file'}] {e.field}: {e.message}"
            for e in validation_errors
            if e.severity == "warning"
        ]

        job.records_ok = len(records)

        # --- Stage 4: Export ---
        out_name = build_output_filename(job.file_path, template)
        out_path = OUTPUT_DIR / out_name
        # include_header arg overrides config when explicitly True;
        # otherwise write_csv reads config.INCLUDE_HEADER_ROW itself.
        write_csv(records, str(out_path), include_header=include_header)
        job.output_file_path = str(out_path)

        job.processing_status = "completed"

    except Exception as exc:
        job.processing_status = "failed"
        job.error_messages.append(str(exc))

    finally:
        # Always record duration regardless of success or failure
        job.processing_duration_s = time.perf_counter() - t0

    # --- Stage 5: Report ---
    # Run report generation in a separate try block so a report failure
    # does not mask the original processing error.
    try:
        report_data = generate_report(job, validation_errors, parse_errors=parse_errors)
        if should_write_report(report_data):
            report_name = f"REPORT_{Path(job.file_name).stem}.txt"
            report_path = REPORTS_DIR / report_name
            write_report(report_data, str(report_path))
            job.report_path = str(report_path)
    except Exception as rep_exc:
        job.error_messages.append(f"Report generation failed: {rep_exc}")

    return job
