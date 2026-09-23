from __future__ import annotations

from pathlib import Path
from runpy import run_path

ROOT = Path(__file__).resolve().parents[2]


def _generator():
    return run_path(str(ROOT / "scripts" / "make_reference_values.py"))


def test_reference_values_are_generated_byte_for_byte():
    actual = (ROOT / "docs/spec/reference_values.md").read_bytes()
    generator = _generator()
    expected = (generator["render"]() + generator["render_new_sections"]()).encode("utf-8")
    assert actual == expected


def test_existing_C8_reference_prefix_unchanged():
    actual = (ROOT / "docs/spec/reference_values.md").read_bytes()
    assert actual.startswith(_generator()["render"]().encode("utf-8"))
