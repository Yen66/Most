from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from construction_os.storage.models import CompanyRow, ObjectRow, ScheduleTaskRow, ValueSourceRow
from construction_os.storage.queries import object_revenues, verify_object
from construction_os.storage.repositories import ObjectRepository, WorkItemRepository


def _seed_versioned_object(session):
    company = CompanyRow(name="Versioned Co")
    session.add(company)
    session.flush()
    source = ValueSourceRow(company_id=company.id, source_type="document", confidence="exact")
    session.add(source)
    session.flush()
    objects = ObjectRepository(session)
    old = objects.add(company.id, name="Bridge", valid_from=date(2026, 1, 1))
    WorkItemRepository(session).add(
        company.id,
        object_id=old.id,
        position_no=1,
        name="Work",
        unit="шт",
        quantity=Decimal("1"),
        price_gross=Decimal("122"),
        amount_gross=Decimal("122"),
        vat_rate=Decimal("0.22"),
        source_id=source.id,
        valid_from=date(2026, 1, 1),
    )
    session.add(
        ScheduleTaskRow(
            company_id=company.id,
            object_id=old.id,
            position_no=1,
            name="Work",
            unit="шт",
            quantity=Decimal("1"),
            amount=Decimal("122"),
            source_id=source.id,
            valid_from=date(2026, 1, 1),
        )
    )
    session.flush()
    current = objects.supersede(
        company.id,
        old.id,
        {"location_text": "new"},
        "reissue",
        "tester",
        date(2026, 2, 1),
    )
    return company, old, current


def test_versioned_object_does_not_double_portfolio(sqlite_session):
    company, _, current = _seed_versioned_object(sqlite_session)
    rows = object_revenues(sqlite_session, date(2026, 9, 20), company.name)
    assert len(rows) == 1
    assert rows[0].object_id == current.id
    assert rows[0].revenue.gross == Decimal("122.00")


def test_verify_uses_object_lineage(sqlite_session):
    company, _, _ = _seed_versioned_object(sqlite_session)
    assert verify_object(sqlite_session, company.name, "Bridge") == []


@pytest.mark.postgres
@pytest.mark.parametrize("table", ["contracts", "objects", "schedule_tasks"])
def test_postgres_new_versioned_tables_reject_direct_update_delete(db_session, table):
    if db_session.bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL trigger test")
    company, old, _ = _seed_versioned_object(db_session)
    target_id = old.id
    if table == "contracts":
        db_session.execute(
            text("SET LOCAL construction_os.allow_supersede='on'")
        )
        db_session.execute(
            text(
                "INSERT INTO contracts (id, company_id, contract_type, number, price_is_final, currency, valid_from) "
                "VALUES (gen_random_uuid(), :company_id, 'unknown', 'PG-1', false, 'RUB', '2026-01-01')"
            ),
            {"company_id": company.id},
        )
        db_session.execute(text("SET LOCAL construction_os.allow_supersede='off'"))
        target_id = db_session.execute(text("SELECT id FROM contracts WHERE number='PG-1'")).scalar_one()
    elif table == "schedule_tasks":
        target_id = db_session.execute(
            text("SELECT id FROM schedule_tasks WHERE company_id=:company_id LIMIT 1"),
            {"company_id": company.id},
        ).scalar_one()
    with pytest.raises(Exception, match="immutable"), db_session.begin_nested():
        db_session.execute(text(f"UPDATE {table} SET replace_reason='x' WHERE id=:id"), {"id": target_id})
    with pytest.raises(Exception, match="immutable"), db_session.begin_nested():
        db_session.execute(text(f"DELETE FROM {table} WHERE id=:id"), {"id": target_id})
