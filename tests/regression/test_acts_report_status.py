from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from construction_os.cli import main
from construction_os.references.calendar_seed import iter_calendar_days
from construction_os.storage import Base, make_engine
from construction_os.storage.acts import change_act_status, create_act
from construction_os.storage.models import CompanyRow, WorkCalendarRow
from construction_os.storage.repositories import ContractRepository


def test_report_signing_status_and_active_contract_cap(tmp_path, monkeypatch, capsys):
    url = f"sqlite+pysqlite:///{tmp_path / 'report.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(WorkCalendarRow(**row) for row in iter_calendar_days(2026))
        company = CompanyRow(name="Report Co")
        session.add(company)
        session.flush()
        repo = ContractRepository(session)
        contract = repo.add(
            company.id,
            contract_type="government",
            number="N1",
            signed_on=date(2026, 8, 1),
            price_is_final=True,
            valid_from=date(2026, 8, 1),
        )
        create_act(
            session,
            company.id,
            contract,
            "SIGNED",
            Decimal("1000000"),
            date(2026, 9, 1),
            signed_on=date(2026, 9, 29),
            via_eis=True,
        )
        create_act(
            session,
            company.id,
            contract,
            "PENDING",
            Decimal("100"),
            date(2026, 9, 1),
            via_eis=True,
        )
        repo.supersede(
            company.id,
            contract.id,
            {"penalty_cap_pct": Decimal("0.005")},
            "contract cap",
            "test",
            date(2026, 10, 1),
        )
        session.commit()
    assert (
        main(
            [
                "acts",
                "report",
                "--company",
                "Report Co",
                "--as-of",
                "2026-10-28",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "SIGNED: signed" in output and "подписан в срок" in output
    assert "PENDING: placed" in output and "просрочено" in output
    assert "Пеня: 5000.00" in output


def test_report_refusal_reset_notice(tmp_path, monkeypatch, capsys):
    url = f"sqlite+pysqlite:///{tmp_path / 'refusal.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(WorkCalendarRow(**row) for row in iter_calendar_days(2026))
        company = CompanyRow(name="Refusal Co")
        session.add(company)
        session.flush()
        contract = ContractRepository(session).add(
            company.id,
            contract_type="government",
            number="N1",
            signed_on=date(2026, 8, 1),
            price_is_final=True,
            valid_from=date(2026, 8, 1),
        )
        first, _, _ = create_act(
            session,
            company.id,
            contract,
            "A1",
            Decimal("100"),
            date(2026, 9, 1),
            via_eis=True,
        )
        change_act_status(
            session,
            company.id,
            first,
            refusal_on=date(2026, 9, 20),
            refusal_reason="Замечания",
        )
        create_act(
            session,
            company.id,
            contract,
            "A1",
            Decimal("100"),
            date(2026, 9, 25),
            via_eis=True,
        )
        session.commit()
    assert (
        main(
            [
                "acts",
                "report",
                "--company",
                "Refusal Co",
                "--as-of",
                "2026-10-01",
            ]
        )
        == 0
    )
    assert "срок сброшен: новый акт от 2026-09-25" in capsys.readouterr().out
