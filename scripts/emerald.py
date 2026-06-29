#!/usr/bin/env python3
"""
Convert an Emerald Airlines DUB aircraft plot (.xlsx) into EAI schedule format.

The DUB plot lists each aircraft's daily rotation by day of week. The EAI file
captures turn pairs (inbound flight -> next outbound flight) for each ops day.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.exists():
    sys.path.insert(0, str(_SRC))

try:
    from converter.normalizer import parse_emerald_day_header
except ImportError:
    parse_emerald_day_header = None

DAY_TO_OPS = {
    "Monday": 1,
    "Tuesday": 2,
    "Wednesday": 3,
    "Thursday": 4,
    "Friday": 5,
    "Saturday": 6,
    "Sunday": 7,
}

EAI_COLUMNS = [
    "Arrival",
    "Departure",
    "Overnight",
    "Effective date",
    "Discontinue date",
    "Ops day",
]


def normalize_flight_number(value) -> str | None:
    if pd.isna(value):
        return None
    return str(value).replace(" ", "").upper()


def parse_aircraft_columns(df: pd.DataFrame) -> list[tuple[int, str]]:
    columns: list[tuple[int, str]] = []
    scan_limit = min(25, len(df))
    for row_idx in range(scan_limit):
        row = df.iloc[row_idx]
        candidates = [
            (col_idx, str(value).strip())
            for col_idx, value in enumerate(row)
            if pd.notna(value) and str(value).strip().upper().startswith("EAI")
        ]
        if candidates:
            columns = candidates
            break
    if not columns:
        raise ValueError(
            "Could not find aircraft columns (expected cells starting with 'EAI')."
        )
    return columns


def _parse_day_cell(cell) -> tuple[str, int] | None:
    if pd.isna(cell):
        return None
    text = str(cell).strip()
    if parse_emerald_day_header is not None:
        parsed = parse_emerald_day_header(text)
        if parsed:
            day_name, _, ops_day = parsed
            return day_name, ops_day
    match = re.match(
        r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
        r"(?:\s*(\d{1,2}[A-Za-z]{3}\d{2,4})|\b)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    day_name = match.group(1).capitalize()
    return day_name, DAY_TO_OPS[day_name]


def parse_day_rows(df: pd.DataFrame) -> list[tuple[int, str, int]]:
    """Return (start_row, day_name, ops_day) for each day block."""
    day_rows: list[tuple[int, str, int]] = []
    for row_idx in range(len(df)):
        parsed = _parse_day_cell(df.iloc[row_idx, 0])
        if parsed:
            day_name, ops_day = parsed
            day_rows.append((row_idx, day_name, ops_day))
    if not day_rows:
        raise ValueError("Could not find any day rows in the DUB plot.")
    return day_rows


def read_flights(df: pd.DataFrame, col_idx: int, start_row: int, end_row: int) -> list[dict]:
    flights: list[dict] = []
    for row_idx in range(start_row, end_row):
        flight_no = normalize_flight_number(df.iloc[row_idx, col_idx])
        if not flight_no:
            continue

        origin = df.iloc[row_idx, col_idx + 1]
        destination = df.iloc[row_idx, col_idx + 3]
        if pd.isna(origin) or pd.isna(destination):
            continue

        flights.append(
            {
                "flight": flight_no,
                "orig": str(origin).strip().upper(),
                "dest": str(destination).strip().upper(),
            }
        )
    return flights


def first_dub_departure(flights: list[dict]) -> str | None:
    for flight in flights:
        if flight["orig"] == "DUB":
            return flight["flight"]
    return None


def next_dub_departure(flights: list[dict], after_idx: int = 0) -> str | None:
    for idx in range(after_idx, len(flights)):
        if flights[idx]["orig"] == "DUB":
            return flights[idx]["flight"]
    return None


def last_dub_arrival(flights: list[dict]) -> str | None:
    for flight in reversed(flights):
        if flight["dest"] == "DUB":
            return flight["flight"]
    return None


def is_away_from_dub(flight: dict) -> bool:
    return flight["orig"] != "DUB" and flight["dest"] != "DUB"


def extract_turn_pairs(flights: list[dict], next_day_flights: list[dict]) -> list[tuple[str, str, int]]:
    """
    Build EAI turn rows for one aircraft on one ops day.

    Rules:
    - DUB turn: inbound flight arriving at DUB -> next departure from DUB same day
    - Away turn: consecutive sectors entirely away from DUB (e.g. GLA-ORK, ORK-GLA)
    - Overnight: last DUB arrival of the day -> first DUB departure next day
      (Sunday wraps to Monday)
    """
    pairs: list[tuple[str, str, int]] = []
    if not flights:
        return pairs

    for idx, flight in enumerate(flights):
        if idx + 1 < len(flights):
            nxt = flights[idx + 1]
            if (
                is_away_from_dub(flight)
                and is_away_from_dub(nxt)
                and flight["dest"] == nxt["orig"]
            ):
                pairs.append((flight["flight"], nxt["flight"], 0))

        if flight["dest"] == "DUB":
            departure = next_dub_departure(flights, idx + 1)
            if departure:
                pairs.append((flight["flight"], departure, 0))

    overnight_arrival = last_dub_arrival(flights)
    overnight_departure = first_dub_departure(next_day_flights)
    if overnight_arrival and overnight_departure:
        pairs.append((overnight_arrival, overnight_departure, 1))

    return pairs


def convert_dub_plot(
    dub_path: Path,
    effective_date: int,
    discontinue_date: int,
) -> pd.DataFrame:
    df = pd.read_excel(dub_path, sheet_name=0, header=None)
    aircraft_columns = parse_aircraft_columns(df)
    day_rows = parse_day_rows(df)

    records: list[dict] = []

    for col_idx, _aircraft in aircraft_columns:
        for day_idx, (start_row, _day_name, ops_day) in enumerate(day_rows):
            end_row = (
                day_rows[day_idx + 1][0]
                if day_idx + 1 < len(day_rows)
                else len(df)
            )
            flights = read_flights(df, col_idx, start_row, end_row)

            if day_idx + 1 < len(day_rows):
                next_start = day_rows[day_idx + 1][0]
                next_end = (
                    day_rows[day_idx + 2][0]
                    if day_idx + 2 < len(day_rows)
                    else len(df)
                )
                next_day_flights = read_flights(df, col_idx, next_start, next_end)
            else:
                next_day_flights = read_flights(
                    df,
                    col_idx,
                    day_rows[0][0],
                    day_rows[1][0],
                )

            for arrival, departure, overnight in extract_turn_pairs(
                flights, next_day_flights
            ):
                records.append(
                    {
                        "Arrival": arrival,
                        "Departure": departure,
                        "Overnight": overnight,
                        "Effective date": effective_date,
                        "Discontinue date": discontinue_date,
                        "Ops day": ops_day,
                    }
                )

    if not records:
        raise ValueError("No turn pairs were extracted from the DUB plot.")

    result = pd.DataFrame(records)
    result = result.drop_duplicates(
        subset=["Arrival", "Departure", "Overnight", "Ops day"]
    )
    result = result.sort_values(
        by=["Ops day", "Arrival", "Departure", "Overnight"],
        kind="stable",
    ).reset_index(drop=True)
    return result[EAI_COLUMNS]


def write_eai_workbook(df: pd.DataFrame, output_path: Path) -> None:
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Sheet1", index=False)
        for sheet_name in ("Sheet2", "Sheet3"):
            pd.DataFrame().to_excel(writer, sheet_name=sheet_name, index=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert Emerald Airlines DUB aircraft plot to EAI format."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="DUB plot 27012026 - emerald airlines.xlsx",
        help="Path to the airline DUB plot .xlsx file",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output .xlsx path (default: <input stem> - EAI.xlsx)",
    )
    parser.add_argument(
        "--effective-date",
        type=int,
        default=29032026,
        help="Effective date in DDMMYYYY format (default: 29032026)",
    )
    parser.add_argument(
        "--discontinue-date",
        type=int,
        default=24102026,
        help="Discontinue date in DDMMYYYY format (default: 24102026)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.exists():
        parser.error(f"Input file not found: {input_path}")

    output_path = (
        Path(args.output)
        if args.output
        else input_path.with_name(f"{input_path.stem} - EAI.xlsx")
    )

    try:
        eai_df = convert_dub_plot(
            input_path,
            effective_date=args.effective_date,
            discontinue_date=args.discontinue_date,
        )
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    write_eai_workbook(eai_df, output_path)
    print(f"Wrote {len(eai_df)} rows to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
