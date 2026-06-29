"""Tests for CSV export helpers."""
from converter.dataclasses import TurnRecord
from converter.exporter import build_output_filename, write_csv


def test_write_csv_without_header(tmp_path):
    records = [
        TurnRecord("FR11", "FR10", 0, "02042026", "22102026", "4"),
    ]
    out = write_csv(records, str(tmp_path / "out.csv"))
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines == ["FR11,FR10,0,02042026,22102026,4"]


def test_write_csv_with_header(tmp_path):
    records = [
        TurnRecord("FR11", "FR10", 0, "02042026", "22102026", "4"),
    ]
    out = write_csv(records, str(tmp_path / "out.csv"), include_header=True)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("arrival_flight,")
    assert "FR11" in lines[1]


def test_build_output_filename_sanitises_spaces():
    name = build_output_filename("/data/My Schedule.xlsx", "ryanair")
    assert name == "OUTPUT_My_Schedule.csv"
