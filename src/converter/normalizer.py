"""Pure functions for normalising dates, flight numbers, and frequency masks."""
import re
from datetime import date, datetime
from typing import Union


def normalize_date(value: Union[str, datetime, date, None]) -> str:
    """Convert various date representations to DDMMYYYY (zero-padded, 8 digits)."""
    if value is None:
        raise ValueError("Date value is None")

    if isinstance(value, (datetime, date)):
        return value.strftime("%d%m%Y")

    s = str(value).strip()

    # Already DDMMYYYY (8 digits, no separators)
    if re.fullmatch(r"\d{8}", s):
        return s

    # Pandas / ISO: YYYY-MM-DD
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})(?:\s.*)?", s)
    if m:
        return f"{m.group(3)}{m.group(2)}{m.group(1)}"

    # DD/MM/YYYY or DD-MM-YYYY
    m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s)
    if m:
        return f"{int(m.group(1)):02d}{int(m.group(2)):02d}{m.group(3)}"

    # DDMonYY  e.g. 13JUL26
    months = {
        "JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
        "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
        "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12",
    }
    m = re.fullmatch(r"(\d{1,2})([A-Za-z]{3})(\d{2,4})", s)
    if m:
        day = int(m.group(1))
        mon = m.group(2).upper()
        yr = m.group(3)
        if len(yr) == 2:
            yr = "20" + yr
        return f"{day:02d}{months[mon]}{yr}"

    raise ValueError(f"Unrecognised date format: {s!r}")


def normalize_flight_number(airline_code: str, flight_num: Union[str, float, int]) -> str:
    """Merge airline code + flight number, stripping leading zeros.

    FR + 011 -> FR11
    FR + 10  -> FR10
    EI + 3221 -> EI3221
    """
    code = str(airline_code).strip().upper()
    num = str(int(float(str(flight_num)))).strip()
    return f"{code}{num}"


def normalize_emerald_flight(raw: str) -> str:
    """Convert 'EI 3221' -> 'EI3221' (remove internal spaces)."""
    return re.sub(r"\s+", "", str(raw).strip()).upper()


def normalize_frequency_mask(mask: str) -> str:
    """Extract operating day digits from a 7-character frequency mask.

    '...4...' -> '4'
    '1......' -> '1'
    '..34...' -> '34'
    '1...5..' -> '15'
    '......7' -> '7'
    """
    if not mask:
        raise ValueError("Empty frequency mask")
    return "".join(c for c in mask if c not in (".", " ", "-"))


_EMERALD_WEEKDAYS = {
    "monday": 1,
    "tuesday": 2,
    "wednesday": 3,
    "thursday": 4,
    "friday": 5,
    "saturday": 6,
    "sunday": 7,
}

_EMERALD_MONTHS = {
    "JAN": "01",
    "FEB": "02",
    "MAR": "03",
    "APR": "04",
    "MAY": "05",
    "JUN": "06",
    "JUL": "07",
    "AUG": "08",
    "SEP": "09",
    "OCT": "10",
    "NOV": "11",
    "DEC": "12",
}


def parse_emerald_day_header(text: str):
    """Parse Emerald day row labels into (day_name, date_str_DDMMYYYY, day_number 1-7).

    Accepts common layout drift, e.g. ``Monday 13JUL26``, ``Monday13JUL26``,
    or weekday-only headers such as ``Monday``.

    Returns None if text is not a day header.
    """
    if not isinstance(text, str):
        return None
    text = text.strip()
    if not text:
        return None

    m = re.match(
        r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
        r"\s*(\d{1,2})([A-Za-z]{3})(\d{2,4})",
        text,
        re.IGNORECASE,
    )
    if m:
        day_name = m.group(1).lower()
        day_num = _EMERALD_WEEKDAYS[day_name]
        day = int(m.group(2))
        mon_str = m.group(3).upper()
        yr = m.group(4)
        if len(yr) == 2:
            yr = "20" + yr
        date_str = f"{day:02d}{_EMERALD_MONTHS[mon_str]}{yr}"
        return (day_name.capitalize(), date_str, day_num)

    m = re.match(
        r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b",
        text,
        re.IGNORECASE,
    )
    if m:
        day_name = m.group(1).lower()
        return (day_name.capitalize(), None, _EMERALD_WEEKDAYS[day_name])

    return None
