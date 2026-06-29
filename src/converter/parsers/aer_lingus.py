"""
Aer Lingus SSIM parser — IATA Type-3 fixed-width records (.txt).

The Aer Lingus SSIM export uses an extended Type-3 layout that differs from
the simplified textbook format in two important ways:

1. There are 4 extra characters between the standard check-character field
   (position 9) and the effective-date field.  In the standard SSIM the
   effective date begins at position 10; in this file it begins at position 14.

2. Both departure and arrival blocks carry a second (UTC) time field in
   addition to the local time, making the block 15 characters wide instead of
   the standard 9.

Concrete 0-indexed field map (verified against the live EI W23 SSIM file):

  [0]      Record type ('3')
  [1]      Service indicator (space for scheduled passenger)
  [2:5]    Airline designator (3-char IATA, e.g. 'EI ')
  [5:9]    Flight number (4-char, right-justified, space-padded)
  [9]      Itinerary variation identifier
  [10:14]  Extra fields: leg/service/operator codes
  [14:21]  Effective period FROM  (DDMMMYY, e.g. '31OCT23')
  [21:28]  Effective period TO    (DDMMMYY)
  [28:35]  Days of operation      (7-char mask, e.g. '  3    ' = Wednesday)
  [35]     Frequency rate
  [36:39]  Departure airport (IATA 3-letter)
  [39:43]  Scheduled departure time — local (HHMM)
  [43:47]  Scheduled departure time — UTC   (HHMM, extra field)
  [47:52]  UTC variation at departure (+-HHMM, 5-char)
  [52:54]  Pad / terminal prefix (2 chars)
  [54:57]  Arrival airport (IATA 3-letter)
  [57:61]  Scheduled arrival time — local  (HHMM)
  [61:65]  Scheduled arrival time — UTC    (HHMM, extra field)
  [65:70]  UTC variation at arrival (+-HHMM, 5-char)

Turns are matched by date and time: for every leg that arrives at a hub
airport, the parser finds the earliest departure from the same hub airport on
the same operating date whose departure time is strictly after the arrival time.
This greedy sweep correctly handles multi-route hub operations where different
inbound flights connect to different outbound flights on the same day.
"""
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .. import config
from ..config import SEASON_DISCONTINUE, SEASON_EFFECTIVE
from ..dataclasses import TurnRecord
from .base import BaseParser

# ---------------------------------------------------------------------------
# Month abbreviation lookup (SSIM dates use 3-letter English month names)
# ---------------------------------------------------------------------------

_MONTHS = {
    "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
    "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
    "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
}


def _parse_ssim_date(raw: str) -> str:
    """Convert SSIM date 'DDMMMYY' or 'DDMMMYYYY' to 'DDMMYYYY'."""
    raw = raw.strip()
    m = re.fullmatch(r"(\d{1,2})([A-Za-z]{3})(\d{2,4})", raw)
    if not m:
        raise ValueError(f"Unrecognised SSIM date: {raw!r}")
    day = int(m.group(1))
    mon = _MONTHS[m.group(2).upper()]
    yr = m.group(3)
    if len(yr) == 2:
        yr = "20" + yr
    return f"{day:02d}{mon}{yr}"


def _parse_days_mask(raw: str) -> str:
    """
    Collapse a 7-char SSIM days-of-operation field to only the active digits.

    '  3    ' -> '3'   (Wednesday only)
    '2    6 ' -> '26'  (Tuesday and Saturday)
    '1234567' -> '1234567'
    """
    return "".join(c for c in raw if c.strip() and c.isdigit())


def _ddmmyyyy_to_date(ddmmyyyy: str) -> Optional[datetime]:
    """Parse 'DDMMYYYY' into a datetime.date; return None on failure."""
    try:
        return datetime.strptime(ddmmyyyy, "%d%m%Y")
    except ValueError:
        return None


def _date_to_ddmmyyyy(dt: datetime) -> str:
    """Format a datetime as 'DDMMYYYY'."""
    return dt.strftime("%d%m%Y")


