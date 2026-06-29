"""Emerald DUB plot layout discovery and user-overridable mapping config.

A sidecar file next to the input (``<plot>.emerald.json``) or an explicit
``--config`` path lets users adjust layout when a new variant drifts without
waiting for a code change. The same model is intended to drive a future UI.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openpyxl

from .. import config
from ..config import SEASON_DISCONTINUE, SEASON_EFFECTIVE
from ..normalizer import parse_emerald_day_header

SIDECAR_SUFFIX = ".emerald.json"


@dataclass
class EmeraldLayoutConfig:
    """Column/row mapping for an Emerald DUB aircraft plot."""

    day_column: int = 0
    header_marker: str = "DAY"
    aircraft_prefix: str = "EAI"
    group_width: int = 6
    flight_offset: int = 0
    from_offset: int = 1
    to_offset: int = 3
    expected_days: int = 7
    effective_date: Optional[str] = None
    discontinue_date: Optional[str] = None
    home_airports: List[str] = field(
        default_factory=lambda: list(config.AIRPORTS.get("emerald", ["DUB"]))
    )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmeraldLayoutConfig":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def effective_date_value(self) -> str:
        return self.effective_date or SEASON_EFFECTIVE

    def discontinue_date_value(self) -> str:
        return self.discontinue_date or SEASON_DISCONTINUE

    def home_airport_set(self) -> set[str]:
        return {a.strip().upper() for a in self.home_airports if a.strip()}


def sidecar_path_for(file_path: str | Path) -> Path:
    path = Path(file_path)
    return path.with_name(path.name + SIDECAR_SUFFIX)


def load_emerald_config(
    file_path: str | Path,
    config_path: Optional[str | Path] = None,
) -> EmeraldLayoutConfig:
    """Load sidecar config if present; otherwise return defaults."""
    candidates: List[Path] = []
    if config_path:
        candidates.append(Path(config_path))
    candidates.append(sidecar_path_for(file_path))

    for path in candidates:
        if path.is_file():
            with open(path, encoding="utf-8") as f:
                return EmeraldLayoutConfig.from_dict(json.load(f))
    return EmeraldLayoutConfig()


def save_emerald_config(config: EmeraldLayoutConfig, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2)
        f.write("\n")
    return out


def inspect_emerald_layout(
    file_path: str | Path,
    layout: Optional[EmeraldLayoutConfig] = None,
) -> Dict[str, Any]:
    """Scan a plot file and return discovered structure (for CLI / future UI)."""
    layout = layout or EmeraldLayoutConfig()
    path = Path(file_path)
    if not path.is_file():
        return {
            "file": str(path),
            "parseable": False,
            "error": f"File not found: {path}",
            "config": layout.to_dict(),
        }

    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    all_rows = [tuple(row) for row in ws.iter_rows(values_only=True)]
    wb.close()

    warnings: List[str] = []
    header_row_idx = _find_header_row(all_rows, layout.header_marker)
    if header_row_idx is None:
        return {
            "file": str(path),
            "parseable": False,
            "error": f"No header row with '{layout.header_marker}' in column {layout.day_column}",
            "config": layout.to_dict(),
        }

    aircraft_cols = _find_aircraft_columns(all_rows[header_row_idx], layout)
    day_sections = _parse_day_sections(all_rows, header_row_idx + 1, layout.day_column)

    if not aircraft_cols:
        warnings.append("No aircraft columns found — check aircraft_prefix or header row")
    if len(day_sections) != layout.expected_days:
        warnings.append(
            f"Found {len(day_sections)} day section(s), expected {layout.expected_days}"
        )

    empty_aircraft = [
        name for col_idx, name in aircraft_cols
        if _count_legs(day_sections, col_idx, layout) == 0
    ]
    if empty_aircraft:
        warnings.append(
            f"{len(empty_aircraft)} aircraft column(s) have no legs: "
            + ", ".join(empty_aircraft[:5])
            + (" …" if len(empty_aircraft) > 5 else "")
        )

    return {
        "file": str(path),
        "parseable": bool(aircraft_cols and day_sections),
        "header_row": header_row_idx + 1,
        "aircraft_count": len(aircraft_cols),
        "aircraft_columns": [
            {"column": idx + 1, "index": idx, "name": name}
            for idx, name in aircraft_cols
        ],
        "day_sections": [
            {
                "row": rows[0][0] if rows else None,
                "ops_day": day_num,
                "leg_rows": len(rows),
            }
            for day_num, rows in day_sections
        ],
        "warnings": warnings,
        "config": layout.to_dict(),
        "sidecar_path": str(sidecar_path_for(path)),
    }


def validate_emerald_structure(
    aircraft_cols: List[Tuple[int, str]],
    day_sections: List[Tuple[int, list]],
    layout: EmeraldLayoutConfig,
) -> List[Dict[str, Any]]:
    """Return parse_errors-style dicts for structural problems."""
    issues: List[Dict[str, Any]] = []

    if not aircraft_cols:
        issues.append({
            "row": None,
            "field": "aircraft_columns",
            "reason": (
                f"No aircraft columns matching prefix '{layout.aircraft_prefix}'. "
                f"Add a sidecar config ({SIDECAR_SUFFIX}) to override mapping."
            ),
        })
    if not day_sections:
        issues.append({
            "row": None,
            "field": "day_sections",
            "reason": "No day sections found in column 0 — check day_column in config",
        })
    elif len(day_sections) != layout.expected_days:
        issues.append({
            "row": None,
            "field": "day_sections",
            "reason": (
                f"Expected {layout.expected_days} day sections, found {len(day_sections)}. "
                "Output may be incomplete — verify or adjust expected_days."
            ),
        })

    for col_idx, name in aircraft_cols:
        if _count_legs(day_sections, col_idx, layout) == 0:
            issues.append({
                "row": None,
                "field": "aircraft_columns",
                "reason": f"Aircraft '{name}' (column {col_idx + 1}) has no legs",
            })

    return issues


def _find_header_row(rows: list, marker: str) -> Optional[int]:
    target = marker.strip().upper()
    for i, row in enumerate(rows):
        if not row or len(row) <= 0:
            continue
        cell = row[0]
        if cell and str(cell).strip().upper() == target:
            return i
    return None


def _find_aircraft_columns(
    header_row: tuple,
    layout: EmeraldLayoutConfig,
) -> List[Tuple[int, str]]:
    prefix = layout.aircraft_prefix.strip().upper()
    prefixed = [
        (i, str(cell).strip())
        for i, cell in enumerate(header_row)
        if cell and str(cell).strip().upper().startswith(prefix)
    ]
    if prefixed:
        return prefixed

    result: List[Tuple[int, str]] = []
    gw = layout.group_width
    for i, cell in enumerate(header_row):
        if cell and str(cell).strip().upper() == layout.header_marker.upper():
            continue
        if cell and str(cell).strip():
            val = str(cell).strip()
            if i > 0 and (i % gw == 1 or i % gw == 0):
                result.append((i, val))
            elif i > 0 and not result:
                result.append((i, val))
    return result


def _parse_day_sections(
    rows: list,
    start_idx: int,
    day_column: int,
) -> List[Tuple[int, list]]:
    sections: List[Tuple[int, list]] = []
    current_day_num: Optional[int] = None
    current_rows: List[tuple] = []

    for row in rows[start_idx:]:
        col_val = row[day_column] if row and len(row) > day_column else None
        parsed = parse_emerald_day_header(col_val) if col_val else None

        if parsed:
            if current_day_num is not None and current_rows:
                sections.append((current_day_num, current_rows))
            _, _, current_day_num = parsed
            current_rows = [row]
        elif current_day_num is not None:
            current_rows.append(row)

    if current_day_num is not None and current_rows:
        sections.append((current_day_num, current_rows))

    return sections


def _count_legs(
    day_sections: List[Tuple[int, list]],
    col_start: int,
    layout: EmeraldLayoutConfig,
) -> int:
    count = 0
    from_off = layout.from_offset
    to_off = layout.to_offset
    flight_off = layout.flight_offset

    for _, rows in day_sections:
        for row in rows:
            if len(row) <= col_start + max(flight_off, from_off, to_off):
                continue
            flight = row[col_start + flight_off]
            from_apt = row[col_start + from_off]
            to_apt = row[col_start + to_off]
            if flight and isinstance(flight, str) and from_apt and to_apt:
                count += 1
    return count
