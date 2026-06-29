"""
Ryanair schedule parser.

Input : Excel/CSV with columns AAl, AFn, DAl, DFn, Eff, Dsc, Frq, Ovn, Apt.
Output: TurnRecord list in AOS turn schema.

Hub filter: rows whose Apt value is not in config.AIRPORTS["ryanair"] are
excluded from the output and recorded in parse_errors for the report.
"""
from typing import List

import pandas as pd

from .. import config
from ..dataclasses import TurnRecord
from ..normalizer import normalize_date, normalize_flight_number, normalize_frequency_mask
from .base import BaseParser

REQUIRED_COLUMNS = {"AAl", "AFn", "DAl", "DFn", "Eff", "Dsc", "Frq"}


class RyanairParser(BaseParser):
    template_name = "ryanair"

    def parse(self) -> List[TurnRecord]:
        self.parse_errors = []

        # Hub airports for this parser (from central config)
        hubs = {h.upper() for h in config.AIRPORTS.get("ryanair", [config.DEFAULT_HUB])}

        ext = self.file_path.suffix.lower()
        if ext in (".xlsx", ".xls"):
            df = pd.read_excel(self.file_path, sheet_name=0)
        elif ext == ".csv":
            df = pd.read_csv(self.file_path)
        else:
            raise ValueError(f"Unsupported file type for Ryanair parser: {ext}")

        self._require_columns(df.columns.tolist(), REQUIRED_COLUMNS)

        records: List[TurnRecord] = []

        for idx, row in df.iterrows():
            excel_row = idx + 2  # +1 for 0-index, +1 for header row

            # --- Hub filter (configurable via config.AIRPORTS["ryanair"]) ---
            apt = str(row.get("Apt", "") or "").strip().upper()
            if apt and apt not in hubs:
                self.parse_errors.append({
                    "row": excel_row,
                    "field": "Apt",
                    "reason": (
                        f"Turn airport {apt!r} is not in hub list "
                        f"{sorted(hubs)} — excluded"
                    ),
                })
                continue

            arr_airline = row.get("AAl")
            arr_num = row.get("AFn")
            dep_airline = row.get("DAl")
            dep_num = row.get("DFn")

            # --- Bank rows: missing arrival data ---
            if pd.isna(arr_airline) or pd.isna(arr_num):
                self.parse_errors.append({
                    "row": excel_row,
                    "field": "AAl/AFn",
                    "reason": "Missing arrival airline or flight number (bank row)",
                })
                continue

            # --- Missing departure data ---
            if pd.isna(dep_airline) or pd.isna(dep_num):
                self.parse_errors.append({
                    "row": excel_row,
                    "field": "DAl/DFn",
                    "reason": "Missing departure airline or flight number",
                })
                continue

            try:
                arrival_flight = normalize_flight_number(arr_airline, arr_num)
                departure_flight = normalize_flight_number(dep_airline, dep_num)

                eff = normalize_date(row["Eff"])
                dsc = normalize_date(row["Dsc"])

                frq_raw = str(row["Frq"]).strip()
                frequency = normalize_frequency_mask(frq_raw)
                if not frequency:
                    self.parse_errors.append({
                        "row": excel_row,
                        "field": "Frq",
                        "reason": f"Invalid or empty frequency mask: {frq_raw!r}",
                    })
                    continue

                # Overnight: accept any non-negative integer.
                # Binary conversion (previous behaviour)
                # overnight = 1 if (not pd.isna(ovn_raw) and str(ovn_raw).strip()
                #                   not in ("", "nan", "0", "0.0")) else 0
                ovn_raw = row.get("Ovn")
                if pd.isna(ovn_raw) or str(ovn_raw).strip() in ("", "nan"):
                    overnight = 0
                else:
                    try:
                        overnight = max(0, int(float(str(ovn_raw).strip())))
                    except (ValueError, TypeError):
                        overnight = 0

                records.append(TurnRecord(
                    arrival_flight=arrival_flight,
                    departure_flight=departure_flight,
                    overnight=overnight,
                    effective_date=eff,
                    discontinue_date=dsc,
                    frequency=frequency,
                ))

            except Exception as e:
                self.parse_errors.append({
                    "row": excel_row,
                    "field": "general",
                    "reason": f"Unexpected error: {e}",
                })
                continue

        return records
