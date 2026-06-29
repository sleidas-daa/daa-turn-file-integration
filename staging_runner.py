#!/usr/bin/env python3
"""Staging runner — validate pre-parsed AOS CSV files without running the parser pipeline.

Drop AOS-format CSV files (6 columns, no header) into the staging/ folder, then
run this script to get validation reports without re-parsing source schedule files.
The full parse-detect-export pipeline is bypassed; only structure/content validation
is performed.

Column order expected in staging CSVs:
  arrival_flight, departure_flight, overnight, effective_date, discontinue_date, frequency

Usage:
  python staging_runner.py                    # validate all CSVs in staging/
  python staging_runner.py --file path.csv    # validate a specific CSV
"""
import argparse
import sys
from pathlib import Path

# Ensure src/ is importable regardless of working directory
sys.path.insert(0, str(Path(__file__).parent / "src"))

from converter.config import REPORTS_DIR
from converter.dataclasses import JobRecord
from converter.staging import validate_staging_file

STAGING_DIR = Path(__file__).parent / "staging"
STAGING_REPORTS_DIR = REPORTS_DIR / "staging"


def _print_summary(job: JobRecord) -> None:
    status = "OK  " if job.processing_status == "completed" else "FAIL"
    print(f"  [{status}] {job.file_name}")
    print(f"       Records   : {job.records_parsed} parsed, "
          f"{job.records_ok} ok, {job.records_rejected} issues")
    print(f"       Validation: {job.validation_status}")
    if job.report_path:
        print(f"       Report    : {job.report_path}")
    if job.error_messages:
        for msg in job.error_messages:
            print(f"       ERROR     : {msg}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate pre-parsed AOS CSV files (staging mode)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--file", "-f",
        help="Validate a specific CSV file instead of scanning staging/",
    )
    args = parser.parse_args()

    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    if args.file:
        target = Path(args.file)
        if not target.exists():
            print(f"ERROR: File not found: {target}")
            sys.exit(1)
        paths = [target]
    else:
        paths = sorted(STAGING_DIR.glob("*.csv"))
        if not paths:
            print(f"No CSV files found in {STAGING_DIR}/")
            print("Drop AOS-format CSVs there and re-run.")
            return

    print(f"Validating {len(paths)} file(s)...\n")
    failed = 0
    for path in paths:
        print(f">> {path.name}")
        job = validate_staging_file(path, reports_dir=STAGING_REPORTS_DIR)
        _print_summary(job)
        if job.processing_status != "completed" or job.validation_status == "failed":
            failed += 1

    total = len(paths)
    print(f"Done. {total - failed}/{total} passed validation.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
