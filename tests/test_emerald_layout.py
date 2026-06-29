"""Tests for Emerald layout inspection and sidecar config."""
import json

from converter.parsers.emerald import EmeraldParser
from converter.parsers.emerald_layout import (
    EmeraldLayoutConfig,
    inspect_emerald_layout,
    load_emerald_config,
    save_emerald_config,
)


class TestEmeraldLayoutInspect:
    def test_inspect_cw17_fixture(self, emerald_plot_cw17):
        result = inspect_emerald_layout(emerald_plot_cw17)
        assert result["parseable"] is True
        assert result["aircraft_count"] == 10
        assert len(result["day_sections"]) == 7
        assert result["header_row"] == 5
        assert not result["warnings"]

    def test_inspect_unknown_file(self, tmp_path):
        result = inspect_emerald_layout(tmp_path / "missing.xlsx")
        assert result["parseable"] is False


class TestEmeraldSidecarConfig:
    def test_load_defaults_when_no_sidecar(self, emerald_plot_cw17):
        cfg = load_emerald_config(emerald_plot_cw17)
        assert cfg.aircraft_prefix == "EAI"
        assert cfg.expected_days == 7

    def test_sidecar_roundtrip(self, tmp_path):
        cfg = EmeraldLayoutConfig(aircraft_prefix="EAI", expected_days=5)
        path = tmp_path / "custom.emerald.json"
        save_emerald_config(cfg, path)
        loaded = load_emerald_config("ignored.xlsx", config_path=path)
        assert loaded.expected_days == 5

    def test_sidecar_auto_discovered(self, tmp_path):
        sidecar = tmp_path / "plot.emerald.json"
        save_emerald_config(
            EmeraldLayoutConfig(effective_date="01012026"),
            sidecar,
        )
        cfg = load_emerald_config(tmp_path / "plot.xlsx", config_path=sidecar)
        assert cfg.effective_date == "01012026"

    def test_custom_dates_applied(self, emerald_plot_cw17, tmp_path):
        sidecar = tmp_path / "dates.emerald.json"
        save_emerald_config(
            EmeraldLayoutConfig(
                effective_date="01012026",
                discontinue_date="31122026",
            ),
            sidecar,
        )
        records = EmeraldParser(
            str(emerald_plot_cw17),
            config_path=sidecar,
        ).parse()
        assert records[0].effective_date == "01012026"
        assert records[0].discontinue_date == "31122026"


class TestEmeraldInspectCLI:
    def test_inspect_json_shape(self, emerald_plot_cw17):
        result = inspect_emerald_layout(emerald_plot_cw17)
        # Future UI can bind directly to this schema
        json.dumps(result)
        assert "sidecar_path" in result
        assert result["sidecar_path"].endswith(".emerald.json")
