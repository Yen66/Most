from __future__ import annotations

from pathlib import Path
from runpy import run_path

ROOT = Path(__file__).resolve().parents[2]


def generated():
    return run_path(str(ROOT / "scripts/make_reference_values.py"))


def test_old_reference_prefix_preserved_byte_for_byte():
    g = generated()
    actual = (ROOT / "docs/spec/reference_values.md").read_bytes()
    expected = (g["render"]() + g["render_new_sections"]()).split("\n## Cash-flow", 1)[0]
    assert len(expected.encode("utf-8")) == 4946
    assert actual.startswith(expected.encode("utf-8"))


def test_CF1_reference_calculated_by_production():
    section = generated()["render_task13_sections"]()
    assert "| CF1 | 23 | 800 000.00 | 2026-09-30" in section
    assert "5 906.85 | 200 000.00 |" in section


def test_goal_seek_rounding_residual_documented():
    section = generated()["render_task13_sections"]()
    assert "| S12 | all | 0.00 | 1.118391 | -0.17 | 0.17 |" in section
    assert "| S11 | price | 0.00 | 0.897000 | 0.00 | 0.00 |" in section


def test_F6_tied_rank_and_financial_exclusion():
    section = generated()["render_task13_sections"]()
    assert "| item:OVR_SITE | 108 000.00 | 98 000.00 | -5 000.00 | 7 |" in section
    assert "| item:BANK_GUAR | 103 000.00 | 103 000.00 | 0.00 | — |" in section


def test_all_reference_sections_byte_exact():
    g = generated()
    actual = (ROOT / "docs/spec/reference_values.md").read_bytes()
    assert actual == (g["render"]() + g["render_new_sections"]()).encode("utf-8")
