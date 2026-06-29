"""Tests for the validation module."""
import pytest
from converter.dataclasses import TurnRecord
from converter.validation import validate_records


def _make_record(**kwargs) -> TurnRecord:
    defaults = dict(
        arrival_flight="FR11",
        departure_flight="FR10",
        overnight=0,
        effective_date="02042026",
        discontinue_date="22102026",
        frequency="4",
    )
    defaults.update(kwargs)
    return TurnRecord(**defaults)


class TestValidation:
    def test_valid_records_no_errors(self):
        records = [_make_record(), _make_record(frequency="1")]
        errors = validate_records(records)
        assert all(e.severity != "error" for e in errors)

    def test_empty_list_produces_warning(self):
        errors = validate_records([])
        assert any(e.severity == "warning" for e in errors)

    def test_missing_arrival_flight(self):
        records = [_make_record(arrival_flight="")]
        errors = validate_records(records)
        assert any(e.field == "arrival_flight" and e.severity == "error" for e in errors)

    def test_missing_departure_flight(self):
        records = [_make_record(departure_flight="")]
        errors = validate_records(records)
        assert any(e.field == "departure_flight" and e.severity == "error" for e in errors)

    def test_overnight_greater_than_1_is_warning(self):
        """overnight > 1 is permitted but flagged as a warning, not an error."""
        records = [_make_record(overnight=2)]
        errors = validate_records(records)
        assert not any(e.field == "overnight" and e.severity == "error" for e in errors)
        assert any(e.field == "overnight" and e.severity == "warning" for e in errors)

    def test_overnight_negative_is_error(self):
        """Negative overnight values are always an error."""
        records = [_make_record(overnight=-1)]
        errors = validate_records(records)
        assert any(e.field == "overnight" and e.severity == "error" for e in errors)

    def test_invalid_date_format(self):
        records = [_make_record(effective_date="2026-04-02")]
        errors = validate_records(records)
        assert any(e.field == "effective_date" and e.severity == "error" for e in errors)

    def test_effective_after_discontinue(self):
        records = [_make_record(effective_date="22102026", discontinue_date="02042026")]
        errors = validate_records(records)
        assert any(e.field == "effective_date" and e.severity == "error" for e in errors)

    def test_invalid_frequency_chars(self):
        records = [_make_record(frequency="8")]
        errors = validate_records(records)
        assert any(e.field == "frequency" and e.severity == "error" for e in errors)

    def test_duplicate_records_flagged_as_warning(self):
        rec = _make_record()
        errors = validate_records([rec, rec])
        assert any(e.severity == "warning" and "Duplicate" in e.message for e in errors)

    def test_non_standard_flight_number_is_warning(self):
        records = [_make_record(arrival_flight="UNKNOWN")]
        errors = validate_records(records)
        assert any(e.field == "arrival_flight" and e.severity == "warning" for e in errors)

    def test_overnight_1_is_valid(self):
        records = [_make_record(overnight=1)]
        errors = validate_records(records)
        assert all(e.field != "overnight" or e.severity != "error" for e in errors)

    def test_frequency_multiple_days(self):
        records = [_make_record(frequency="15")]
        errors = validate_records(records)
        assert all(e.field != "frequency" or e.severity != "error" for e in errors)
