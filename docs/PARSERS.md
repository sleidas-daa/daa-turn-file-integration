# DAA Turn File Converter — Parser Reference

Each parser is a subclass of `BaseParser` and lives in `src/converter/parsers/`. They all return `List[TurnRecord]`, where each record is one aircraft turn at a configured hub airport. Parser configuration (which airports count as a hub, season dates) is read from `config.py`.

---

## Emerald Airlines parser (`emerald.py`)

### Input format

Emerald provides a wide horizontal grid in `.xlsx` format — often called a "DUB plot". Each column after the first represents one aircraft registration. Rows represent flight legs, grouped into weekday sections. Time values are stored as Excel `time` objects.

### Layout

```
ROW 1–5   Blank / header preamble (variable; parser scans for the marker row)
ROW n     Header row: column A = 'DAY', subsequent columns = aircraft codes
          e.g.  DAY | EAI AT7 FAT | EAI ATR | ...
ROW n+1   Blank spacer
ROW n+2   Weekday section start: "Monday 13JUL26" or "Monday13JUL26"
ROW n+3+  Flight leg rows for that weekday:
          col A = blank (inherited day)
          col B = flight number  (e.g. "EI 3221")
          col C = departure airport
          col D = departure time  (Excel time)
          col E = arrival airport
          col F = arrival time    (Excel time)
          col G = blank
ROW m     Blank spacer before next weekday section
```

### Parsing steps

1. **Find the header row** — scan column A for the value matching `config.EMERALD_HEADER_MARKER` (default: `"DAY"`).
2. **Identify aircraft columns** — starting from column B, each non-blank cell in the header row is an aircraft.
3. **Split into weekday sections** — each cell in column A that matches `"Monday"`, `"Tuesday"`, ... starts a new section. The day number (1=Mon … 7=Sun) is derived from the day name.
4. **Collect legs** — for each aircraft column and each weekday section, read `flight`, `dep_apt`, `dep_time`, `arr_apt`, `arr_time`, `day_num`.
5. **Build turns** — see matching logic below.

### Turn matching

Emerald legs are ordered chronologically within each aircraft column across all weekdays. The parser scans consecutive pairs `(leg[i], leg[i+1])`:

```
If leg[i].arr_apt == leg[i+1].dep_apt  AND  leg[i].arr_apt is a hub airport:
    → This is a turn: aircraft arrives at the hub and departs on leg[i+1].
```

The wrap `(i+1) % n` handles the week boundary so the last leg of Sunday pairs with the first leg of Monday.

### Overnight calculation

```python
overnight = (departure_day_num - arrival_day_num) % 7
```

| Arrival day | Departure day | overnight |
|-------------|--------------|-----------|
| Monday (1)  | Monday (1)   | 0         |
| Monday (1)  | Tuesday (2)  | 1         |
| Monday (1)  | Thursday (4) | 3         |
| Friday (5)  | Sunday (7)   | 2         |
| Friday (5)  | Monday (1)   | 3         |
| Tuesday (2) | Monday (1)   | 6         |

Values `> 1` are valid (multi-night hub sit) and trigger a warning if `WARN_OVERNIGHT_GT_1 = True` in config.

### Effective and discontinue dates

Emerald plots do not contain date ranges. The parser uses `config.SEASON_EFFECTIVE` and `config.SEASON_DISCONTINUE` as defaults, typically the IATA summer or winter season boundaries.

### Configuration sidecar

If the standard column layout does not match a particular file, a JSON sidecar can be placed alongside the input file:

```
my_plot.xlsx
my_plot.xlsx.emerald.json
```

The sidecar can override header row position, column offsets, home airports, and season dates.

---

## Ryanair parser (`ryanair.py`)

### Input format

Ryanair provides a `.xlsx` file with a header row and one flight turn per row. The file is well-structured and requires minimal transformation.

### Column mapping

| Column | Field          | Notes                                        |
|--------|----------------|----------------------------------------------|
| Apt    | hub filter     | Only rows where Apt is a configured hub are kept |
| AAl    | airline code   | e.g. "FR"                                    |
| AFn    | arrival flight num | combined with AAl to form arrival_flight |
| DAl    | airline code   | typically same as AAl                        |
| DFn    | departure flight num | combined with DAl                      |
| Tst    | bank row flag  | "N" = normal turn; "B" or other = bank, skip |
| Eff    | effective_date | Excel date → DDMMYYYY                        |
| Dsc    | discontinue_date | Excel date → DDMMYYYY                      |
| Frq    | frequency mask | "1......" → "1", "...4..." → "4" etc.        |
| Ovn    | overnight      | Integer from the source file                 |

### Hub filter

Only rows where the `Apt` column matches one of the airports in `config.AIRPORTS["ryanair"]` (default: `["DUB"]`) are processed. Rows for other airports are skipped and recorded in `parse_errors`.

### Frequency parsing

