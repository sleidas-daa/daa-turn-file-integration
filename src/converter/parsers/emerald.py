"""
Emerald Airlines DUB aircraft plot parser (.xlsx).

Input format
------------
Emerald provides a wide horizontal grid where each column after the first
represents one aircraft registration.  Days of the week are stacked
vertically as named sections.  A typical layout (simplified):

    Row 7:  DAY       | EAI AT7 FAT | EAI ATR | ...
    Row 8:  (blank spacer)
    Row 9:  Monday 13JUL26
    Row 10: (blank) EI 3220  DUB 05:50  GLA 07:05
    Row 11: (blank) EI 3221  GLA 07:35  DUB 08:50
    ...
    Row N:  (blank spacer)
    Row N+1: Tuesday 14JUL26
    ...

Each aircraft column has a sub-grid of: flight | from_apt | from_time | to_apt | to_time.
Time values are stored as Excel time objects.

Turn matching
-------------
Within each aircraft column, legs are ordered chronologically across all
weekdays.  The parser treats consecutive pairs as a turn when:
  • leg[i] arrives at a configured hub airport
  • leg[i+1] departs from that same airport

The week wraps: the last leg of Sunday is paired with the first leg of
Monday to capture turns that start at the end of the week.

Overnight calculation: (departure_day - arrival_day) % 7
--------------------------------------------------------
IATA weekday numbering is 1=Monday, 7=Sunday.  Modular-7 arithmetic
gives the correct number of nights even across the week boundary:
  Mon (1) → Mon (1): (1-1) % 7 = 0   (same-day turn)
  Mon (1) → Tue (2): (2-1) % 7 = 1   (one overnight)
  Mon (1) → Thu (4): (4-1) % 7 = 3   (three nights)
  Fri (5) → Mon (1): (1-5) % 7 = 3   (crosses weekend)
  Tue (2) → Mon (1): (1-2) % 7 = 6   (six nights — unusual but valid)

Values > 1 are unusual and trigger a warning if config.WARN_OVERNIGHT_GT_1
is True (the default).  Values of 3 or more indicate an aircraft parked at
the hub for several days between operations — this can be legitimate (e.g.
a Monday arrival/Thursday departure for scheduled maintenance).

Layout overrides
----------------
If the standard column mapping doesn't match a particular file, a JSON
sidecar can be placed alongside the input:
    my_plot.xlsx
    my_plot.xlsx.emerald.json
See EmeraldLayoutConfig in emerald_layout.py for the full schema.
"""
from dataclasses import dataclass
from datetime import time
from typing import List, Optional, Tuple

import openpyxl

from ..dataclasses import TurnRecord
from ..normalizer import normalize_emerald_flight
from .base import BaseParser
from .emerald_layout import (
    EmeraldLayoutConfig,
    _find_aircraft_columns,
    _find_header_row,
    _parse_day_sections,
    load_emerald_config,
    validate_emerald_structure,
)


@dataclass
class _Leg:
    """Internal representation of a single flight leg from the plot grid.

    day_num uses IATA weekday numbering (1=Monday, 7=Sunday) derived from
    the section header (e.g. "Monday 13JUL26" → day_num=1).
    """
    flight: str
    from_apt: str
    from_time: Optional[time]
    to_apt: str
    to_time: Optional[time]
    day_num: int


