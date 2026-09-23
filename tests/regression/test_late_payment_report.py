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


def test_late_full_payment_is_reported_as_late(tmp_path, monkeypatch, capsys):
    url = f"sqlite+pysqlite:///{tmp_path / 'late.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(WorkCalendarRow(**row) for row in iter_calendar_days(2026))
        company = CompanyRow(name="Late Co")
        session.add(company)
        session.flush()
        contract = ContractRepository(session).add(
            company.id,
            contract_type="government",
            number="N",
            signed_on=date(2026, 8, 1),
            price_is_final=True,
            valid_from=date(2026, 8, 1),
        )
        _act, obligation, _ = create_act(
            session,
            company.id,
            contract,
            "LATE",
            Decimal("1000000"),
            date(2026, 9, 1),
            signed_on=date(2026, 9, 29),
        )
        register_payment(
            session,
            company.id,
            obligation,
            date(2026, 10, 28),
            Decimal("1000000"),
        )
        session.commit()
    assert (
        main(
            [
                "acts",
                "report",
                "--company",
                "Late Co",
                "--as-of",
                "2026-10-28",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "просрочка=да" in output
    assert "Пеня: 9333.33" in output
    assert "via_eis: нет данных — принято ЕИС-актирование" in output
