from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

from openpyxl import load_workbook
from sqlalchemy import func, select

from construction_os.cli_intake import run_intake
from construction_os.importers.intake import intake_batch
from construction_os.storage.models import CompanyRow, DocumentRow, WorkItemRow

FIXTURE_NAMES = (
    "vor_object_a.xlsx",
    "vor_object_b.xlsx",
    "vor_object_c.xlsx",
    "schedule_object_a.xlsx",
)


def _files(fixtures_dir):
    return [fixtures_dir / name for name in FIXTURE_NAMES]


def test_batch_four_reference_values(sqlite_session, fixtures_dir):
    receipt = intake_batch(
        sqlite_session, "Подрядчик", _files(fixtures_dir), date(2026, 9, 20)
    )
    assert receipt["summary"] == {
        "imported": 4,
        "skipped": 0,
        "rejected": 0,
        "portfolio_gross": "198690812.22",
        "portfolio_net": "162861321.49",
    }
    assert [row["positions"] for row in receipt["files"]][0] == 29


def test_duplicate_batch_does_not_create_rows(sqlite_session, fixtures_dir):
    intake_batch(sqlite_session, "A", _files(fixtures_dir), date(2026, 9, 20))
    before = sqlite_session.scalar(select(func.count()).select_from(WorkItemRow))
    receipt = intake_batch(sqlite_session, "A", _files(fixtures_dir), date(2026, 9, 20))
    assert receipt["summary"]["skipped"] == 4
    assert receipt["summary"]["imported"] == 0
    assert sqlite_session.scalar(select(func.count()).select_from(WorkItemRow)) == before
    assert sqlite_session.scalar(select(func.count()).select_from(DocumentRow)) == 4


def test_corrupt_xlsx_isolated(sqlite_session, fixtures_dir, tmp_path):
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"not a workbook")
    receipt = intake_batch(sqlite_session, "A", [bad, *_files(fixtures_dir)])
    assert receipt["summary"]["imported"] == 4
    assert receipt["summary"]["rejected"] == 1


def test_all_corrupt_exit_two(sqlite_session, tmp_path, capsys):
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"invalid")
    args = SimpleNamespace(company="A", files=[str(bad)], report=None)
    assert run_intake(args, sqlite_session) == 2
    assert "rejected: 1" in capsys.readouterr().out


def test_unsupported_diagnostics(sqlite_session, tmp_path):
    paths = []
    for suffix in (".xml", ".docx", ".pdf", ".txt"):
        path = tmp_path / ("test" + suffix)
        path.write_text("text")
        paths.append(path)
    receipt = intake_batch(sqlite_session, "A", paths)
    assert receipt["summary"]["rejected"] == 4
    assert "GGE" in receipt["files"][0]["errors"][0]
    assert "неподдерживаемый" in receipt["files"][1]["errors"][0]
    assert "неподдерживаемый" in receipt["files"][2]["errors"][0]
    assert "не определён" in receipt["files"][3]["errors"][0]


def test_structure_not_filename(sqlite_session, fixtures_dir, tmp_path):
    source = fixtures_dir / "vor_object_a.xlsx"
    renamed = tmp_path / "random.data"
    renamed.write_bytes(source.read_bytes())
    receipt = intake_batch(sqlite_session, "A", [renamed], date(2026, 9, 20))
    assert receipt["files"][0]["type"] == "vor"
    assert receipt["summary"]["imported"] == 1


def test_shifted_header(sqlite_session, fixtures_dir):
    shifted = fixtures_dir / "vor_object_a_shifted_2.xlsx"
    receipt = intake_batch(sqlite_session, "A", [shifted], date(2026, 9, 20))
    assert receipt["files"][0]["positions"] == 29
    assert receipt["files"][0]["type"] == "vor"


def test_json_receipt_matches_stdout(sqlite_session, fixtures_dir, tmp_path, capsys):
    path = tmp_path / "receipt.json"
    args = SimpleNamespace(
        company="A", files=[str(_files(fixtures_dir)[0])], report=str(path)
    )
    assert run_intake(args, sqlite_session) == 0
    receipt = json.loads(path.read_text(encoding="utf-8"))
    stdout = capsys.readouterr().out
    assert f'imported: {receipt["summary"]["imported"]}' in stdout
    assert receipt["summary"]["portfolio_gross"] in stdout


def test_company_created_once(sqlite_session, fixtures_dir):
    intake_batch(sqlite_session, "Новая", _files(fixtures_dir)[:1])
    intake_batch(sqlite_session, "Новая", _files(fixtures_dir)[:1])
    assert sqlite_session.scalar(select(func.count()).select_from(CompanyRow)) == 1


def test_cost_sheet_before_vor(sqlite_session, fixtures_dir, tmp_path):
    # The existing cost template contains a "Статьи" catalog and a "Затраты" sheet.
    from construction_os.importers.cost_template import make_template
    from construction_os.references import DEFAULT_COST_ARTICLES
    from construction_os.storage.models import CostArticleRow, CostEntryRow

    for index, (code, category, name) in enumerate(DEFAULT_COST_ARTICLES, 1):
        sqlite_session.add(
            CostArticleRow(code=code, category=category, name=name, sort_order=index)
        )
    sqlite_session.flush()
    path = tmp_path / "costs.xlsx"
    make_template(path)
    book = load_workbook(path)
    book["Затраты"].append(
        ["vor_object_a", None, "MAT", None, None, None, 100, "fixed", None, "net", None, None, None]
    )
    book.save(path)
    receipt = intake_batch(sqlite_session, "A", [path, _files(fixtures_dir)[0]])
    assert receipt["summary"]["imported"] == 2
    assert sqlite_session.scalar(select(func.count()).select_from(CostEntryRow)) == 1
