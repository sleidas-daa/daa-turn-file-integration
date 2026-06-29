"""Tests for the Aer Lingus SSIM parser."""
import pytest

from converter.parsers.aer_lingus import AerLingusParser, _parse_ssim_date, _parse_days_mask


class TestSSIMHelpers:
    """Unit tests for the SSIM field parsing helpers."""

    def test_parse_ssim_date_two_digit_year(self):
        assert _parse_ssim_date("29MAR26") == "29032026"

    def test_parse_ssim_date_four_digit_year(self):
        assert _parse_ssim_date("29MAR2026") == "29032026"

    def test_parse_ssim_date_oct(self):
        assert _parse_ssim_date("24OCT26") == "24102026"

    def test_parse_ssim_date_invalid_raises(self):
        with pytest.raises(ValueError):
            _parse_ssim_date("INVALID")

    def test_parse_days_mask_all_days(self):
        assert _parse_days_mask("1234567") == "1234567"

    def test_parse_days_mask_blanks(self):
        assert _parse_days_mask("1 3 5 7") == "1357"

    def test_parse_days_mask_single_day(self):
        # '  2    ' represents Tuesday only
        assert _parse_days_mask("  2    ") == "2"

    def test_parse_days_mask_empty(self):
        assert _parse_days_mask("       ") == ""


class TestAerLingusParserUnit:
    """Tests against the minimal synthetic SSIM fixture."""

    def test_parses_without_error(self, aer_lingus_txt):
        parser = AerLingusParser(str(aer_lingus_txt))
        records = parser.parse()
        assert isinstance(records, list)

    def test_produces_at_least_one_record(self, aer_lingus_txt):
        """The fixture has exactly one matchable DUB arrival → DUB departure pair."""
        parser = AerLingusParser(str(aer_lingus_txt))
        records = parser.parse()
        assert len(records) >= 1

    def test_flight_number_format(self, aer_lingus_txt):
        """All turn flights must start with the EI airline code."""
        parser = AerLingusParser(str(aer_lingus_txt))
        records = parser.parse()
        for rec in records:
            assert rec.arrival_flight.startswith("EI")
            assert rec.departure_flight.startswith("EI")

    def test_arrival_at_dub_identified(self, aer_lingus_txt):
        """EI3221 is the inbound GLA→DUB leg; it must appear as an arrival flight."""
        parser = AerLingusParser(str(aer_lingus_txt))
        records = parser.parse()
        arrivals = {r.arrival_flight for r in records}
        assert "EI3221" in arrivals

    def test_departure_from_dub_matched(self, aer_lingus_txt):
        """EI3222 is the first DUB departure after EI3221 arrives; must be the dep."""
        parser = AerLingusParser(str(aer_lingus_txt))
        records = parser.parse()
        pairs = {(r.arrival_flight, r.departure_flight) for r in records}
        assert ("EI3221", "EI3222") in pairs

    def test_overnight_zero_for_same_day_turn(self, aer_lingus_txt):
        """EI3221 arrives 08:50, EI3222 departs 09:20 — same day, overnight=0."""
        parser = AerLingusParser(str(aer_lingus_txt))
        records = parser.parse()
        matched = [r for r in records if r.arrival_flight == "EI3221"]
        assert len(matched) >= 1
        assert matched[0].overnight == 0

    def test_date_format(self, aer_lingus_txt):
        """Effective and discontinue dates must be in DDMMYYYY format."""
        parser = AerLingusParser(str(aer_lingus_txt))
        records = parser.parse()
        for rec in records:
            assert len(rec.effective_date) == 8
            assert rec.effective_date.isdigit()
            assert len(rec.discontinue_date) == 8
            assert rec.discontinue_date.isdigit()

    def test_frequency_field_populated(self, aer_lingus_txt):
        """Frequency must be non-empty digits."""
        parser = AerLingusParser(str(aer_lingus_txt))
        records = parser.parse()
        for rec in records:
            assert rec.frequency
            assert all(c.isdigit() for c in rec.frequency)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            AerLingusParser(str(tmp_path / "nope.txt"))

    def test_unsupported_extension_raises(self, tmp_path):
        p = tmp_path / "schedule.xlsx"
        p.write_bytes(b"dummy")
        with pytest.raises(ValueError, match="Unsupported file type"):
            AerLingusParser(str(p)).parse()

    def test_empty_file_returns_empty_list(self, tmp_path):
        p = tmp_path / "empty.txt"
        p.write_text("")
        records = AerLingusParser(str(p)).parse()
        assert records == []

    def test_no_dub_arrival_returns_empty(self, tmp_path):
        """A file with only non-DUB legs should produce no turns."""
        from tests.conftest import _ssim_line
        content = (
            "1IATA SSIM\n"
            + _ssim_line("EI", "3000", "29MAR26", "24OCT26", "1234567",
                         "LHR", "CDG", dep_time="0800", arr_time="1000")
            + "9END\n"
        )
        p = tmp_path / "no_dub.txt"
        p.write_text(content, encoding="utf-8")
        records = AerLingusParser(str(p)).parse()
        assert records == []
