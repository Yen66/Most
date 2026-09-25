from __future__ import annotations

from pathlib import Path
from runpy import run_path

from construction_os.storage.models import Base
from construction_os.storage.repositories import (
    ALL_REPOSITORIES,
    EXCLUDED_TABLES,
    TENANT_REPOSITORIES,
)

ROOT = Path(__file__).resolve().parents[2]


def generator():
    return run_path(str(ROOT / "scripts/make_reference_values.py"))


def test_verdict_section_all_e_v1_rows():
    section = generator()["render_verdict_sections"]()
    expected = (
        "| 0.00% | 35 656 922.00 | 29 226 985.25 | 6 429 936.75 | 0.00 |",
        "| 5.00% | 33 874 075.93 | 27 765 636.01 | 6 108 439.92 | -1 461 349.24 |",
        "| 8.00% | 32 804 368.25 | 26 888 826.43 | 5 915 541.82 | -2 338 158.82 |",
        "| 10.00% | 32 091 229.83 | 26 304 286.75 | 5 786 943.08 | -2 922 698.50 |",
        "| 15.00% | 30 308 383.71 | 24 842 937.47 | 5 465 446.24 | -4 384 047.78 |",
        "| 20.00% | 28 525 537.58 | 23 381 588.18 | 5 143 949.40 | -5 845 397.07 |",
        "| 22.00% | 27 812 399.16 | 22 797 048.49 | 5 015 350.67 | -6 429 936.76 |",
    )
    assert all(row in section for row in expected)


def test_verdict_section_e_v2_risk_count():
    section = generator()["render_verdict_sections"]()
    assert "WINTER, TEMP_FAC, TRAFFIC, MOB, DRAIN, LAB_CONTROL (6)" in section
    assert "остальные отсутствующие статьи 23; всего отсутствует 29" in section


def test_verdict_section_e_v3_e_v5():
    section = generator()["render_verdict_sections"]()
    assert "прибыль до налога 103 000.00; маржа 10.30%; светофор ВХОДИТЬ" in section
    assert "прибыль -27 000.00; маржа -3.10%; светофор НЕ ВХОДИТЬ" in section


def test_reference_file_exact_generator_output():
    g = generator()
    expected = (g["render"]() + g["render_new_sections"]()).encode("utf-8")
    assert (ROOT / "docs/spec/reference_values.md").read_bytes() == expected


def test_schema_counters_unchanged():
    assert len(Base.metadata.tables) == 21
    assert len(TENANT_REPOSITORIES) == 17
    assert len(ALL_REPOSITORIES) == 21
    assert len(EXCLUDED_TABLES) == 4
