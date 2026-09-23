from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from construction_os.references.calendar_seed import iter_calendar_days
from construction_os.storage.acts import create_act, register_payment
from construction_os.storage.cashflow import (
    CashFlowError, add_manual_flow, build_cash_flows, validate_category,
)
from construction_os.storage.models import (
    CashFlowRow, CompanyRow, CostArticleRow, PaymentObligationRow, WorkCalendarRow,
)
from construction_os.storage.repositories import CashFlowRepository, ContractRepository

D = Decimal
T = date.fromisoformat


def seed(session, suffix="A"):
    company = CompanyRow(name="CF-" + suffix)
    session.add(company)
    session.flush()
    if session.scalar(select(WorkCalendarRow.id).where(
        WorkCalendarRow.cal_date == T("2026-09-29")
    )) is None:
        session.add_all(WorkCalendarRow(**row) for row in iter_calendar_days(2026))
    for code in ("MAT", "LAB", "SUB"):
        if session.scalar(select(CostArticleRow.id).where(
            CostArticleRow.code == code
        )) is None:
            session.add(CostArticleRow(
                code=code, category="direct", name=code, is_active=True
            ))
    session.flush()
    contract = ContractRepository(session).add(
        company.id, contract_type="government", number="N-" + suffix,
        signed_on=T("2026-08-01"), price_is_final=True,
        valid_from=T("2026-08-01"),
    )
    act, obligation, _ = create_act(
        session, company.id, contract, "CF1", D("1000000"),
        T("2026-09-01"), signed_on=T("2026-09-29"), via_eis=True,
    )
    return company, contract, act, obligation


@pytest.mark.parametrize("direction,category,expected", [
    ("inflow", "bad", "unknown inflow category: bad"),
    ("outflow", "bad", "unknown outflow category: bad"),
])
def test_F2_category_errors(sqlite_session, direction, category, expected):
    seed(sqlite_session)
    with pytest.raises(CashFlowError, match=expected):
        validate_category(sqlite_session, direction, category)


def test_CF1_build_is_idempotent(sqlite_session):
    company, _, _, obligation = seed(sqlite_session)
    first = build_cash_flows(sqlite_session, company.name)
    second = build_cash_flows(sqlite_session, company.name)
    assert (first.created, first.existed) == (1, 0)
    assert (second.created, second.existed) == (0, 1)
    row = sqlite_session.scalar(select(CashFlowRow))
    assert row.amount == D("1000000")
    assert row.flow_date == T("2026-10-08")
    assert row.plan_or_fact == "plan"
    assert row.source_id == obligation.id


def test_CF3_retention_unknown_return_date(sqlite_session):
    company, contract, _, _ = seed(sqlite_session)
    ContractRepository(sqlite_session).supersede(
        company.id, contract.id,
        {"warranty_retention_pct": D("0.05")},
        "retention", "test", T("2026-09-01"),
    )
    result = build_cash_flows(sqlite_session, company.name)
    flow = sqlite_session.scalar(select(CashFlowRow))
    assert flow.amount == D("950000.00")
    assert any("50000.00" in w and "неизвестна" in w for w in result.warnings)


def test_CF4_payment_fact_and_new_obligation_version(sqlite_session):
    company, _, _, obligation = seed(sqlite_session)
    build_cash_flows(sqlite_session, company.name)
    new = register_payment(
        sqlite_session, company.id, obligation,
        T("2026-10-20"), D("1000000"),
    )
    result = build_cash_flows(sqlite_session, company.name)
    active = list(sqlite_session.scalars(select(CashFlowRow).where(
        CashFlowRow.company_id == company.id, CashFlowRow.valid_to.is_(None)
    )))
    assert result.created == 1
    assert len(active) == 1
    assert active[0].source_id == new.id
    assert active[0].flow_date == T("2026-10-20")
    assert active[0].plan_or_fact == "fact"
    assert build_cash_flows(sqlite_session, company.name).existed == 1


