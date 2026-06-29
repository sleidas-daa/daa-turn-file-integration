# AOS Schedule Converter

Converts airline schedule files into AOS-compatible turn-sequence CSV files for stand planning and allocation.

## Web UI

```bash
pip install -r requirements.txt
python ui_app.py
```

Open **http://127.0.0.1:8765** — drag & drop files, choose a parser, preview, and convert. Runs locally only (files stay on your machine).

## CLI

```bash
python run.py --file "path/to/schedule.xlsx"
```

Template is auto-detected. Override with `--template ryanair|emerald|aer_lingus`.

### Queue mode

Drop files into `queue/`, then run `python run.py`. Job state is stored in `queue/.queue_state.json`.

### Emerald layout inspection

```bash
python run.py --file "plot.xlsx" --inspect
```

Optional sidecar config: `plot.xlsx.emerald.json` (or `--config path.json`) to override column mapping and season dates.

### Staging validation

Validate pre-parsed AOS CSVs without re-running parsers:

```bash
python staging_runner.py
```

Drop CSVs into `staging/`.

## Output format

Six columns, **no header by default** (use `--with-header` if needed):

```
arrival_flight, departure_flight, overnight, effective_date, discontinue_date, frequency
```

- `overnight`: `0` same-day, `1` overnight
- Dates: `DDMMYYYY`
- `frequency`: ops day digit(s) `1`–`7`

Converted files are written to `output/`. Reports land in `reports/` only when there are errors or warnings.

## Project layout

```
run.py                 CLI entry point
ui_app.py              Web UI (drag-drop queue, preview, convert)
ui/                    FastAPI server + static frontend
staging_runner.py      Staging CSV validator
queue/                 Input drop folder
output/                Converted CSVs
staging/               Pre-parsed CSVs for validation
reports/               Error/warning reports
scripts/emerald.py     Legacy standalone Emerald → Excel exporter
src/converter/         Core library
tests/fixtures/        Committed regression Excel files
```

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

CI runs on push and pull requests to `main` and `testing` (see `.github/workflows/ci.yml`):

| Job | Purpose |
|---|---|
| **test** | pytest + coverage report |
| **SonarQube** | Code quality and coverage upload |
| **Snyk** | Dependency and code (SAST) vulnerability scans |

### CI secrets (GitHub repository settings)

Configure under **Settings → Secrets and variables → Actions**:

| Secret | Used by | Description |
|---|---|---|
| `SONAR_TOKEN` | SonarQube job | Project or org token from SonarCloud / SonarQube |
| `SONAR_HOST_URL` | SonarQube job | e.g. `https://sonarcloud.io` or your internal SonarQube host |
| `SNYK_TOKEN` | Snyk job | Snyk **service account** or API token |

Sonar project key in `sonar-project.properties`: **`daa-internal_daa-turn-file-integration`** (org: `daa-org`). Ensure the SonarQube/SonarCloud project uses the same key.

You can also trigger CI manually: **Actions → CI → Run workflow**.

Add new real airline plot variants under `tests/fixtures/` to lock in layout compatibility.

## Configuration

Edit `src/converter/config.py` for default season dates and paths. Per-file Emerald overrides use `.emerald.json` sidecars — see `src/converter/parsers/emerald_layout.py`.

## Adding a new airline

1. Add `src/converter/parsers/<name>.py` extending `BaseParser`
2. Register in `src/converter/processor.py`
3. Add detection rules in `src/converter/detection.py`
4. Add tests under `tests/`
