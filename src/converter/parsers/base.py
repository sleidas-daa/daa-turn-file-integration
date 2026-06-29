"""
Abstract base class for all airline schedule parsers.
Useful for future templates
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List

from ..dataclasses import TurnRecord


class BaseParser(ABC):
    """All parsers must implement parse() and return a list of TurnRecord."""

    template_name: str = "unknown"

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"Input file not found: {file_path}")
        # Populated during parse() with dicts: {row, field, reason} for rows
        # that could not produce a valid TurnRecord (bank rows, filter exclusions…)
        self.parse_errors: List[Dict[str, Any]] = []

    @abstractmethod
    def parse(self) -> List[TurnRecord]:
        """Parse the file and return normalised TurnRecord objects."""

    def _require_columns(self, df_columns: list, required: set) -> None:
        missing = required - set(df_columns)
        if missing:
            raise ValueError(
                f"[{self.template_name}] Missing required columns: {sorted(missing)}"
            )
