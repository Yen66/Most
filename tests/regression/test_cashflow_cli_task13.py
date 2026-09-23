from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from construction_os.cli import main
from construction_os.references.calendar_seed import iter_calendar_days
from construction_os.storage import Base, make_engine
from construction_os.storage.acts import create_act
from construction_os.storage.models import CompanyRow, CostArticleRow, WorkCalendarRow
from construction_os.storage.repositories import ContractRepository


def setup(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'cf.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(WorkCalendarRow(**row) for row in iter_calendar_days(2026))
        for code in ("MAT", "LAB"):
            session.add(CostArticleRow(code=code, category="direct", name=code, is_active=True))
        company = CompanyRow(name="Demo Co")
        session.add(company)
        session.flush()
        contract = ContractRepository(session).add(
            company.id,
            contract_type="government",
            number="DEMO",
            signed_on=date(2026, 8, 1),
            price_is_final=True,
            valid_from=date(2026, 8, 1),
        )
        create_act(
            session,
            company.id,
            contract,
            "CF1",
            Decimal("1000000"),
            date(2026, 9, 1),
            signed_on=date(2026, 9, 29),
            via_eis=True,
        )
        session.commit()
    return engine


def cmd(action, *args):
    return ["cash-flow", action, "--company", "Demo Co", *args]


def test_CLI_CF1_and_idempotent_build(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    assert (
        main(
            cmd(
                "add",
                "--date",
                "2026-09-15",
                "--direction",
                "out",
                "--amount",
                "600000",
                "--category",
                "MAT",
                "--contract-number",
                "DEMO",
            )
        )
        == 0
    )
    assert (
        main(
            cmd(
                "add",
                "--date",
                "2026-09-30",
                "--direction",
                "out",
                "--amount",
                "200000",
                "--category",
                "LAB",
                "--contract-number",
                "DEMO",
            )
        )
        == 0
    )
    assert main(cmd("build", "--contract-number", "DEMO")) == 0
    assert main(cmd("build", "--contract-number", "DEMO")) == 0
    build_output = capsys.readouterr().out
    assert "создано: 1, существует: 0" in build_output
    assert "создано: 0, существует: 1" in build_output
    assert main(cmd("report", "--as-of", "2026-10-31", "--rate", "0.14")) == 0
    output = capsys.readouterr().out
    assert "Дней в минусе: 23" in output
    assert "Максимальный разрыв: 800000.00" in output
    assert "Финансирование [ОЦЕНКА]: 5906.85" in output
    assert "Баланс на 2026-10-31: +200000.00" in output


def test_CLI_report_read_only(tmp_path, monkeypatch, capsys):
    engine = setup(tmp_path, monkeypatch)
    assert main(cmd("build")) == 0
    capsys.readouterr()
    with Session(engine) as session:
        before = {
            table.name: session.scalar(select(func.count()).select_from(table))
            for table in Base.metadata.tables.values()
        }
    assert main(cmd("report", "--as-of", "2026-10-31", "--rate", "0.14")) == 0
    with Session(engine) as session:
        after = {
            table.name: session.scalar(select(func.count()).select_from(table))
            for table in Base.metadata.tables.values()
        }
    assert before == after


def test_CLI_earlier_than_first_flow_error(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    assert main(cmd("build")) == 0
    capsys.readouterr()
    assert main(cmd("report", "--as-of", "2026-08-01", "--rate", "0.14")) == 2
    assert "cash-flow report: as_of earlier than first flow" in capsys.readouterr().out


def test_CLI_unknown_category(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    assert (
        main(
            cmd(
                "add",
                "--date",
                "2026-09-15",
                "--direction",
                "in",
                "--amount",
                "1",
                "--category",
                "unknown",
            )
        )
        == 2
    )
    assert "unknown inflow category: unknown" in capsys.readouterr().out


def test_CLI_plan_override(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    assert (
        main(
            cmd(
                "add",
                "--date",
                "2026-09-15",
                "--direction",
                "out",
                "--amount",
                "100",
                "--category",
                "MAT",
                "--plan",
            )
        )
        == 0
    )
    capsys.readouterr()
    assert main(cmd("report", "--as-of", "2026-09-20", "--rate", "0.14")) == 0
    assert "MAT | plan | USER_INPUT" in capsys.readouterr().out


def test_CLI_future_plan_separate(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch)
    assert (
        main(
            cmd(
                "add",
                "--date",
                "2026-09-15",
                "--direction",
                "out",
                "--amount",
                "100",
                "--category",
                "MAT",
            )
        )
        == 0
    )
    assert (
        main(
            cmd(
                "add",
                "--date",
                "2026-11-01",
                "--direction",
                "in",
                "--amount",
                "1000",
                "--category",
                "advance",
                "--plan",
            )
        )
        == 0
    )
    capsys.readouterr()
    assert main(cmd("report", "--as-of", "2026-10-31", "--rate", "0.14")) == 0
    output = capsys.readouterr().out
    assert "За горизонтом (план)" in output
    assert "2026-11-01 | inflow | 1000.00 | advance | plan" in output
