"""
Auto-detect which parser template should be used for a given input file.

Why auto-detection?
-------------------
Operations staff drop files from several different airlines into the queue
folder without necessarily naming them consistently.  The detector inspects
the filename, file extension, and (for non-txt files) the first few rows of
the file to decide the most likely parser.  This means the common workflow
requires zero configuration: just drop the file in and it works.

Scoring system
--------------
Each template starts with a score of 0.0.  Points are added for:
  - Filename keyword match       (+0.4)
  - Extension heuristic          (+0.3 for .txt → Aer Lingus)
  - Content inspection match     (+0.3 – 0.6 depending on certainty)

The highest-scoring template is selected.  If the best score is below the
0.2 threshold the file is returned as 'unknown' so the caller can prompt
the user to specify a template explicitly via --template.

Confidence is capped at 1.0 and rounded to 2 decimal places.
"""
import re
from pathlib import Path
from typing import Tuple, Optional

import openpyxl
import pandas as pd


# (template_name, confidence 0-1)
DetectionResult = Tuple[str, float]

# Keyword sets for filename-based scoring.
# Lowercased and space-stripped before comparison.
RYANAIR_KEYWORDS = {"ryanair", "fr s26", "ryan", "fr ac", "fr_s26"}
EMERALD_KEYWORDS = {"emerald", "eai", "dub plot", "dub_plot"}
AER_LINGUS_KEYWORDS = {"aerlingus", "aer lingus", "ei ssim", "ei_s26", "ssim"}

# Ryanair Excel files always have these column headers in the first row.
# We check how many are present: 6+ → high confidence, 3+ → medium.
RYANAIR_REQUIRED_COLS = {"AAl", "AFn", "DAl", "DFn", "Frq", "Eff", "Dsc", "Ovn"}

# Emerald plots are identified by the string 'DAY' appearing in the first
# column of the header row.
EMERALD_HEADER_MARKER = "DAY"


def detect_template(file_path: str) -> DetectionResult:
    """Return (template_name, confidence) for a file.

    template_name: 'ryanair' | 'emerald' | 'aer_lingus' | 'unknown'
    confidence: 0.0 – 1.0

    Callers should treat 'unknown' as a signal to ask the user for the
    template rather than attempting to parse with a guess.
    """
    path = Path(file_path)
    # Strip spaces so "dub plot" and "dubplot" match the same keyword
    name_lower = path.stem.lower().replace(" ", "")
    ext = path.suffix.lower()

    scores: dict[str, float] = {"ryanair": 0.0, "emerald": 0.0, "aer_lingus": 0.0}

    # --- Step 1: filename keyword heuristics ---
    # Each keyword set is checked independently; only one bonus per template
    # is awarded per keyword category (break after the first match).
    for kw in RYANAIR_KEYWORDS:
        if kw.replace(" ", "") in name_lower:
            scores["ryanair"] += 0.4
            break
    for kw in EMERALD_KEYWORDS:
        if kw.replace(" ", "") in name_lower:
            scores["emerald"] += 0.4
            break
    for kw in AER_LINGUS_KEYWORDS:
        if kw.replace(" ", "") in name_lower:
            scores["aer_lingus"] += 0.4
            break

    # --- Step 2: extension heuristics ---
    # Only Aer Lingus delivers .txt files; Ryanair and Emerald use .xlsx.
    # We don't add extension points for xlsx because both Ryanair and Emerald
    # use it — content inspection is more reliable there.
    if ext == ".txt":
        scores["aer_lingus"] += 0.3

    # --- Step 3: content inspection ---
    # Reading file contents is more expensive than filename/extension checks,
    # so this step runs last after the cheap checks have narrowed the field.
    if ext in (".xlsx", ".xls"):
        template, content_conf = _inspect_excel(file_path)
        if template:
            scores[template] = min(1.0, scores[template] + content_conf)
    elif ext == ".csv":
        template, content_conf = _inspect_csv(file_path)
        if template:
            scores[template] = min(1.0, scores[template] + content_conf)
    elif ext == ".txt":
        template, content_conf = _inspect_txt(file_path)
        if template:
            scores[template] = min(1.0, scores[template] + content_conf)

    best = max(scores, key=lambda k: scores[k])
    best_score = scores[best]

    # Score < 0.2 means we couldn't identify anything meaningful.
    # Return 'unknown' so the caller knows to ask the user rather than guessing.
    if best_score < 0.2:
        return ("unknown", 0.0)

    return (best, round(min(best_score, 1.0), 2))


def _inspect_excel(file_path: str) -> Tuple[Optional[str], float]:
    """Check the first ~10 rows of an Excel file for recognisable structure.

    Ryanair: first row contains known column names (AAl, AFn, etc.).
    Emerald: contains a cell with the string 'DAY', or a weekday name
             followed by a date (e.g. 'Monday 13JUL26').
    """
    try:
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active

        # Sample first 10 rows only — we don't need to read the whole file
        rows = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            rows.append(row)
            if i >= 9:
                break
        wb.close()

        # Ryanair: first row has column headers matching known set
        if rows:
            first_row_values = {str(v).strip() for v in rows[0] if v is not None}
            overlap = first_row_values & RYANAIR_REQUIRED_COLS
            if len(overlap) >= 6:
                return ("ryanair", 0.6)   # strong match: nearly all expected columns found
            if len(overlap) >= 3:
                return ("ryanair", 0.3)   # partial match

        # Emerald: look for the 'DAY' header marker or weekday names in any cell
        for row in rows:
            for cell in row:
                if str(cell).strip().upper() == EMERALD_HEADER_MARKER:
                    return ("emerald", 0.5)
                # Day-section headers look like "Monday 13JUL26" — their presence
                # strongly implies an Emerald plot layout
                if isinstance(cell, str) and re.match(
                    r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
                    r"(?:\s*\d|\b)",
                    cell.strip(),
                    re.IGNORECASE,
                ):
                    return ("emerald", 0.4)

    except Exception:
        # Corrupted or encrypted files: skip content check, rely on filename/ext
        pass
    return (None, 0.0)


def _inspect_csv(file_path: str) -> Tuple[Optional[str], float]:
    """Check a CSV file for Ryanair column headers.

    We only check CSV against Ryanair because Emerald and Aer Lingus do not
    deliver CSV files.
    """
    try:
        df = pd.read_csv(file_path, nrows=3)
        cols = set(df.columns.tolist())
        overlap = cols & RYANAIR_REQUIRED_COLS
        if len(overlap) >= 4:
            return ("ryanair", 0.5)
    except Exception:
        pass
    return (None, 0.0)


def _inspect_txt(file_path: str) -> Tuple[Optional[str], float]:
    """Check a text file for SSIM Type-3 records (Aer Lingus format).

    SSIM files begin with a Type-1 header line and contain Type-3 flight
    leg records, each starting with '3' followed by a service-type character.
    We only read the first 2 KB to keep detection fast on large SSIM files.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            head = f.read(2000)

        # Type-3 records: '3' followed immediately by a capital letter or space.
        # This pattern appears hundreds of times in a real SSIM file.
        if re.search(r"^3[A-Z ]", head, re.MULTILINE):
            return ("aer_lingus", 0.5)

        # SSIM files also contain a Type-1 header line or the word 'SSIM'
        if "SSIM" in head.upper() or re.search(r"^1[A-Z ]", head, re.MULTILINE):
            return ("aer_lingus", 0.4)

    except Exception:
        pass
    return (None, 0.0)
