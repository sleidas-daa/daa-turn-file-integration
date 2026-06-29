"""
Validation rules for TurnRecord lists.

Each TurnRecord is checked for:
  • non-empty arrival and departure flight numbers
  • standard IATA flight-number format (2-3 letter code + digits)
  • overnight being a non-negative integer (warning when > 1 if configured)
  • effective and discontinue dates in DDMMYYYY format within a plausible range
  • effective date not after discontinue date
  • frequency digits in the range 1-7 with no duplicates

Warning-level findings do not block export but appear in the report file.
Some warning types can be suppressed via config.py flags.
"""
import re
from typing import List

from . import config
from .dataclasses import TurnRecord, ValidationError


def validate_records(records: List[TurnRecord]) -> List[ValidationError]:
    """Validate a list of TurnRecord objects and return all findings."""
    errors: List[ValidationError] = []

    if not records:
        errors.append(ValidationError(None, "records", "No records produced", "warning"))
        return errors

    seen: set = set()

    for i, rec in enumerate(records):
        row = i + 1

        # --- Required fields ---
        if not rec.arrival_flight or not rec.arrival_flight.strip():
            errors.append(ValidationError(row, "arrival_flight", "Missing arrival flight number"))
        if not rec.departure_flight or not rec.departure_flight.strip():
            errors.append(ValidationError(row, "departure_flight", "Missing departure flight number"))

        # --- Flight number format (IATA: 2-3 letter code + digits) ---
        # We allow leading zeros in the numeric part (e.g. EI052 is valid)
        if rec.arrival_flight and not re.match(r"^[A-Z0-9]{2,3}\d+$", rec.arrival_flight):
            errors.append(ValidationError(
                row, "arrival_flight",
                f"Non-standard flight number format: {rec.arrival_flight!r}", "warning"
            ))
        if rec.departure_flight and not re.match(r"^[A-Z0-9]{2,3}\d+$", rec.departure_flight):
            errors.append(ValidationError(
                row, "departure_flight",
                f"Non-standard flight number format: {rec.departure_flight!r}", "warning"
            ))

        # --- Overnight ---
        if not isinstance(rec.overnight, int) or rec.overnight < 0:
            errors.append(ValidationError(
                row, "overnight",
                f"Overnight must be a non-negative integer, got {rec.overnight!r}"
            ))
        elif rec.overnight > 1 and config.WARN_OVERNIGHT_GT_1:
            # This warning is suppressed when WARN_OVERNIGHT_GT_1 = False in config
            errors.append(ValidationError(
                row, "overnight",
                f"Overnight value {rec.overnight} is greater than 1 — verify this is intentional",
                "warning",
            ))

        # --- Date format: exactly 8 digits DDMMYYYY ---
        for field_name, date_val in (
            ("effective_date", rec.effective_date),
            ("discontinue_date", rec.discontinue_date),
        ):
            if not date_val or not re.fullmatch(r"\d{8}", str(date_val)):
                errors.append(ValidationError(
                    row, field_name, f"Invalid date format (expected DDMMYYYY): {date_val!r}"
                ))
            else:
                _validate_date_range(row, field_name, str(date_val), errors)

        # --- Effective must not exceed discontinue ---
        if (
            rec.effective_date and rec.discontinue_date
            and re.fullmatch(r"\d{8}", rec.effective_date)
            and re.fullmatch(r"\d{8}", rec.discontinue_date)
        ):
            if _date_sort_key(rec.effective_date) > _date_sort_key(rec.discontinue_date):
                errors.append(ValidationError(
                    row, "effective_date",
                    f"Effective date {rec.effective_date} is after discontinue {rec.discontinue_date}"
                ))

        # --- Frequency: non-empty, digits 1-7 only ---
        freq = str(rec.frequency).strip()
        if not freq:
            errors.append(ValidationError(row, "frequency", "Missing frequency / ops day"))
        else:
            if not re.fullmatch(r"[1-7]+", freq):
                errors.append(ValidationError(
                    row, "frequency", f"Frequency must contain digits 1-7 only, got {freq!r}"
                ))
            elif len(set(freq)) != len(freq):
                errors.append(ValidationError(
                    row, "frequency", f"Duplicate day digits in frequency: {freq!r}", "warning"
                ))

        # --- Duplicate detection ---
        key = (rec.arrival_flight, rec.departure_flight, rec.effective_date,
               rec.discontinue_date, rec.frequency)
        if key in seen:
            errors.append(ValidationError(
                row, "record",
                f"Duplicate record: {rec.arrival_flight}/{rec.departure_flight} "
                f"eff={rec.effective_date} frq={rec.frequency}", "warning"
            ))
        seen.add(key)

    return errors


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _date_sort_key(ddmmyyyy: str) -> str:
    """Convert DDMMYYYY to YYYYMMDD for lexicographic date comparison."""
    return ddmmyyyy[4:8] + ddmmyyyy[2:4] + ddmmyyyy[0:2]


def _validate_date_range(
    row: int, field: str, ddmmyyyy: str, errors: List[ValidationError]
) -> None:
    try:
        day = int(ddmmyyyy[0:2])
        mon = int(ddmmyyyy[2:4])
        yr = int(ddmmyyyy[4:8])
        if not (1 <= day <= 31 and 1 <= mon <= 12 and 2020 <= yr <= 2040):
            errors.append(ValidationError(
                row, field, f"Date out of plausible range: {ddmmyyyy}", "warning"
            ))
    except ValueError:
        pass
