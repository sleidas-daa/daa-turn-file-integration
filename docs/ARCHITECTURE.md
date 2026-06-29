# DAA Turn File Converter — Architecture

## What this system does

The Turn File Converter reads airline schedule files (Excel plots, SSIM text exports, Ryanair Excel sheets) and produces AOS-compatible turn files: headerless CSV files where each row represents one aircraft turn at a hub airport. A "turn" is an inbound flight landing at the hub, the aircraft overnighting (or not), and the same aircraft departing on a subsequent flight.

These turn files are imported directly into the Airport Operations System (AOS) to drive ground handler planning and resource allocation.

---

## End-to-end data flow

```
INPUT FILE
(xlsx / txt / csv)
       │
       ▼
┌─────────────────┐
│  File Detection │  detection.py
│  (auto-detect   │  Inspects filename, headers, structure to
│   parser type)  │  choose the correct parser with a confidence score.
└────────┬────────┘
         │  template name: "ryanair" | "emerald" | "aer_lingus"
         ▼
┌─────────────────┐
│     Parser      │  parsers/ryanair.py
│  (format-       │  parsers/emerald.py
│   specific)     │  parsers/aer_lingus.py
└────────┬────────┘
         │  List[TurnRecord]
         ▼
┌─────────────────┐
│   Validation    │  validation.py
│  (rules engine) │  Checks field formats, date ordering,
│                 │  overnight range, duplicates.
└────────┬────────┘
         │  List[ValidationError] (errors + warnings)
         ▼
┌─────────────────┐
│    Exporter     │  exporter.py
│  (CSV writer)   │  Writes headerless CSV to output/
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Reporter     │  reporter.py
│  (report file)  │  Writes a text report to reports/ when
│                 │  validation warnings or errors exist.
└────────┬────────┘
         │
         ▼
OUTPUT: output/OUTPUT_<filename>.csv
REPORT: reports/REPORT_<filename>.txt  (only if issues found)
```

The **Processor** (`processor.py`) orchestrates all five stages for a single job. It is the only module that imports from all other modules; parsers, validators, and exporters do not know about each other.

---

## Directory layout

```
project-root/
│
├── src/converter/            Core Python package
│   ├── config.py             ← ALL runtime configuration lives here
│   ├── dataclasses.py        Domain objects: TurnRecord, ValidationError, JobRecord
│   ├── models.py             Backward-compat shim — re-exports from dataclasses.py
│   ├── detection.py          Auto-detects which parser to use
│   ├── processor.py          Orchestrator: detection → parse → validate → export → report
│   ├── validation.py         Rules engine applied after every parse
│   ├── exporter.py           Writes the output CSV
│   ├── reporter.py           Writes the text report file
│   ├── normalizer.py         Field normalisation helpers (flight number cleanup, etc.)
│   ├── preview.py            Generates a quick preview summary of parsed records
│   ├── staging.py            Moves files between queue and staging
│   ├── queue_manager.py      Queue state CRUD backed by .queue_state.json
│   └── parsers/
│       ├── base.py           Abstract BaseParser class (all parsers inherit this)
│       ├── emerald.py        Emerald Airlines: xlsx DUB aircraft plot
│       ├── emerald_layout.py Emerald column/row layout config and helpers
│       ├── ryanair.py        Ryanair: xlsx turn file
│       └── aer_lingus.py     Aer Lingus: IATA SSIM Type-3 text file
│
├── ui/                       FastAPI web server (optional, separate process)
│   ├── server.py             REST endpoints for queue management and job status
│   ├── queue_store.py        In-memory queue state for the API layer
│   ├── security.py           API key and CORS middleware
│   └── static/               Browser front-end (HTML/CSS/JS)
│
├── tests/                    pytest test suite
│   ├── conftest.py           Shared fixtures and session hooks
│   ├── fixtures/             Real reference files used by integration tests
│   └── test_*.py             One test file per module
│
├── queue/                    Drop files here to be processed (watched directory)
├── staging/                  Files move here while being processed
├── output/                   Completed CSV turn files land here
├── reports/                  Per-job validation report files land here
│
├── run.py                    CLI entry point: process one file at a time
├── staging_runner.py         Watches queue/ and auto-processes new files
└── ui_app.py                 Launches the FastAPI web server
```

---

## Key design decisions

### 1. `config.py` is the single source of truth

