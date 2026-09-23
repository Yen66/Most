from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from construction_os.storage import make_engine
from construction_os.storage.acts import change_act_status, create_act, register_payment
from construction_os.storage.models import CompanyRow
from construction_os.storage.repositories import ContractRepository


def main() -> None:
    engine = make_engine()
    with Session(engine) as session:
        company = session.scalar(select(CompanyRow).where(CompanyRow.name == "Demo Co"))
        if company is None:
            company = CompanyRow(name="Demo Co")
            session.add(company)
            session.flush()
        contract = ContractRepository(session).add(
            company.id,
            contract_type="government",
            number="ДЕМО-АКТ-2026",
            signed_on=date(2026, 8, 1),
            price_is_final=True,
            valid_from=date(2026, 8, 1),
        )
        _first, obligation, _ = create_act(
            session, company.id, contract, "ДЕМО-1",
            Decimal("10000.00"), date(2026, 9, 1),
            signed_on=date(2026, 9, 29), via_eis=True, actor="demo",
        )
        register_payment(
            session, company.id, obligation, date(2026, 10, 8),
            Decimal("10000.00"), actor="demo",
        )
        create_act(
            session, company.id, contract, "ДЕМО-2",
            Decimal("1000000.00"), date(2026, 9, 1),
            signed_on=date(2026, 9, 29), via_eis=True, actor="demo",
        )
        third, _, _ = create_act(
            session, company.id, contract, "ДЕМО-3",
            Decimal("20000.00"), date(2026, 9, 1), actor="demo",
        )
        change_act_status(
            session, company.id, third, refusal_on=date(2026, 9, 20),
            refusal_reason="Замечания", actor="demo",
        )
        create_act(
            session, company.id, contract, "ДЕМО-3",
            Decimal("20000.00"), date(2026, 9, 25), actor="demo",
        )
        session.commit()
        print(f"acts demo: {company.name}, contract={contract.number}, acts=3")


if __name__ == "__main__":
    main()
