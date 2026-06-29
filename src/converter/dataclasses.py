"""
Core data classes for the DAA Turn File Converter.

TurnRecord     — one row in an AOS-compatible output CSV.
ValidationError — a single validation finding attached to a record or file.
JobRecord      — lifecycle state for one queued processing job.

These are plain Python dataclasses (no ORM, no serialisation framework) so
that parsers, validators, exporters, and the UI layer can all share them
without pulling in unnecessary dependencies.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class TurnRecord:
    """
    One aircraft turn at a hub airport, ready for import into AOS.

    Fields mirror the six columns of the output CSV exactly.
    overnight — number of nights the aircraft stays at the hub between the
                arrival and the subsequent departure.  0 = same-day turn,
                1 = one overnight, etc.  Values > 1 are valid but unusual and
                will trigger a warning unless WARN_OVERNIGHT_GT_1 is False.
    frequency — IATA weekday digit(s) (1=Mon … 7=Sun) on which the turn
                operates.  Single digit for a specific day, multiple digits
                for a multi-day operation.
    """

    arrival_flight: str
    departure_flight: str
    overnight: int        # non-negative integer
    effective_date: str   # DDMMYYYY
    discontinue_date: str # DDMMYYYY
    frequency: str        # e.g. "4", "26", "1234567"

    def to_row(self) -> List:
        """Return fields in output-column order for CSV writing."""
        return [
            self.arrival_flight,
            self.departure_flight,
            self.overnight,
            self.effective_date,
            self.discontinue_date,
            self.frequency,
        ]


@dataclass
class ValidationError:
    """A single validation finding linked to an optional row number."""

    row_index: Optional[int]
    field: str
    message: str
    severity: str = "error"  # "error" or "warning"


@dataclass
class JobRecord:
    """
    Tracks state for one file through the queue → processing → output pipeline.

    Stored as JSON in the queue state file and passed between the processor,
    reporter, and UI layer.  to_dict / from_dict provide stable serialisation
    without a full ORM.
    """

    id: str
    file_name: str
    file_path: str
    file_size: int
    detected_template: str = ""
    confidence: float = 0.0
    processing_status: str = "queued"   # queued | processing | completed | failed
    timestamp: str = ""
    validation_status: str = "pending"  # pending | passed | failed
    output_file_path: str = ""
    report_path: str = ""
    records_parsed: int = 0
    records_ok: int = 0
    records_rejected: int = 0
    processing_duration_s: float = 0.0
    error_messages: List[str] = field(default_factory=list)
    validation_errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "file_name": self.file_name,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "detected_template": self.detected_template,
            "confidence": self.confidence,
            "processing_status": self.processing_status,
            "timestamp": self.timestamp,
            "validation_status": self.validation_status,
            "output_file_path": self.output_file_path,
            "report_path": self.report_path,
            "records_parsed": self.records_parsed,
            "records_ok": self.records_ok,
            "records_rejected": self.records_rejected,
            "processing_duration_s": self.processing_duration_s,
            "error_messages": self.error_messages,
            "validation_errors": self.validation_errors,
            "warnings": self.warnings,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "JobRecord":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
