"""Unit tests for normalizer functions."""
import pytest
from datetime import date, datetime

from converter.normalizer import (
    normalize_date,
    normalize_flight_number,
    normalize_emerald_flight,
    normalize_frequency_mask,
    parse_emerald_day_header,
)


class TestNormalizeDate:
    def test_datetime_object(self):
        assert normalize_date(datetime(2026, 4, 2)) == "02042026"

    def test_date_object(self):
        assert normalize_date(date(2026, 3, 30)) == "30032026"

    def test_iso_string(self):
        assert normalize_date("2026-04-02") == "02042026"

    def test_iso_string_leading_zero(self):
        assert normalize_date("2026-03-29") == "29032026"

    def test_already_ddmmyyyy(self):
        assert normalize_date("02042026") == "02042026"

    def test_ddmonyy(self):
        assert normalize_date("13JUL26") == "13072026"

    def test_ddmonyyyy(self):
        assert normalize_date("13JUL2026") == "13072026"

    def test_slash_format(self):
        assert normalize_date("02/04/2026") == "02042026"

    def test_none_raises(self):
        with pytest.raises(ValueError):
            normalize_date(None)

    def test_unrecognised_raises(self):
        with pytest.raises(ValueError):
            normalize_date("not-a-date")


class TestNormalizeFlightNumber:
    def test_strips_leading_zeros_int_float(self):
        assert normalize_flight_number("FR", 11.0) == "FR11"
        assert normalize_flight_number("FR", 10.0) == "FR10"

    def test_large_number(self):
        assert normalize_flight_number("FR", 1948.0) == "FR1948"

    def test_string_num(self):
        assert normalize_flight_number("EI", "3221") == "EI3221"

    def test_code_uppercased(self):
        assert normalize_flight_number("fr", 11) == "FR11"


class TestNormalizeEmeraldFlight:
    def test_removes_space(self):
        assert normalize_emerald_flight("EI 3221") == "EI3221"

    def test_already_clean(self):
        assert normalize_emerald_flight("EI3221") == "EI3221"

    def test_multiple_spaces(self):
        assert normalize_emerald_flight("EI  3221") == "EI3221"


class TestNormalizeFrequencyMask:
    def test_single_day_thursday(self):
        assert normalize_frequency_mask("...4...") == "4"

    def test_single_day_monday(self):
        assert normalize_frequency_mask("1......") == "1"

    def test_two_days(self):
        assert normalize_frequency_mask("..34...") == "34"

    def test_non_adjacent(self):
        assert normalize_frequency_mask("1...5..") == "15"

    def test_sunday(self):
        assert normalize_frequency_mask("......7") == "7"

    def test_every_day(self):
        assert normalize_frequency_mask("1234567") == "1234567"

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            normalize_frequency_mask("")


class TestParseEmeraldDayHeader:
    def test_monday(self):
        result = parse_emerald_day_header("Monday 13JUL26")
        assert result is not None
        day_name, date_str, day_num = result
        assert day_num == 1
        assert date_str == "13072026"

    def test_tuesday(self):
        result = parse_emerald_day_header("Tuesday 14JUL26")
        assert result[2] == 2

    def test_sunday(self):
        result = parse_emerald_day_header("Sunday 19JUL26")
        assert result[2] == 7

    def test_case_insensitive(self):
        result = parse_emerald_day_header("MONDAY 13JUL26")
        assert result is not None

    def test_no_space_between_day_and_date(self):
        result = parse_emerald_day_header("Monday13JUL26")
        assert result is not None
        day_name, date_str, day_num = result
        assert day_num == 1
        assert date_str == "13072026"

    def test_weekday_only_header(self):
        result = parse_emerald_day_header("Monday")
        assert result is not None
        day_name, date_str, day_num = result
        assert day_num == 1
        assert date_str is None

    def test_non_header_returns_none(self):
        assert parse_emerald_day_header("DUB Aircraft Plot") is None
        assert parse_emerald_day_header(None) is None
        assert parse_emerald_day_header(42) is None
