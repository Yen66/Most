from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from construction_os.cli import main
from construction_os.references.cost_articles import DEFAULT_COST_ARTICLES
from construction_os.storage import Base, make_engine
from construction_os.storage.models import (
    CompanyRow,
    CostArticleRow,
    CostEntryRow,
    ObjectRow,
    ValueSourceRow,
    WorkItemRow,
)

D = Decimal


def setup_db(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'whatif.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for i, (code, cat, name) in enumerate(DEFAULT_COST_ARTICLES, 1):
            session.add(
                CostArticleRow(
                    code=code,
                    category=cat,
                    name=name,
                    is_active=True,
                    sort_order=i,
                )
            )
        company = CompanyRow(name="Demo Co")
        session.add(company)
        session.flush()
        src = ValueSourceRow(company_id=company.id, source_type="user_input", confidence="exact")
        session.add(src)
        session.flush()
        obj = ObjectRow(
            company_id=company.id,
            name="Demo Object",
            valid_from=date(2026, 9, 20),
        )
        session.add(obj)
        session.flush()
        session.add(
            WorkItemRow(
                company_id=company.id,
                object_id=obj.id,
                position_no=1,
                name="Demo",
                unit="шт",
                quantity=D("1"),
                price_gross=D("1220000"),
                amount_gross=D("1220000"),
                vat_rate=D("0.22"),
                source_id=src.id,
                valid_from=date(2026, 9, 20),
            )
        )
        for code, amount in (
            ("MAT", "500000"),
            ("LAB", "250000"),
            ("MACH_OWN", "70000"),
            ("OVR_SITE", "50000"),
            ("BANK_GUAR", "27000"),
        ):
            session.add(
                CostEntryRow(
                    company_id=company.id,
                    object_id=obj.id,
                    article_code=code,
                    amount=D(amount),
                    amount_type="fixed",
                    vat_mode="net",
                    source_id=src.id,
                    valid_from=date(2026, 9, 20),
                    created_by="test",
                )
            )
        session.commit()
    return engine


def command(*args):
    return [
        "whatif",
        "--company",
        "Demo Co",
        "--object",
        "Demo Object",
        "--date",
        "2026-09-20",
        *args,
    ]


def test_CLI_S6_and_read_only(tmp_path, monkeypatch, capsys):
    engine = setup_db(tmp_path, monkeypatch)
    with Session(engine) as session:
        before = {
            table.name: session.scalar(select(func.count()).select_from(table))
            for table in Base.metadata.tables.values()
        }
    assert (
        main(
            command(
                "--cost-multiplier",
                "item:MAT=1.10",
                "--price-reduction",
                "0.92",
            )
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "Прибыль до налога: -27 000" in output
    assert "Выручка без НДС: 920 000" in output
    assert "Полнота: неполный" in output
    with Session(engine) as session:
        after = {
            table.name: session.scalar(select(func.count()).select_from(table))
            for table in Base.metadata.tables.values()
        }
    assert before == after


def test_CLI_S10_goal_seek(tmp_path, monkeypatch, capsys):
    setup_db(tmp_path, monkeypatch)
    assert main(command("--goal-seek", "item:MAT", "--target-profit", "0")) == 0
    output = capsys.readouterr().out
    assert "m*: 1.206000" in output
    assert "Проверочная прибыль: 0.00" in output


def test_CLI_S12_rounding_residual(tmp_path, monkeypatch, capsys):
    setup_db(tmp_path, monkeypatch)
    assert main(command("--goal-seek", "all", "--target-profit", "0")) == 0
    output = capsys.readouterr().out
    assert "m*: 1.118391" in output
    assert "Остаток округления: 0.17" in output


def test_CLI_F6_sensitivity(tmp_path, monkeypatch, capsys):
    setup_db(tmp_path, monkeypatch)
    assert main(command("--sensitivity", "--step", "0.10")) == 0
    output = capsys.readouterr().out
    assert "item:MAT" in output and "-50000.00" in output
    assert "BANK_GUAR" in output and "financial:" in output


def test_CLI_show_29_articles(tmp_path, monkeypatch, capsys):
    setup_db(tmp_path, monkeypatch)
    assert main(command("--show-parameters")) == 0
    output = capsys.readouterr().out
    assert all(code + " |" in output for code, _, _ in DEFAULT_COST_ARTICLES)
    assert "нет данных" in output


def test_CLI_bad_target(tmp_path, monkeypatch, capsys):
    setup_db(tmp_path, monkeypatch)
    assert main(command("--cost-multiplier", "wrong=1.1")) == 2
    assert "invalid cost-multiplier target: wrong" in capsys.readouterr().out


def test_CLI_bad_multiplier(tmp_path, monkeypatch, capsys):
    setup_db(tmp_path, monkeypatch)
    assert main(command("--cost-multiplier", "all=bad")) == 2
    assert "invalid multiplier: bad" in capsys.readouterr().out


def test_CLI_bad_step(tmp_path, monkeypatch, capsys):
    setup_db(tmp_path, monkeypatch)
    assert main(command("--sensitivity", "--step", "bad")) == 2
    assert "invalid sensitivity step: bad" in capsys.readouterr().out


def test_CLI_tenant_isolation(tmp_path, monkeypatch, capsys):
    engine = setup_db(tmp_path, monkeypatch)
    with Session(engine) as session:
        company = CompanyRow(name="Other Co")
        session.add(company)
        session.flush()
        obj = ObjectRow(
            company_id=company.id,
            name="Demo Object",
            valid_from=date(2026, 9, 20),
        )
        session.add(obj)
        session.flush()
        src = ValueSourceRow(company_id=company.id, source_type="user_input", confidence="exact")
        session.add(src)
        session.flush()
        session.add(
            CostEntryRow(
                company_id=company.id,
                object_id=obj.id,
                article_code="MAT",
                amount=D("99999999"),
                amount_type="fixed",
                vat_mode="net",
                source_id=src.id,
                valid_from=date(2026, 9, 20),
                created_by="test",
            )
        )
        session.commit()
    assert main(command()) == 0
    assert "Прибыль до налога: 103 000" in capsys.readouterr().out
