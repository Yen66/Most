from __future__ import annotations

from pathlib import Path

from scripts.make_reference_values import render, render_new_sections

ROOT = Path(__file__).resolve().parents[2]


def test_reference_values_are_generated_byte_for_byte():
    actual = (ROOT / "docs/spec/reference_values.md").read_bytes()
    expected = (render() + render_new_sections()).encode("utf-8")
    assert actual == expected


def test_existing_C8_reference_prefix_unchanged():
    actual = (ROOT / "docs/spec/reference_values.md").read_bytes()
    assert actual.startswith(render().encode("utf-8"))
