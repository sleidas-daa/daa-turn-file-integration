#!/usr/bin/env python3
"""CLI entry point for the AOS schedule converter.

Usage examples:
  # Process all files in queue/
  python run.py

  # Process a single file directly (does NOT need to be in queue/)
  python run.py --file "path/to/schedule.xlsx"

  # Override the detected template
  python run.py --file "schedule.xlsx" --template ryanair

  # Print a status summary of all tracked jobs
  python run.py --status

  # Include CSV header row (AOS requires no header by default)
  python run.py --with-header

Supported templates: ryanair, emerald, aer_lingus
"""
import argparse
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Ensure src/ is importable regardless of working directory
sys.path.insert(0, str(Path(__file__).parent / "src"))

from converter.config import OUTPUT_DIR, QUEUE_DIR, REPORTS_DIR
from converter.dataclasses import JobRecord
from converter.processor import process_job
from converter.queue_manager import QueueManager


def _print_job_summary(job: JobRecord) -> None:
    status_icon = {"completed": "OK", "failed": "FAIL", "queued": "WAIT", "processing": "RUN"}.get(
        job.processing_status, "?"
    )
    print(f"  [{status_icon}] {job.file_name}")
    print(f"       Template : {job.detected_template} (conf={job.confidence:.0%})")
    print(f"       Records  : {job.records_parsed} parsed, {job.records_ok} ok, {job.records_rejected} rejected")
    print(f"       Status   : {job.processing_status} | validation: {job.validation_status}")
    if job.output_file_path:
        print(f"       Output   : {job.output_file_path}")
    if job.report_path:
        print(f"       Report   : {job.report_path}")
    if job.error_messages:
        for msg in job.error_messages:
            print(f"       ERROR    : {msg}")
    if job.warnings:
        print(f"       Warnings : {len(job.warnings)}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AOS airline schedule converter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--file", "-f",
        help="Path to a specific file to process (skips queue scan)",
    )
    parser.add_argument(
        "--template", "-t",
        choices=["ryanair", "emerald", "aer_lingus"],
        help="Force a specific parser template (overrides auto-detection)",
    )
    parser.add_argument(
        "--with-header",
        action="store_true",
        dest="with_header",
        help="Include a header row in the output CSV (AOS requires no header by default)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show status of all tracked jobs and exit",
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Scan file structure without converting (Emerald plots)",
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to layout config JSON (Emerald: .emerald.json sidecar format)",
    )

    args = parser.parse_args()

    # Ensure output directories exist
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    include_header = args.with_header
    queue = QueueManager()

    if args.status:
        jobs = queue.all_jobs()
        if not jobs:
            print("No jobs tracked yet.")
        else:
            print(f"Tracked jobs ({len(jobs)}):\n")
            for job in jobs:
                _print_job_summary(job)
        return

    if args.file:
        # Single-file mode: bypass queue
        path = Path(args.file)
        if not path.exists():
            print(f"ERROR: File not found: {path}")
            sys.exit(1)

        if args.inspect:
            import json
            from converter.parsers.emerald_layout import (
                inspect_emerald_layout,
                load_emerald_config,
            )
            layout = load_emerald_config(path, args.config)
            result = inspect_emerald_layout(path, layout)
            print(json.dumps(result, indent=2))
            sys.exit(0 if result.get("parseable") else 1)

        job = JobRecord(
            id=str(uuid.uuid4()),
            file_name=path.name,
            file_path=str(path.resolve()),
            file_size=path.stat().st_size,
            timestamp=datetime.now(UTC).isoformat(),
        )
        print(f"Processing: {path.name}")
        job = process_job(
            job,
            template_override=args.template,
            include_header=include_header,
            config_path=args.config,
        )
        queue.update(job)
        _print_job_summary(job)
        sys.exit(0 if job.processing_status == "completed" else 1)

    # Queue mode: scan queue folder and process pending files
    new_files = queue.scan_for_new_files()
    if new_files:
        print(f"Found {len(new_files)} new file(s) in queue/")

    pending = queue.pending_jobs()
    if not pending:
        print("No pending jobs. Drop files into the queue/ folder and run again.")
        return

    print(f"Processing {len(pending)} job(s)...\n")
    failed = 0
    for job in pending:
        print(f">> {job.file_name}")
        job = process_job(
            job,
            template_override=args.template,
            include_header=include_header,
            config_path=args.config,
        )
        queue.update(job)
        _print_job_summary(job)
        if job.processing_status == "failed":
            failed += 1

    print(f"Done. {len(pending) - failed}/{len(pending)} succeeded.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
