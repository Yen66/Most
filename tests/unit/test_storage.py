from datetime import date
from decimal import Decimal

import pytest

from construction_os.storage.models import Base, CompanyRow, ObjectRow, ValueSourceRow
from construction_os.storage.repositories import ImmutableRecordError, WorkItemRepository


def seed(s, name):
    c = CompanyRow(name=name)
    s.add(c)
    s.flush()
    o = ObjectRow(company_id=c.id, name="obj")
    v = ValueSourceRow(company_id=c.id, source_type="document", confidence="exact")
    s.add_all([o, v])
    s.flush()
    return c, o, v


def test_company_id_on_tenant_tables():
    excluded = {"companies", "reference_rates"}
    assert all("company_id" in t.c for n, t in Base.metadata.tables.items() if n not in excluded)


def test_company_isolation(sqlite_session):
    c1, o1, s1 = seed(sqlite_session, "A")
    c2, o2, s2 = seed(sqlite_session, "B")
    r = WorkItemRepository(sqlite_session)
    for c, o, s, p in [(c1, o1, s1, "10"), (c2, o2, s2, "20")]:
        r.add(
            c.id,
            company_id=c.id,
            object_id=o.id,
            position_no=1,
            name="w",
            unit="u",
            quantity=Decimal("1"),
            price_gross=Decimal(p),
            amount_gross=Decimal(p),
            vat_rate=Decimal("0.22"),
            source_id=s.id,
            valid_from=date(2026, 1, 1),
        )
    assert len(r.list_current(c1.id, o1.id)) == 1 and r.list_current(c1.id, o1.id)[
        0
    ].price_gross == Decimal("10.0000")


def test_supersede(sqlite_session):
    c, o, s = seed(sqlite_session, "A")
    r = WorkItemRepository(sqlite_session)
    old = r.add(
        c.id,
        company_id=c.id,
        object_id=o.id,
        position_no=1,
        name="x",
        unit="т",
        quantity=Decimal("1"),
        price_gross=Decimal("2350"),
        amount_gross=Decimal("2350"),
        vat_rate=Decimal("0.22"),
        source_id=s.id,
        valid_from=date(2026, 9, 1),
    )
    new = r.supersede(
        c.id,
        old.id,
        {"price_gross": Decimal("2480"), "amount_gross": Decimal("2480")},
        "new quote",
        "tester",
        date(2026, 9, 15),
    )
    assert r.list_current(c.id, o.id)[0].id == new.id
    with pytest.raises(ImmutableRecordError):
        r.update(old.id)
