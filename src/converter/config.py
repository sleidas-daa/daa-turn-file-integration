"""
Central configuration for the DAA Turn File Converter.

All runtime behaviour — paths, output formatting, warnings, airport scope, and
testing toggles — is controlled from this single file.  Parsers and processors
import what they need; no magic numbers should appear elsewhere in the codebase.
"""
from pathlib import Path

# ===========================================================================
# Paths
# ===========================================================================

ROOT_DIR = Path(__file__).parent.parent.parent
QUEUE_DIR = ROOT_DIR / "queue"
OUTPUT_DIR = ROOT_DIR / "output"
REPORTS_DIR = ROOT_DIR / "reports"
STAGING_DIR = ROOT_DIR / "staging"
QUEUE_STATE_FILE = QUEUE_DIR / ".queue_state.json"

# ===========================================================================
# Supported input file extensions
# ===========================================================================

SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".csv", ".txt"}

# ===========================================================================
# Season date defaults
# These are used when a source file does not supply its own date range.
# Format: DDMMYYYY (zero-padded day and month)
# ===========================================================================

# IATA S26 season: 29 March 2026 – 24 October 2026
SEASON_EFFECTIVE = "29032026"
SEASON_DISCONTINUE = "24102026"

# ===========================================================================
# Airport scope
# Each parser will only build turns that connect THROUGH one of its listed
# airports.  Edit the list for the relevant parser to add or remove scope.
# "DUB" (Dublin) is the default hub for all parsers.
# "ORK" (Cork) is included for Emerald because they operate Cork turns.
# ===========================================================================

AIRPORTS = {
    "emerald": ["DUB", "ORK"],   # Emerald Airlines: Dublin + Cork
    "ryanair": ["DUB"],           # Ryanair: Dublin only
    "aer_lingus": ["DUB"],        # Aer Lingus: Dublin only
}

# Convenience alias — the primary hub used in single-hub contexts
DEFAULT_HUB = "DUB"

# ===========================================================================
# Output formatting
#
# Both options below are DEBUG/DIAGNOSTIC aids and are disabled by default.
# Enabling them changes the CSV in ways that AOS does not expect.
# ===========================================================================

# Add a column-header row as the first line of every output CSV.
# AOS expects headerless files; enable only for manual inspection.
INCLUDE_HEADER_ROW = False

# Replace genuinely empty/absent fields with the string below.
# Helps spot data gaps during manual review; leave False for production.
FILL_MISSING_WITH_PLACEHOLDER = False
MISSING_PLACEHOLDER = "MISSING"

# ===========================================================================
# Warning controls
# Warnings appear in the per-job report file and in job.warnings.
# Disabling a warning here suppresses it system-wide.
# ===========================================================================

# Emit a warning when an overnight value is greater than 1.
# Overnights > 1 are unusual but can be legitimate (e.g. an aircraft that
# sits at the hub for several days between operations).
# Set to False if high overnight values are expected and reviewed elsewhere.
WARN_OVERNIGHT_GT_1 = True

# Emit a warning when the parser encounters a leg that connects through an
# airport NOT in the parser's AIRPORTS list.
# Useful for auditing scope, but generates noise in busy files — off by default.
WARN_NON_HUB_AIRPORT = False

# ===========================================================================
# Testing
# Setting ENABLE_TESTS to False instructs conftest.py to skip every collected
# test.  This is provided as a last-resort escape hatch only — leaving tests
# disabled means regressions will go undetected.
# ===========================================================================

ENABLE_TESTS = True

# ===========================================================================
# Output column order (used by exporter and CSV header when enabled)
# ===========================================================================

OUTPUT_COLUMNS = [
    "arrival_flight",
    "departure_flight",
    "overnight",
    "effective_date",
    "discontinue_date",
    "frequency",
]
