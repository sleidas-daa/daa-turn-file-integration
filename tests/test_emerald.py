"""Tests for the Emerald Airlines parser."""
import pytest
from converter.parsers.emerald import EmeraldParser


class TestEmeraldParserUnit:
    """Tests against the minimal synthetic fixture (one aircraft, Mon-Tue)."""

    def test_parses_without_error(self, emerald_xlsx):
        parser = EmeraldParser(str(emerald_xlsx))
        records = parser.parse()
        assert isinstance(records, list)

    def test_flight_number_format(self, emerald_xlsx):
        """All flight numbers must be stripped of spaces."""
        parser = EmeraldParser(str(emerald_xlsx))
        records = parser.parse()
        for rec in records:
            assert " " not in rec.arrival_flight
            assert " " not in rec.departure_flight

    def test_season_dates_applied(self, emerald_xlsx):
        """Effective / discontinue dates must match the season in config."""
        from converter.config import SEASON_EFFECTIVE, SEASON_DISCONTINUE
        parser = EmeraldParser(str(emerald_xlsx))
        records = parser.parse()
        for rec in records:
            assert rec.effective_date == SEASON_EFFECTIVE
            assert rec.discontinue_date == SEASON_DISCONTINUE

    def test_ops_day_range(self, emerald_xlsx):
        """Frequency must be a single weekday digit (1-7)."""
        parser = EmeraldParser(str(emerald_xlsx))
        records = parser.parse()
        for rec in records:
            assert rec.frequency in [str(d) for d in range(1, 8)]

    def test_overnight_non_negative(self, emerald_xlsx):
        """Overnight must be a non-negative integer.

        Values > 1 are now valid: modular weekday arithmetic means an aircraft
        arriving Monday and departing Thursday has overnight=3.
        """
        parser = EmeraldParser(str(emerald_xlsx))
        records = parser.parse()
        for rec in records:
            assert isinstance(rec.overnight, int)
            assert rec.overnight >= 0
            # 6 is the maximum (e.g. Tuesday arrival → Monday departure = 6 nights)
            assert rec.overnight < 7

    def test_monday_dub_turns_produced(self, emerald_xlsx):
        """Monday (day 1): EI3221 arrives DUB → EI3222 departs DUB — turn exists."""
        parser = EmeraldParser(str(emerald_xlsx))
        records = parser.parse()
        day1_turns = [r for r in records if r.frequency == "1"]
        arr_flights = {r.arrival_flight for r in day1_turns}
        assert "EI3221" in arr_flights

    def test_overnight_detected(self, emerald_xlsx):
        """EI3223 arrives DUB Monday, EI3224 departs DUB Tuesday → overnight=1."""
        parser = EmeraldParser(str(emerald_xlsx))
        records = parser.parse()
        overnight_records = [r for r in records if r.overnight > 0]
        assert len(overnight_records) >= 1
        # The cross-day turn is on day 1 (Monday arrival)
        assert any(r.frequency == "1" for r in overnight_records)

    def test_non_dub_turns_excluded(self, emerald_xlsx):
        """All output flights must be EI-prefixed (fixture has only EI aircraft)."""
        parser = EmeraldParser(str(emerald_xlsx))
        records = parser.parse()
        for rec in records:
            assert rec.arrival_flight.startswith("EI")
            assert rec.departure_flight.startswith("EI")

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            EmeraldParser(str(tmp_path / "nope.xlsx"))

    def test_compact_day_headers(self, emerald_xlsx_compact_days):
        """Parser must handle day headers with no space before the date string."""
        parser = EmeraldParser(str(emerald_xlsx_compact_days))
        records = parser.parse()
        assert len(records) >= 1
        assert any(r.frequency == "1" for r in records)


class TestEmeraldOvernightCalculation:
    """Unit-level tests for the overnight counter fix.

    Before the fix, overnight was always 0 or 1 (binary day-change flag).
    After the fix, overnight = (dep_day - arr_day) % 7, so multi-night
    stays produce values like 2, 3, 4 …
    """

    def test_same_day_overnight_is_zero(self, emerald_xlsx):
        """EI3221 (GLA→DUB Mon) → EI3222 (DUB→EDI Mon) must give overnight=0."""
        parser = EmeraldParser(str(emerald_xlsx))
        records = parser.parse()
        same_day = [r for r in records
                    if r.arrival_flight == "EI3221"
                    and r.departure_flight == "EI3222"]
        assert len(same_day) == 1
        assert same_day[0].overnight == 0

    def test_one_night_overnight_is_one(self, emerald_xlsx):
        """EI3223 (EDI→DUB Mon) → EI3224 (DUB→GLA Tue) must give overnight=1."""
        parser = EmeraldParser(str(emerald_xlsx))
        records = parser.parse()
        one_night = [r for r in records
                     if r.arrival_flight == "EI3223"
                     and r.departure_flight == "EI3224"]
        assert len(one_night) == 1
        assert one_night[0].overnight == 1


class TestEmeraldPlotCW17:
    """Structural regression tests for the real Plot_DUB_CW17Nov25.xlsx file.

    These tests check structural properties of the output (record count,
    day coverage, field formats) rather than specific flight numbers so that
    they remain valid across schedule revisions.
    """

    def test_parses_all_aircraft(self, emerald_plot_cw17):
        """Real file has 10 aircraft — should produce at least 200 turn records."""
        records = EmeraldParser(str(emerald_plot_cw17)).parse()
        assert len(records) >= 200

    def test_all_ops_days_present(self, emerald_plot_cw17):
        """Every day of the week must appear in the output frequency values."""
        records = EmeraldParser(str(emerald_plot_cw17)).parse()
        ops_days = {rec.frequency for rec in records}
        assert ops_days == {str(d) for d in range(1, 8)}

    def test_record_structure(self, emerald_plot_cw17):
        """Every record must have valid flights, dates, and a non-negative overnight."""
        records = EmeraldParser(str(emerald_plot_cw17)).parse()
        for rec in records:
            assert rec.arrival_flight.startswith("EI")
            assert rec.departure_flight.startswith("EI")
            assert rec.overnight >= 0
            assert len(rec.effective_date) == 8
            assert len(rec.discontinue_date) == 8

    def test_overnight_range(self, emerald_plot_cw17):
        """Overnight values must be in 0-6 (modular weekly arithmetic)."""
        records = EmeraldParser(str(emerald_plot_cw17)).parse()
        for rec in records:
            assert 0 <= rec.overnight < 7
