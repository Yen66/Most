"""Isolated deterministic CF1 demo. Run after alembic upgrade head."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from construction_os.references.calendar_seed import iter_calendar_days
from construction_os.storage import make_engine
from construction_os.storage.acts import create_act
from construction_os.storage.cashflow import add_manual_flow, build_cash_flows
from construction_os.storage.models import (
    AcceptanceActRow, CompanyRow, ContractRow, WorkCalendarRow,
)
from construction_os.storage.repositories import ContractRepository


def main() -> None:
    with Session(make_engine()) as session:
        company = session.scalar(select(CompanyRow).where(CompanyRow.name == "Demo Co"))
        if company is None:
            company = CompanyRow(name="Demo Co")
            session.add(company)
            session.flush()
        contract = session.scalar(select(ContractRow).where(
            ContractRow.company_id == company.id,
            ContractRow.number == "ДЕМО-АКТ-2026",
            ContractRow.valid_to.is_(None),
        ))
        if contract is None:
            contract = ContractRepository(session).add(
                company.id, contract_type="government", number="ДЕМО-АКТ-2026",
                signed_on=date(2026, 8, 1), price_is_final=True,
                valid_from=date(2026, 8, 1),
            )
        if session.scalar(select(WorkCalendarRow.id).limit(1)) is None:
            session.add_all(WorkCalendarRow(**row) for row in iter_calendar_days(2026))
            session.flush()
        if session.scalar(select(AcceptanceActRow).where(
            AcceptanceActRow.company_id == company.id,
            AcceptanceActRow.contract_id == contract.id,
            AcceptanceActRow.act_number == "CF1",
            AcceptanceActRow.valid_to.is_(None),
        )) is None:
            create_act(
                session, company.id, contract, "CF1", Decimal("1000000"),
                date(2026, 9, 1), signed_on=date(2026, 9, 29),
                via_eis=True, actor="cashflow-demo",
            )
            add_manual_flow(
                session, company.id, date(2026, 9, 15), "outflow",
                Decimal("600000"), "MAT", contract_id=contract.id,
                actor="cashflow-demo",
            )
            add_manual_flow(
                session, company.id, date(2026, 9, 30), "outflow",
                Decimal("200000"), "LAB", contract_id=contract.id,
                actor="cashflow-demo",
            )
        result = build_cash_flows(session, company.name, contract.number, "cashflow-demo")
        session.commit()
        print(f"cashflow demo: создано: {result.created}, существует: {result.existed}")


if __name__ == "__main__":
    main()