Every tunable parameter — directory paths, season dates, airport scope, warning toggles, output formatting flags — lives in `src/converter/config.py`. No magic strings or hardcoded paths appear anywhere else in the codebase. Parsers, validators, and the exporter all import from config rather than defining their own defaults.

**Why:** Airlines deliver new schedule files every season. The season dates, active airports, and warning thresholds change regularly. Keeping them in one place means a single edit in `config.py` propagates everywhere without touching parser logic.

### 2. `dataclasses.py` holds all domain objects

`TurnRecord`, `ValidationError`, and `JobRecord` are plain Python dataclasses with no ORM or serialisation framework dependency. `models.py` is a thin re-export shim kept for backward compatibility with any code that still imports from the old location.

**Why:** Plain dataclasses can be shared freely across the parser, validator, exporter, reporter, and UI layers without circular imports. They also serialise trivially to/from JSON via `to_dict()` / `from_dict()`, which is all the queue state file needs.

### 3. Every parser extends `BaseParser`

`BaseParser` enforces a single contract: `parse()` returns `List[TurnRecord]`. It also provides `self.parse_errors` for row-level issues that don't raise (e.g. a blank row in a schedule, which is informational rather than fatal).

**Why:** The processor only needs to know `parser_cls.parse()` — it doesn't care whether the source is an Excel grid or a fixed-width text file. Adding a new airline means writing a new `BaseParser` subclass and registering it in the `PARSERS` dict in `processor.py`.

### 4. Validation is a separate pass after parsing

The parser's job is to extract records faithfully. The validator's job is to find problems. They are deliberately separate so that:
- Parsers can be tested independently of validation rules.
- Validation rules can be changed without touching parser code.
- A future UI can show parse output separately from validation findings.

### 5. Overnight is computed with modular weekday arithmetic

```python
overnight = (departure_day_num - arrival_day_num) % 7
```

IATA weekday numbers are 1 (Monday) through 7 (Sunday). The modulo-7 operation correctly handles the week wrap: an aircraft arriving on Friday (5) and departing on Monday (1) gives `(1 - 5) % 7 = 3`, meaning three nights at the hub.

The old implementation used `int(a.day_num != b.day_num)`, which capped overnight at 1 regardless of the actual gap. This produced wrong values for multi-night aircraft plots.

### 6. AOS output format

The output is a headerless, comma-separated CSV with exactly six columns in this order:

```
arrival_flight, departure_flight, overnight, effective_date, discontinue_date, frequency
```

Example rows:
```
EI3409,EI3550,3,29032026,24102026,1
EI3409,EI3550,2,29032026,24102026,5
```

Dates are in `DDMMYYYY` format. Frequency is an IATA weekday digit (1=Monday, 7=Sunday). AOS will reject files with a header row or extra columns — the `INCLUDE_HEADER_ROW` and `FILL_MISSING_WITH_PLACEHOLDER` flags in config are diagnostic tools only and must not be enabled in production.

### 7. Report files are generated only when needed

`reporter.py` writes a text report only when there is something worth reporting: parse errors, validation warnings or errors, or a job failure. Clean jobs produce no report file, keeping the `reports/` directory meaningful.

---

## Adding a new airline parser

1. Create `src/converter/parsers/<airline>.py` with a class that extends `BaseParser`.
2. Implement `parse() -> List[TurnRecord]`.
3. Register the class in the `PARSERS` dict in `processor.py`.
4. Add an airport scope entry in `config.AIRPORTS`.
5. Add detection logic in `detection.py` so the system can auto-identify files.
6. Write tests in `tests/test_<airline>.py` using a synthetic fixture in `conftest.py`.

---

## Running the system

### Single file (CLI)
```bash
python run.py --file "queue/My Schedule.xlsx"
# or specify the parser explicitly:
python run.py --file "queue/My Schedule.xlsx" --template ryanair
```

### Queue watcher (automated)
```bash
python staging_runner.py
```
Drop files into `queue/`. The runner detects them, moves them through staging, and writes output + report.

### Web UI
```bash
python ui_app.py
# open http://localhost:8000
```
See `docs/WEB_UI_INTEGRATION.md` for full details.

### Tests
```bash
pytest
```
Tests that require specific real-world files are automatically skipped when those files are absent. Set `ENABLE_TESTS = False` in `config.py` only as a last resort — doing so hides regressions.