class EmeraldParser(BaseParser):
    template_name = "emerald"

    def __init__(
        self,
        file_path: str,
        layout: Optional[EmeraldLayoutConfig] = None,
        config_path: Optional[str] = None,
    ):
        super().__init__(file_path)
        # Load layout from sidecar JSON if present, otherwise use defaults.
        # The sidecar path can be explicitly overridden via config_path (--config CLI flag).
        self.layout = layout or load_emerald_config(file_path, config_path)

    def parse(self) -> List[TurnRecord]:
        self.parse_errors = []

        # Load the whole workbook into memory.  data_only=True ensures formula
        # cells return their last-calculated value rather than the formula text.
        wb = openpyxl.load_workbook(self.file_path, data_only=True)
        ws = wb.active
        all_rows = [tuple(row) for row in ws.iter_rows(values_only=True)]
        wb.close()

        layout = self.layout

        # --- Locate the header row ---
        # The header row is identified by the presence of layout.header_marker
        # (default: 'DAY') in the day-column.  Its row index determines where
        # aircraft columns are labelled and where day sections begin.
        header_row_idx = _find_header_row(all_rows, layout.header_marker)
        if header_row_idx is None:
            raise ValueError(
                f"Could not find Emerald header row with '{layout.header_marker}' "
                f"in column {layout.day_column + 1}. "
                f"Run with --inspect or add a {self.file_path.name}.emerald.json sidecar."
            )

        # --- Identify aircraft columns and day sections ---
        # Each non-blank cell in the header row (after the DAY column) is one aircraft.
        # Day sections are blocks of rows between weekday-name cells in column A.
        aircraft_cols = _find_aircraft_columns(all_rows[header_row_idx], layout)
        day_sections = _parse_day_sections(
            all_rows, header_row_idx + 1, layout.day_column
        )

        # Structural warnings (e.g. unrecognised columns) go into parse_errors
        # so they appear in the report but do not abort processing.
        self.parse_errors.extend(
            validate_emerald_structure(aircraft_cols, day_sections, layout)
        )

        # --- Build turn records for each aircraft column ---
        records: List[TurnRecord] = []
        for ac_start_col, _ac_name in aircraft_cols:
            # Collect all legs for this aircraft across all weekdays
            legs = self._collect_legs(day_sections, ac_start_col)
            # Pair consecutive hub-arrival/hub-departure legs into TurnRecords
            records.extend(self._build_turns(legs))

        # If nothing was extracted but there were structural errors, surface them
        if not records and self.parse_errors:
            raise ValueError(
                "No turn pairs extracted. See report for structural issues, "
                "or add a sidecar .emerald.json to adjust column mapping."
            )

        return records

    def _collect_legs(
        self, day_sections: List[Tuple[int, list]], col_start: int
    ) -> List[_Leg]:
        """Read leg rows from one aircraft column across all day sections.

        Legs are collected in ascending weekday order (Monday first) so that
        consecutive pairs correctly reflect the aircraft's week schedule.
        """
        layout = self.layout
        legs: List[_Leg] = []

        for day_num, rows in sorted(day_sections, key=lambda x: x[0]):
            for row in rows:
                # Column indices are relative to the aircraft column's start position.
                # flight_offset, from_offset, to_offset are defined in EmeraldLayoutConfig.
                flight_col = col_start + layout.flight_offset
                from_col = col_start + layout.from_offset
                to_col = col_start + layout.to_offset
                time_from_col = col_start + layout.from_offset + 1
                time_to_col = col_start + layout.to_offset + 1

                if len(row) <= max(flight_col, from_col, to_col):
                    continue   # row is too short (blank row or different section)

                flight = row[flight_col]
                from_apt = row[from_col]
                from_time = row[time_from_col] if time_from_col < len(row) else None
                to_apt = row[to_col]
                to_time = row[time_to_col] if time_to_col < len(row) else None

                # Skip blank rows (no flight number) and non-string cells
                # (some layouts have numeric or None placeholders)
                if not flight or not isinstance(flight, str):
                    continue
                if not from_apt or not to_apt:
                    continue

                legs.append(_Leg(
                    flight=normalize_emerald_flight(flight),
                    from_apt=str(from_apt).strip().upper(),
                    from_time=from_time if isinstance(from_time, time) else None,
                    to_apt=str(to_apt).strip().upper(),
                    to_time=to_time if isinstance(to_time, time) else None,
                    day_num=day_num,
                ))

        return legs

    def _build_turns(self, legs: List[_Leg]) -> List[TurnRecord]:
        """Pair consecutive legs into TurnRecords where the connection is at a hub.

        Pairing rule
        ------------
        For each leg[i], check if:
          1. leg[i].to_apt == leg[i+1].from_apt   — the aircraft connects through
                                                     the same airport
          2. that airport is in the configured hub set (config.AIRPORTS["emerald"])

        If both conditions are met, leg[i] is the inbound (arrival) and
        leg[i+1] is the outbound (departure), forming one TurnRecord.

        The index wraps via % n so that the last Sunday leg pairs with the
        first Monday leg — capturing turns that sit at the hub over the weekend.

        Overnight formula
        -----------------
        overnight = (dep_day_num - arr_day_num) % 7

        This produces the number of nights between the two legs.  Modular
        arithmetic handles the week boundary correctly: a Friday arrival (5)
        pairing with a Monday departure (1) gives (1-5) % 7 = 3 nights.
        """
        if not legs:
            return []

        layout = self.layout
        home = layout.home_airport_set()   # set of hub airport codes e.g. {'DUB', 'ORK'}
        records: List[TurnRecord] = []
        n = len(legs)

        for i in range(n):
            a = legs[i]              # inbound leg (arriving at hub)
            b = legs[(i + 1) % n]   # outbound leg (departing from hub)

            # Connection check: the aircraft must land and depart from the same airport
            if a.to_apt != b.from_apt:
                continue

            # Hub filter: only hub connections produce turn records.
            # Non-hub connections (e.g. GLA→EDI) are ignored.
            if a.to_apt not in home:
                continue

            # Overnight = nights between arrival and departure.
            # Modular-7 arithmetic keeps the result in 0–6 regardless of the
            # week boundary.  See module docstring for the full example table.
            overnight = (b.day_num - a.day_num) % 7

            records.append(TurnRecord(
                arrival_flight=a.flight,
                departure_flight=b.flight,
                overnight=overnight,
                effective_date=layout.effective_date_value(),
                discontinue_date=layout.discontinue_date_value(),
                frequency=str(a.day_num),   # IATA weekday digit of the arrival day
            ))

        return records
