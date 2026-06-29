"""Tests for parse preview helper."""
from pathlib import Path

from converter.preview import preview_file

FIXTURE = Path(__file__).parent / "fixtures" / "Plot_DUB_CW17Nov25.xlsx"


class TestPreviewFile:
    def test_emerald_fixture_preview(self):
        if not FIXTURE.exists():
            return
        result = preview_file(str(FIXTURE), template_override="emerald")
        assert result["ok"] is True
        assert result["record_count"] >= 200
        assert len(result["rows"]) > 0
