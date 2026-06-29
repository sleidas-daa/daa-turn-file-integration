"""
Write TurnRecord lists to AOS-compatible CSV files.

Two debug options (both off by default) are read from config:
  INCLUDE_HEADER_ROW           — prepend a column-name header row
  FILL_MISSING_WITH_PLACEHOLDER — replace empty/None fields with a sentinel
                                  string (default 'MISSING')

Both options change the output in ways that AOS does not expect and should
only be enabled during manual data inspection.
"""
import csv
from pathlib import Path
from typing import List

from . import config
from .dataclasses import TurnRecord


def write_csv(
    records: List[TurnRecord],
    output_path: str,
    include_header: bool = False,
    fill_missing: bool = False,
) -> Path:
    """
    Write records to a CSV file and return the Path.

    Parameters
    ----------
    include_header : bool
        Prepend a header row with column names.  Defaults to the
        INCLUDE_HEADER_ROW config value; pass explicitly to override.
    fill_missing : bool
        Replace None/empty string cells with config.MISSING_PLACEHOLDER.
        Defaults to FILL_MISSING_WITH_PLACEHOLDER config value.
    """
    # Respect explicit overrides; fall back to config defaults
    write_header = include_header or config.INCLUDE_HEADER_ROW
    do_fill = fill_missing or config.FILL_MISSING_WITH_PLACEHOLDER
    placeholder = config.MISSING_PLACEHOLDER

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        if write_header:
            writer.writerow(config.OUTPUT_COLUMNS)

        for rec in records:
            row = rec.to_row()
            if do_fill:
                # Replace any empty/None value with the configured placeholder
                row = [
                    placeholder if (v is None or str(v).strip() == "") else v
                    for v in row
                ]
            writer.writerow(row)

    return out


def build_output_filename(input_file_path: str, template: str) -> str:
    """Build the output CSV filename from the input file stem.

    Result: OUTPUT_<sanitised_stem>.csv
    Spaces in the original filename are replaced with underscores.
    """
    stem = Path(Path(input_file_path).name).stem
    stem_clean = stem.replace(" ", "_")
    return f"OUTPUT_{stem_clean}.csv"