class AerLingusParser(BaseParser):
    """Parser for Aer Lingus IATA SSIM Type-3 schedule files (.txt)."""

    template_name = "aer_lingus"

    def parse(self) -> List[TurnRecord]:
        self.parse_errors = []
        ext = self.file_path.suffix.lower()
        if ext == ".txt":
            return self._parse_ssim_txt()
        raise ValueError(f"Unsupported file type for Aer Lingus parser: {ext}")

    # ------------------------------------------------------------------
    # Main SSIM parsing pass
    # ------------------------------------------------------------------

    def _parse_ssim_txt(self) -> List[TurnRecord]:
        """Read the SSIM file and build turn records."""
        with open(self.file_path, "r", encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()

        # Collect all Type-3 flight leg records
        legs: List[dict] = []
        for line in lines:
            if not line or line[0] != "3":
                continue
            leg = self._parse_type3(line)
            if leg:
                legs.append(leg)

        if not legs:
            return []

        return self._build_hub_turns(legs)

    def _parse_type3(self, line: str) -> Optional[dict]:
        """
        Parse a single Type-3 SSIM record using the extended EI field layout.

        Returns a dict of extracted fields, or None if the line is malformed
        or missing required fields.
        """
        # Guarantee we have enough characters even if the file has short lines
        line = line.rstrip("\n").ljust(200)

        try:
            # --- Airline and flight number ---------------------------------
            airline = line[2:5].strip()            # e.g. 'EI'

            # The 4-char flight-number field is space-padded and right-justified.
            # We strip the outer whitespace only — leading zeros (e.g. '052')
            # are part of the published flight identifier ('EI052' not 'EI52').
            flight_num_raw = line[5:9].strip()     # e.g. '052', '3221', '520'
            if not airline or not flight_num_raw:
                return None

            # --- Date range and operating days ----------------------------
            # These fields sit 4 positions later than the textbook SSIM layout
            # because the EI file inserts extra operator/service fields at
            # positions 10-13.
            eff_raw = line[14:21].strip()          # e.g. '31OCT23'
            dsc_raw = line[21:28].strip()          # e.g. '31OCT23'
            days_raw = line[28:35]                 # e.g. '  2    ' (Tuesday)

            # --- Airports --------------------------------------------------
            dep_apt = line[36:39].strip()          # e.g. 'SEA', 'DUB'
            arr_apt = line[54:57].strip()          # e.g. 'DUB', 'MAN'

            if not dep_apt or not arr_apt:
                return None

            # --- Times (local HHMM) ----------------------------------------
            dep_time = line[39:43].strip()         # departure time local
            arr_time = line[57:61].strip()         # arrival time local

            # --- Build normalised values -----------------------------------
            eff = _parse_ssim_date(eff_raw) if eff_raw else SEASON_EFFECTIVE
            dsc = _parse_ssim_date(dsc_raw) if dsc_raw else SEASON_DISCONTINUE
            days = _parse_days_mask(days_raw) if days_raw.strip() else ""
            flight_id = f"{airline}{flight_num_raw}"   # 'EI052', 'EI3221' …

            return {
                "flight_id": flight_id,
                "airline": airline,
                "flight_num": flight_num_raw,
                "eff": eff,
                "dsc": dsc,
                "days": days,
                "dep_apt": dep_apt,
                "dep_time": dep_time,
                "arr_apt": arr_apt,
                "arr_time": arr_time,
            }

        except Exception:
            # Malformed line — silently skip; Type-1/2/9 records fall here too
            return None

    # ------------------------------------------------------------------
    # Turn-matching: time-based sweep
    # ------------------------------------------------------------------

    def _build_hub_turns(self, legs: List[dict]) -> List[TurnRecord]:
        """
        Match hub arrivals with subsequent hub departures to produce TurnRecords.

        Strategy
        --------
        Each SSIM record is a single flight on a specific date.  For every date
        we collect:
          • arrivals  — legs whose arr_apt is a hub
          • departures — legs whose dep_apt is a hub

        We sort both lists by time and sweep through them: the earliest arriving
        flight is paired with the earliest available departure whose departure
        time is strictly later than the arrival time (same-day turn, overnight=0).
        If no same-day departure exists, we look one day ahead (overnight=1).

        This greedy approach mirrors how airport slot tools assign turns and
        correctly handles cases where multiple inbound flights at the same hub on
        the same day connect to different outbound flights.
        """
        hubs = {h.upper() for h in config.AIRPORTS.get("aer_lingus", [config.DEFAULT_HUB])}

        arrivals = [l for l in legs if l["arr_apt"] in hubs]
        departures = [l for l in legs if l["dep_apt"] in hubs]

        # Index departures by operating date for O(1) lookup
        deps_by_date: Dict[str, List[dict]] = {}
        for dep in departures:
            deps_by_date.setdefault(dep["eff"], []).append(dep)

        # Sort each day's departures by departure time once, up front
        for date_key in deps_by_date:
            deps_by_date[date_key].sort(key=lambda d: d.get("dep_time") or "")

        # Sort arrivals by (date, arrival time) so earlier arrivals get first
        # pick of the available departures (greedy sweep)
        arrivals.sort(key=lambda a: (a["eff"], a.get("arr_time") or ""))

        # Track which departure records have already been matched so each
        # aircraft slot is used at most once
        matched_dep_ids: set = set()

        records: List[TurnRecord] = []

        for arr in arrivals:
            arr_date = arr["eff"]
            arr_time = arr.get("arr_time") or ""

            dep, overnight = self._find_next_departure(
                arr_date, arr_time, deps_by_date, matched_dep_ids
            )
            if dep is None:
                continue

            matched_dep_ids.add(id(dep))

            records.append(TurnRecord(
                arrival_flight=arr["flight_id"],
                departure_flight=dep["flight_id"],
                overnight=overnight,
                effective_date=arr_date,
                discontinue_date=arr["dsc"],
                frequency=arr["days"] or dep["days"] or "",
            ))

        return records

    def _find_next_departure(
        self,
        arr_date: str,
        arr_time: str,
        deps_by_date: Dict[str, List[dict]],
        matched_ids: set,
    ):
        """
        Return (dep_dict, overnight_count) for the next available departure.

        Tries same-day first (overnight=0), then next-day (overnight=1).
        Returns (None, 0) if nothing is available.
        """
        # --- Same-day: departure time must be after arrival time ----------
        for dep in deps_by_date.get(arr_date, []):
            if id(dep) in matched_ids:
                continue
            dep_time = dep.get("dep_time") or ""
            if dep_time > arr_time:
                return dep, 0

        # --- Next-day: any departure qualifies (aircraft overnighted) -----
        arr_dt = _ddmmyyyy_to_date(arr_date)
        if arr_dt is not None:
            next_date = _date_to_ddmmyyyy(arr_dt + timedelta(days=1))
            for dep in deps_by_date.get(next_date, []):
                if id(dep) in matched_ids:
                    continue
                return dep, 1

        return None, 0
