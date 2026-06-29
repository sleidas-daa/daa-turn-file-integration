"""Parse a schedule file and return preview data without writing output."""
from typing import Any, Dict, List, Optional

from .config import OUTPUT_COLUMNS
from .detection import detect_template
from .processor import PARSERS


def preview_file(
    file_path: str,
    template_override: Optional[str] = None,
    max_rows: int = 100,
) -> Dict[str, Any]:
    """Parse file and return metadata + sample rows for UI preview."""
    if template_override and template_override != "auto":
        template = template_override
        confidence = 1.0
    else:
        template, confidence = detect_template(file_path)

    if template == "unknown" or template not in PARSERS:
        return {
            "ok": False,
            "template": template,
            "confidence": confidence,
            "error": f"Could not identify template. Choose a parser manually.",
            "columns": OUTPUT_COLUMNS,
            "rows": [],
            "record_count": 0,
            "warnings": [],
            "parse_errors": [],
        }

    parser_cls = PARSERS[template]
    if template == "emerald":
        parser = parser_cls(file_path)
    else:
        parser = parser_cls(file_path)

    try:
        records = parser.parse()
    except Exception as exc:
        return {
            "ok": False,
            "template": template,
            "confidence": confidence,
            "error": str(exc),
            "columns": OUTPUT_COLUMNS,
            "rows": [],
            "record_count": 0,
            "warnings": [],
            "parse_errors": parser.parse_errors,
        }

    rows: List[List[Any]] = [rec.to_row() for rec in records[:max_rows]]

    return {
        "ok": True,
        "template": template,
        "confidence": confidence,
        "error": None,
        "columns": OUTPUT_COLUMNS,
        "rows": rows,
        "record_count": len(records),
        "truncated": len(records) > max_rows,
        "warnings": [],
        "parse_errors": parser.parse_errors,
    }
