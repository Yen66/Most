from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from construction_os.cli import main
from construction_os.references.calendar_seed import iter_calendar_days
from construction_os.storage import Base, make_engine
from construction_os.storage.models import CompanyRow, WorkCalendarRow
from construction_os.storage.repositories import ContractRepository


def test_acts_cli_add_pay_report(tmp_path, monkeypatch, capsys):
    url = f"sqlite+pysqlite:///{tmp_path / 'acts.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for year in (2026, 2027):
            session.add_all(WorkCalendarRow(**r) for r in iter_calendar_days(year))
        company = CompanyRow(name="CLI Co")
        session.add(company)
        session.flush()
        ContractRepository(session).add(
            company.id, contract_type="government", number="N1",
            signed_on=date(2026, 8, 1), price_is_final=True,
            valid_from=date(2026, 8, 1),
        )
        session.commit()
    assert main([
        "acts", "add", "--company", "CLI Co", "--contract-number", "N1",
        "--act-number", "A1", "--amount-gross", "1000000.00",
        "--placed-on", "2026-09-01", "--signed-on", "2026-09-29",
        "--via-eis",
    ]) == 0
    output = capsys.readouterr().out
    assert "Срок подписания: 2026-09-29" in output
    assert "due_on=2026-10-08; basis=law_eis_7" in output
    assert main([
        "acts", "pay", "--company", "CLI Co", "--contract-number", "N1",
        "--act-number", "A1", "--paid-on", "2026-10-10", "--amount", "400000",
    ]) == 0
    assert "остаток 600000.00" in capsys.readouterr().out
    assert main([
        "acts", "report", "--company", "CLI Co", "--as-of", "2026-10-20",
    ]) == 0
    report = capsys.readouterr().out
    assert "оплачено=400000.00; осталось=600000.00; просрочка=да" in report
    assert main(["acts", "list", "--company", "CLI Co"]) == 0
    assert "A1: signed" in capsys.readouterr().out


def test_acts_cli_missing_contract(tmp_path, monkeypatch, capsys):
    url = f"sqlite+pysqlite:///{tmp_path / 'missing.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(CompanyRow(name="CLI Co"))
        session.commit()
    result = main([
        "acts", "add", "--company", "CLI Co", "--contract-number", "MISSING",
        "--act-number", "A1", "--amount-gross", "100",
        "--placed-on", "2026-09-01",
    ])
    assert result != 0
    assert "нет данных: договор MISSING" in capsys.readouterr().out


def test_postgres_new_immutability_triggers(db_session):
    if db_session.bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL trigger test")
    from construction_os.storage.acts import create_act

    company = CompanyRow(name="PG Acts Co")
    db_session.add(company)
    db_session.flush()
    contract = ContractRepository(db_session).add(
        company.id, contract_type="government", number="PG-1",
        signed_on=date(2026, 8, 1), price_is_final=True,
        valid_from=date(2026, 8, 1),
    )
    act, obligation, _ = create_act(
        db_session, company.id, contract, "PG-A1", Decimal("100"),
        date(2026, 9, 1), signed_on=date(2026, 9, 29),
    )
    for table, row in (("acceptance_acts", act), ("payment_obligations", obligation)):
        with pytest.raises(Exception, match="immutable"), db_session.begin_nested():
            db_session.execute(
                text(f"UPDATE {table} SET replace_reason='x' WHERE id=:id"),
                {"id": row.id},
            )
        with pytest.raises(Exception, match="immutable"), db_session.begin_nested():
            db_session.execute(
                text(f"DELETE FROM {table} WHERE id=:id"), {"id": row.id}
            )
