from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from construction_os.domain import Company, WorkItem
from construction_os.storage.models import CompanyRow, ObjectRow, ValueSourceRow
from construction_os.storage.repositories import ImmutableRecordError, WorkItemRepository


def _seed_work_item(session):
    company = CompanyRow(name="A")
    session.add(company)
    session.flush()
    source = ValueSourceRow(company_id=company.id, source_type="document", confidence="exact")
    session.add(source)
    session.flush()
    obj = ObjectRow(company_id=company.id, name="O")
    session.add(obj)
    session.flush()
    repo = WorkItemRepository(session)
    item = repo.add(
        company.id,
        object_id=obj.id,
        position_no=1,
        name="Работа",
        unit="шт",
        quantity=Decimal("2"),
        price_gross=Decimal("10.00"),
        amount_gross=Decimal("20.00"),
        vat_rate=Decimal("0.22"),
        source_id=source.id,
        valid_from=date(2026, 1, 1),
    )
    return company, source, obj, repo, item


def test_domain_company_is_plain_dataclass():
    company = Company("Компания")
    assert company.name == "Компания"


def test_domain_work_item_decimal():
    item = WorkItem(uuid4(), uuid4(), 1, "Работа", "шт", Decimal("1"), Decimal("2"), Decimal("2"), Decimal("0.22"), uuid4(), date(2026, 1, 1))
    assert item.amount_gross == Decimal("2")


def test_repository_add(sqlite_session):
    _, _, _, _, item = _seed_work_item(sqlite_session)
    assert item.position_no == 1


def test_repository_get(sqlite_session):
    company, _, _, repo, item = _seed_work_item(sqlite_session)
    assert repo.get(company.id, item.id).id == item.id


def test_repository_company_filter(sqlite_session):
    company, _, obj, repo, _ = _seed_work_item(sqlite_session)
    assert len(repo.list_current(company.id, object_id=obj.id)) == 1
    assert repo.list_current(uuid4(), object_id=obj.id) == []


def test_repository_update_forbidden(sqlite_session):
    _, _, _, repo, item = _seed_work_item(sqlite_session)
    with pytest.raises(ImmutableRecordError):
        repo.update(item.id)


def test_repository_delete_forbidden(sqlite_session):
    _, _, _, repo, item = _seed_work_item(sqlite_session)
    with pytest.raises(ImmutableRecordError):
        repo.delete(item.id)


def test_supersede_creates_new_row(sqlite_session):
    company, _, obj, repo, item = _seed_work_item(sqlite_session)
    new = repo.supersede(company.id, item.id, {"price_gross": Decimal("11.00"), "amount_gross": Decimal("22.00")}, "correction", "tester", date(2026, 2, 1))
    assert new.id != item.id
    assert repo.list_current(company.id, object_id=obj.id)[0].id == new.id


def test_supersede_preserves_old_value_on_date(sqlite_session):
    company, _, _, repo, item = _seed_work_item(sqlite_session)
    repo.supersede(company.id, item.id, {"price_gross": Decimal("11.00")}, "correction", "tester", date(2026, 2, 1))
    old = repo.get_on_date(company.id, item.id, date(2026, 1, 15))
    assert old.price_gross == Decimal("10.00")


def test_supersede_wrong_company_rejected(sqlite_session):
    _, _, _, repo, item = _seed_work_item(sqlite_session)
    with pytest.raises(KeyError):
        repo.supersede(uuid4(), item.id, {}, "bad", "tester", date(2026, 2, 1))
