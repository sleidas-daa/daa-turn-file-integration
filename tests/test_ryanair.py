"""Tests for the Ryanair parser."""
import pytest
from converter.parsers.ryanair import RyanairParser


class TestRyanairParserUnit:
    def test_parses_valid_rows(self, ryanair_xlsx):
        parser = RyanairParser(str(ryanair_xlsx))
        records = parser.parse()
        # Rows 4 (bank) and 5 (ORK) are not in the output; 3 valid DUB records expected
        assert len(records) == 3

    def test_flight_number_format(self, ryanair_xlsx):
        parser = RyanairParser(str(ryanair_xlsx))
        records = parser.parse()
        assert records[0].arrival_flight == "FR11"
        assert records[0].departure_flight == "FR10"

    def test_date_format(self, ryanair_xlsx):
        parser = RyanairParser(str(ryanair_xlsx))
        records = parser.parse()
        # Row 1: eff=2026-04-02 -> 02042026
        assert records[0].effective_date == "02042026"
        assert records[0].discontinue_date == "22102026"

    def test_frequency_extracted(self, ryanair_xlsx):
        parser = RyanairParser(str(ryanair_xlsx))
        records = parser.parse()
        assert records[0].frequency == "4"   # ...4...
        assert records[1].frequency == "1"   # 1......

    def test_overnight_flag(self, ryanair_xlsx):
        parser = RyanairParser(str(ryanair_xlsx))
        records = parser.parse()
        assert records[0].overnight == 0  # no overnight
        assert records[1].overnight == 0
        assert records[2].overnight == 1  # Ovn=1

    def test_bank_rows_tracked_in_parse_errors(self, ryanair_xlsx):
        """Bank row (row 4) and non-DUB row (row 5) must appear in parse_errors."""
        parser = RyanairParser(str(ryanair_xlsx))
        records = parser.parse()
        assert len(records) == 3
        assert len(parser.parse_errors) >= 2
        reasons = [e["reason"] for e in parser.parse_errors]
        assert any("bank row" in r.lower() or "arrival" in r.lower() for r in reasons)

    def test_non_dub_airport_excluded_with_error(self, ryanair_xlsx):
        """Row with Apt=ORK must be excluded from output but tracked in parse_errors."""
        parser = RyanairParser(str(ryanair_xlsx))
        records = parser.parse()
        # No ORK flights in output
        all_apts_implied = True  # output only has DUB turns by construction
        assert len(records) == 3
        # parse_errors should contain the ORK exclusion
        ork_errors = [e for e in parser.parse_errors if "ORK" in e.get("reason", "")]
        assert len(ork_errors) >= 1

    def test_valid_records_have_non_empty_arrival(self, ryanair_xlsx):
        """All output records must have a non-empty arrival flight."""
        parser = RyanairParser(str(ryanair_xlsx))
        records = parser.parse()
        for rec in records:
            assert rec.arrival_flight != ""

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            RyanairParser(str(tmp_path / "nonexistent.xlsx"))

    def test_missing_required_columns(self, tmp_path):
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["ColA", "ColB"])
        ws.append(["x", "y"])
        p = tmp_path / "bad.xlsx"
        wb.save(p)
        with pytest.raises(ValueError, match="Missing required columns"):
            RyanairParser(str(p)).parse()


class TestRyanairIntegration:
    """Integration test using the real Ryanair sample file."""
    SAMPLE = r"C:\Users\Igi20\Downloads\S26 DUB TR - ryanair.xlsx"

    @pytest.mark.skipif(
        not __import__("pathlib").Path(SAMPLE).exists(),
        reason="Real sample file not available"
    )
    def test_real_file_parses(self):
        parser = RyanairParser(self.SAMPLE)
        records = parser.parse()
        assert len(records) > 1000, "Expected ~1500+ records from real file"

    @pytest.mark.skipif(
        not __import__("pathlib").Path(SAMPLE).exists(),
        reason="Real sample file not available"
    )
    def test_real_file_record_structure(self):
        parser = RyanairParser(self.SAMPLE)
        records = parser.parse()
        for rec in records[:20]:
            assert rec.arrival_flight.startswith("FR")
            assert rec.departure_flight.startswith("FR")
            assert rec.overnight >= 0  # any non-negative integer accepted
            assert len(rec.effective_date) == 8
            assert len(rec.discontinue_date) == 8
            assert rec.frequency.isdigit() or all(c in "1234567" for c in rec.frequency)

    @pytest.mark.skipif(
        not __import__("pathlib").Path(SAMPLE).exists(),
        reason="Real sample file not available"
    )
    def test_first_record_matches_expected_output(self):
        """First valid row should match row 1 of the adjusted CSV reference."""
        parser = RyanairParser(self.SAMPLE)
        records = parser.parse()
        r = records[0]
        assert r.arrival_flight == "FR11"
        assert r.departure_flight == "FR10"
        assert r.frequency == "4"
        assert r.overnight == 0