Ryanair uses a 7-character mask like `"...4..."` (dots for inactive days). The parser extracts the digit positions: `"...4..." → "4"`, `"1...5.." → "15"`.

---

## Aer Lingus parser (`aer_lingus.py`)

### Input format

Aer Lingus provides an IATA SSIM (Standard Schedules Information Manual) file in `.txt` format. Each line is a fixed-width record. The system reads **Type-3** records (flight leg records), which start with the character `"3"`.

### SSIM Type-3 field layout (extended EI format)

The live EI SSIM export uses an extended layout that differs from the textbook SSIM spec at two points:

1. Four extra characters at positions 10–13 (leg/operator/service codes) push the date fields to positions 14–27 instead of the standard 10–23.
2. Each airport block carries both a local time and a UTC time, making the departure block 18 characters wide (instead of the standard 9) and the arrival block similarly extended.

The verified 0-indexed field map:

```
Position  Width  Field
──────────────────────────────────────────────────────────────────────
  0         1    Record type ('3' = flight leg)
  1         1    Service indicator (space = scheduled passenger)
  2–4        3    Airline designator (e.g. 'EI ')
  5–8        4    Flight number (right-justified, space-padded; e.g. ' 052')
  9         1    Itinerary variation identifier
 10–13       4    Extra fields (leg number, service type, operator code)
 14–20       7    Effective date FROM  (DDMMMYY, e.g. '31OCT23')
 21–27       7    Effective date TO    (DDMMMYY)
 28–34       7    Days of operation    (7-char mask, e.g. '  3    ' = Wed)
 35          1    Frequency rate
 36–38       3    Departure airport (IATA 3-letter)
 39–42       4    Scheduled departure time — local (HHMM)
 43–46       4    Scheduled departure time — UTC   (HHMM)
 47–51       5    UTC variation at departure (e.g. '+0000', '+0100')
 52–53       2    Pad / terminal prefix
 54–56       3    Arrival airport (IATA 3-letter)
 57–60       4    Scheduled arrival time — local  (HHMM)
 61–64       4    Scheduled arrival time — UTC    (HHMM)
 65–69       5    UTC variation at arrival
──────────────────────────────────────────────────────────────────────
```

### Flight number convention

The 4-character flight number field is **not** stripped of leading zeros. `EI052` is the published identifier and is different from `EI52`. The parser preserves the raw field content after outer whitespace removal only.

### Date format conversion

SSIM dates are in `DDMMMYY` format (e.g. `31OCT23`). The parser converts them to `DDMMYYYY` (e.g. `31102023`) using a fixed month abbreviation table.

### Days-of-operation mask

A 7-character string where position `n-1` contains the digit `n` if the flight operates on day `n`, and a space if it does not.

```
'1234567' → all days
'  3    ' → Wednesday only
'1  45  ' → Monday, Thursday, Friday
```

The parser collapses this to a compact string of active digits: `'  3    ' → '3'`.

### Turn matching — time-based greedy sweep

The SSIM contains individual flight legs. A "turn" is an inbound leg that arrives at a hub airport paired with the next available outbound leg that departs from the same hub.

**Algorithm:**

1. Separate all legs into **arrivals** (arr_apt is a hub) and **departures** (dep_apt is a hub).
2. Index departures by operating date.
3. Sort arrivals by `(operating_date, arrival_time)`.
4. For each arrival (earliest first):
   - Find the first unmatched departure on the same date whose `dep_time > arr_time` → `overnight = 0`.
   - If none, find the first unmatched departure on the next calendar date → `overnight = 1`.
   - If still none, the arrival is unmatched (unusual; logged in `parse_errors`).
5. Mark the matched departure as used so it cannot be assigned to a second arrival.

**Why greedy?** On a busy day, many flights land at DUB. Each one departs again on a different aircraft slot. Greedy-by-arrival-time ensures the earliest-arriving aircraft gets the earliest-departing slot, which reflects how slots are actually allocated and avoids over-counting.

**Why time-based rather than flight-number adjacency?** The flight number `n+1` heuristic (pair EI052 with EI053) only works for symmetric route pairs and breaks for code-shares, charter supplements, and multi-stop itineraries. Time-based matching works for any inbound/outbound combination.

### Hub airport scope

`config.AIRPORTS["aer_lingus"]` lists the hub airports the parser considers (default: `["DUB"]`). Legs connecting exclusively through non-hub airports are ignored.

---

## Output record format

All three parsers produce `TurnRecord` objects with the same six fields:

| Field             | Type | Format     | Example          |
|-------------------|------|------------|------------------|
| arrival_flight    | str  | IATA code  | `EI3409`         |
| departure_flight  | str  | IATA code  | `EI3550`         |
| overnight         | int  | 0–6        | `3`              |
| effective_date    | str  | DDMMYYYY   | `29032026`       |
| discontinue_date  | str  | DDMMYYYY   | `24102026`       |
| frequency         | str  | 1–7 digit(s) | `1`, `245`, `1234567` |

The exporter writes these in column order, no header, comma-separated.
