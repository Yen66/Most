from datetime import date

from construction_os.cli import main
from construction_os.storage import Base, make_engine


def test_debug_formatter(capsys):
    code = main(["debug-format", "1234.50"])
    assert code == 0
    assert "1 234.50 ₽" in capsys.readouterr().out


def test_report_empty_database(monkeypatch, tmp_path, capsys):
    database = tmp_path / "empty.db"
    url = f"sqlite+pysqlite:///{database}"
    Base.metadata.create_all(make_engine(url))
    monkeypatch.setenv("DATABASE_URL", url)
    code = main(["report", "--date", date(2026, 9, 20).isoformat()])
    assert code == 2
    assert "No imported objects" in capsys.readouterr().out


def test_cli_import_verify_report(monkeypatch, tmp_path, fixtures_dir, capsys):
    database = tmp_path / "pipeline.db"
    url = f"sqlite+pysqlite:///{database}"
    Base.metadata.create_all(make_engine(url))
    monkeypatch.setenv("DATABASE_URL", url)
    for suffix in ("a", "b", "c"):
        assert main(["import", str(fixtures_dir / f"vor_object_{suffix}.xlsx"), "--kind", "vor", "--company", "A"]) == 0
    assert main(["import", str(fixtures_dir / "schedule_object_a.xlsx"), "--kind", "schedule", "--company", "A"]) == 0
    assert main(["verify", "--object", "vor_object_a", "--company", "A"]) == 0
    assert main(["report", "--date", "2026-09-20", "--company", "A"]) == 0
    output = capsys.readouterr().out
    assert "Differences: 0" in output
    assert "Портфель с НДС: 198 690 812.22 ₽" in output
    assert "Портфель без НДС: 162 861 321.49 ₽" in output
