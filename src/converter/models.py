"""
Backward-compatibility shim — re-exports everything from dataclasses.py.

New code should import directly from converter.dataclasses.
This module exists so that any external scripts or tests that still reference
converter.models continue to work without modification.
"""
from .dataclasses import JobRecord, TurnRecord, ValidationError  # noqa: F401

__all__ = ["TurnRecord", "ValidationError", "JobRecord"]
