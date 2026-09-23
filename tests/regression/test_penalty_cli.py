from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from construction_os.cli import main
from construction_os.references.calendar_seed import iter_calendar_days
from construction_os.storage import Base, make_engine
from construction_os.storage.acts import create_act, register_payment
from construction_os.storage.models import CompanyRow, WorkCalendarRow
from construction_os.storage.repositories import ContractRepository


def test_penalty_cli_partial_payment_and_report(tmp_path, monkeypatch, capsys):
    url = f"sqlite+pysqlite:///{tmp_path / 'penalty.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            WorkCalendarRow(**row) for row in iter_calendar_days(2026)
        )
        company = CompanyRow(name="Penalty Co")
        session.add(company)
        session.flush()
        contract = ContractRepository(session).add(
            company.id, contract_type="government", number="N1",
            signed_on=date(2026, 8, 1), price_is_final=True,
            valid_from=date(2026, 8, 1),
        )
        act, obligation, _ = create_act(
            session, company.id, contract, "P5", Decimal("1000000"),
            date(2026, 8, 1), signed_on=date(2026, 9, 1),
        )
        register_payment(
            session, company.id, obligation, date(2026, 9, 30),
            Decimal("400000"),
        )
        session.commit()
    assert main([
        "penalty", "--company", "Penalty Co", "--contract-number", "N1",
        "--act-number", "P5", "--as-of", "2026-10-20",
    ]) == 0
    output = capsys.readouterr().out
    assert "дней просрочки=40" in output
    assert "пеня 9 333,33" in output
    assert "пеня 5 600,00" in output
    assert "ИТОГ: 14 933,33" in output
    assert main([
        "acts", "report", "--company", "Penalty Co", "--as-of", "2026-10-20",
    ]) == 0
    assert "Пеня: 14933.33" in capsys.readouterr().out


def test_penalty_cli_ambiguity(tmp_path, monkeypatch, capsys):
    url = f"sqlite+pysqlite:///{tmp_path / 'ambiguous.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            WorkCalendarRow(**row) for row in iter_calendar_days(2026)
        )
        company = CompanyRow(name="Ambiguous Co")
        session.add(company)
        session.flush()
        for number in ("N1", "N2"):
            contract = ContractRepository(session).add(
                company.id, contract_type="government", number=number,
                signed_on=date(2026, 8, 1), price_is_final=True,
                valid_from=date(2026, 8, 1),
            )
            create_act(
                session, company.id, contract, "A1", Decimal("100"),
                date(2026, 9, 1), signed_on=date(2026, 9, 29),
            )
        session.commit()
    assert main([
        "penalty", "--company", "Ambiguous Co", "--act-number", "A1",
        "--as-of", "2026-10-28",
    ]) != 0
    assert "неоднозначность: уточните договор" in capsys.readouterr().out
