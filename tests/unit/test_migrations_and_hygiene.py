from pathlib import Path

from construction_os.storage.models import Base

ROOT = Path(__file__).resolve().parents[2]


def test_schema_has_exactly_nineteen_tables():
    assert len(Base.metadata.tables) == 19


def test_generated_fixtures_are_ignored():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "*.xlsx" in text
    assert "tests/fixtures/generated/" in text
    assert "!tests/fixtures/*.xlsx" not in text
    assert "data_raw/*" in text


def test_no_bootstrap_file():
    assert not (ROOT / ".bootstrap").exists()


def test_fixture_readme_names_all_files():
    text = (ROOT / "tests" / "fixtures" / "README.md").read_text(encoding="utf-8")
    for name in (
        "vor_object_a.xlsx",
        "vor_object_b.xlsx",
        "vor_object_c.xlsx",
        "schedule_object_a.xlsx",
    ):
        assert name in text
