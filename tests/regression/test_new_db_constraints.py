from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from construction_os.storage.models import (
    AcceptanceActRow,
    CompanyRow,
    PaymentObligationRow,
    WorkCalendarRow,
)
from construction_os.storage.repositories import ContractRepository


@pytest.mark.parametrize(
    "kind,constraint",
    [
        ("placed", "ck_acts_status_requires_placed_on"),
        ("signed", "ck_acts_status_requires_signed_on"),
        ("refused", "ck_acts_status_requires_refusal"),
        ("both", "ck_acts_not_signed_and_refused"),
        ("act_amount", "ck_acts_amount_positive"),
        ("payment_pair", "ck_pay_obl_paid_pair"),
        ("payment_range", "ck_pay_obl_paid_range"),
        ("payment_amount", "ck_pay_obl_amount_positive"),
    ],
)
def test_named_checks_on_active_database(db_session, kind, constraint):
    company = CompanyRow(name=f"Check-{kind}")
    db_session.add(company)
    db_session.flush()
    contract = ContractRepository(db_session).add(
        company.id,
        contract_type="government",
        number="N",
        signed_on=date(2026, 8, 1),
        price_is_final=True,
        valid_from=date(2026, 8, 1),
    )
    act_values = {
        "company_id": company.id,
        "contract_id": contract.id,
        "act_number": "A",
        "amount_gross": Decimal("100"),
        "placed_on": date(2026, 9, 1),
        "status": "placed",
        "valid_from": date(2026, 9, 1),
    }
    if kind.startswith("payment"):
        act = AcceptanceActRow(**act_values)
        db_session.add(act)
        db_session.flush()
        values = {
            "company_id": company.id,
            "act_id": act.id,
            "amount": Decimal("100"),
            "due_on": date(2026, 10, 8),
            "term_workdays": 7,
            "term_basis": "law_eis_7",
            "valid_from": date(2026, 9, 29),
        }
        if kind == "payment_pair":
            values["paid_amount"] = Decimal("10")
        elif kind == "payment_range":
            values["paid_on"] = date(2026, 10, 8)
            values["paid_amount"] = Decimal("101")
        else:
            values["amount"] = Decimal("0")
        row = PaymentObligationRow(**values)
    else:
        if kind == "placed":
            act_values["placed_on"] = None
        elif kind == "signed":
            act_values["status"] = "signed"
        elif kind == "refused":
            act_values["status"] = "refused"
            act_values["refusal_on"] = date(2026, 9, 20)
        elif kind == "both":
            act_values["signed_on"] = date(2026, 9, 29)
            act_values["refusal_on"] = date(2026, 9, 20)
        else:
            act_values["amount_gross"] = Decimal("0")
        row = AcceptanceActRow(**act_values)
    with pytest.raises(IntegrityError, match=constraint), db_session.begin_nested():
        db_session.add(row)
        db_session.flush()


def test_postgres_work_calendar_append_only(db_session):
    if db_session.bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL calendar trigger test")
    for sql in (
        "UPDATE work_calendar SET source='x' WHERE cal_date='2026-01-12'",
        "DELETE FROM work_calendar WHERE cal_date='2026-01-12'",
    ):
        with pytest.raises(Exception, match="append-only"), db_session.begin_nested():
            db_session.execute(text(sql))


def test_postgres_migration_has_730_calendar_rows(db_session):
    if db_session.bind.dialect.name != "postgresql":
        pytest.skip("SQLite create_all does not run migration seed")
    assert db_session.scalar(select(func.count()).select_from(WorkCalendarRow)) == 730