def test_manual_duplicate_allowed_and_provenance(sqlite_session):
    from construction_os.storage.models import ValueRefRow
    company, contract, _, _ = seed(sqlite_session)
    for _ in range(2):
        add_manual_flow(
            sqlite_session, company.id, T("2026-09-15"),
            "outflow", D("600000"), "MAT", contract_id=contract.id,
        )
    rows = list(sqlite_session.scalars(select(CashFlowRow).where(
        CashFlowRow.source_kind.is_(None)
    )))
    assert len(rows) == 2
    for row in rows:
        assert sqlite_session.scalar(select(func.count()).select_from(ValueRefRow).where(
            ValueRefRow.entity_id == row.id, ValueRefRow.entity_name == "cash_flows"
        )) == 5


def test_manual_company_isolation(sqlite_session):
    a, ca, _, _ = seed(sqlite_session, "A")
    b, cb, _, _ = seed(sqlite_session, "B")
    add_manual_flow(
        sqlite_session, a.id, T("2026-09-15"),
        "outflow", D("10"), "MAT", contract_id=ca.id,
    )
    assert CashFlowRepository(sqlite_session).list_current(b.id) == []
    with pytest.raises(PermissionError, match="company mismatch"):
        add_manual_flow(
            sqlite_session, b.id, T("2026-09-15"),
            "outflow", D("10"), "MAT", contract_id=ca.id,
        )


def test_advance_not_invented(sqlite_session):
    company, contract, _, _ = seed(sqlite_session)
    ContractRepository(sqlite_session).supersede(
        company.id, contract.id,
        {"advance_pct": D("0.30")},
        "advance", "test", T("2026-09-01"),
    )
    result = build_cash_flows(sqlite_session, company.name)
    assert any("нет цены контракта" in w for w in result.warnings)
    assert sqlite_session.scalar(select(func.count()).select_from(CashFlowRow)) == 1


@pytest.mark.parametrize(
    "field,value,constraint",
    [
        ("direction", "bad", "ck_cash_flow_direction"),
        ("amount", D("0"), "ck_cash_flow_amount_positive"),
        ("plan_or_fact", "bad", "ck_cash_flow_plan_fact"),
        ("source_kind", "payment_obligation", "ck_cash_flow_source_pair"),
        ("source_id", "non-null", "ck_cash_flow_source_pair"),
    ],
)
def test_F2_named_checks_both_databases(db_session, field, value, constraint):
    from uuid import uuid4

    company = CompanyRow(name="CF-CHECK-" + field)
    db_session.add(company)
    db_session.flush()
    values = {
        "company_id": company.id,
        "flow_date": T("2026-09-15"),
        "direction": "outflow",
        "amount": D("1"),
        "category": "other_outflow",
        "plan_or_fact": "fact",
        "valid_from": T("2026-09-15"),
    }
    values[field] = uuid4() if value == "non-null" else value
    with pytest.raises(IntegrityError, match=constraint), db_session.begin_nested():
        db_session.add(CashFlowRow(**values))
        db_session.flush()


def test_auto_source_unique_both_databases(db_session):
    from uuid import uuid4

    company = CompanyRow(name="CF-UNIQUE")
    db_session.add(company)
    db_session.flush()
    src = uuid4()
    values = {
        "company_id": company.id,
        "flow_date": T("2026-09-15"),
        "direction": "inflow",
        "amount": D("1"),
        "category": "act_payment",
        "plan_or_fact": "plan",
        "source_kind": "payment_obligation",
        "source_id": src,
        "valid_from": T("2026-09-15"),
    }
    db_session.add(CashFlowRow(**values))
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(CashFlowRow(**values))
        db_session.flush()


def test_postgres_cashflow_immutable(db_session):
    if db_session.bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL-only immutable trigger")
    company = CompanyRow(name="CF-TRIGGER")
    db_session.add(company)
    db_session.flush()
    row = CashFlowRow(
        company_id=company.id, flow_date=T("2026-09-15"),
        direction="outflow", amount=D("10"), category="other_outflow",
        plan_or_fact="fact", valid_from=T("2026-09-15"),
    )
    db_session.add(row)
    db_session.flush()
    with pytest.raises(Exception, match="cash_flows immutable"), db_session.begin_nested():
        db_session.execute(text("UPDATE cash_flows SET amount=11 WHERE id=:id"), {
            "id": str(row.id),
        })
