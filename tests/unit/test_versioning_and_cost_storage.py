from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from construction_os.storage.models import (
    Base,
    CompanyRow,
    CostArticleRow,
    CostEntryRow,
    ValueSourceRow,
)
from construction_os.storage.repositories import (
    ALL_REPOSITORIES,
    TENANT_REPOSITORIES,
    ContractRepository,
    CostArticleRepository,
    CostEntryRepository,
    DuplicateActiveVersionError,
    InvalidBusinessKeyError,
    ObjectRepository,
    ScenarioRepository,
    ScheduleTaskRepository,
)

D = Decimal


def seed(session):
    c = CompanyRow(name="A")
    session.add(c)
    session.flush()
    src = ValueSourceRow(company_id=c.id, source_type="user_input", confidence="confirmed")
    session.add(src)
    session.flush()
    return c, src


def test_schema_has_18_tables():
    assert len(Base.metadata.tables) == 18


def test_contract_new_fields_types():
    t = Base.metadata.tables["contracts"]
    assert (
        t.c.signed_on.nullable
        and t.c.award_reduction_factor.nullable
        and t.c.award_reduction_factor.type.scale == 6
    )


@pytest.mark.parametrize(
    "table",
    [
        "contracts",
        "objects",
        "work_items",
        "schedule_tasks",
        "cost_entries",
        "scenarios",
        "acceptance_acts",
        "payment_obligations",
    ],
)
def test_versioned_tables_have_four_fields(table):
    assert {"valid_from", "valid_to", "superseded_by", "replace_reason"} <= set(
        Base.metadata.tables[table].c.keys()
    )


def test_cost_articles_are_global():
    assert "company_id" not in Base.metadata.tables["cost_articles"].c


def test_cost_entries_have_no_derived_vat_columns():
    assert {"amount_net", "vat_amount"}.isdisjoint(Base.metadata.tables["cost_entries"].c)


def test_no_fake_rate_tables():
    assert {"vat_rates", "profit_tax_rates", "winter_rates"}.isdisjoint(Base.metadata.tables)


def test_repository_counts():
    assert len(TENANT_REPOSITORIES) == 14 and len(ALL_REPOSITORIES) == 18


def test_cost_article_repository_global():
    assert (
        CostArticleRepository.tenant_scoped is False
        and CostArticleRepository not in TENANT_REPOSITORIES
    )


def test_contract_without_number_and_date_rejected(sqlite_session):
    c, _ = seed(sqlite_session)
    with pytest.raises(InvalidBusinessKeyError, match="договор без номера и без даты"):
        ContractRepository(sqlite_session).add(
            c.id, contract_type="unknown", price_is_final=False, valid_from=date(2026, 1, 1)
        )


def test_contract_duplicate_number_rejected(sqlite_session):
    c, _ = seed(sqlite_session)
    r = ContractRepository(sqlite_session)
    r.add(
        c.id,
        contract_type="unknown",
        number="1",
        signed_on=date(2026, 1, 1),
        price_is_final=False,
        valid_from=date(2026, 1, 1),
    )
    with pytest.raises(DuplicateActiveVersionError, match="contracts"):
        r.add(
            c.id,
            contract_type="unknown",
            number="1",
            signed_on=date(2026, 2, 1),
            price_is_final=False,
            valid_from=date(2026, 2, 1),
        )


def test_contract_null_number_uses_date(sqlite_session):
    c, _ = seed(sqlite_session)
    r = ContractRepository(sqlite_session)
    r.add(
        c.id,
        contract_type="unknown",
        number=None,
        signed_on=date(2026, 1, 1),
        price_is_final=False,
        valid_from=date(2026, 1, 1),
    )
    with pytest.raises(DuplicateActiveVersionError):
        r.add(
            c.id,
            contract_type="unknown",
            number=None,
            signed_on=date(2026, 1, 1),
            price_is_final=False,
            valid_from=date(2026, 1, 1),
        )


def test_contract_supersede_factor(sqlite_session):
    c, _ = seed(sqlite_session)
    r = ContractRepository(sqlite_session)
    old = r.add(
        c.id,
        contract_type="unknown",
        number="1",
        signed_on=date(2026, 1, 1),
        price_is_final=False,
        award_reduction_factor=None,
        valid_from=date(2026, 1, 1),
    )
    new = r.supersede(
        c.id,
        old.id,
        {"award_reduction_factor": D("0.87"), "price_is_final": True},
        "auction",
        "tester",
        date(2026, 2, 1),
    )
    assert (
        old.valid_to == date(2026, 2, 1)
        and old.superseded_by == new.id
        and new.award_reduction_factor == D("0.87")
    )


def test_object_versions_same_name_can_coexist(sqlite_session):
    c, _ = seed(sqlite_session)
    r = ObjectRepository(sqlite_session)
    old = r.add(c.id, name="O", valid_from=date(2026, 1, 1))
    new = r.supersede(
        c.id, old.id, {"location_text": "new"}, "correction", "tester", date(2026, 2, 1)
    )
    assert new.name == old.name


def test_object_third_active_rejected(sqlite_session):
    c, _ = seed(sqlite_session)
    r = ObjectRepository(sqlite_session)
    r.add(c.id, name="O", valid_from=date(2026, 1, 1))
    with pytest.raises(DuplicateActiveVersionError):
        r.add(c.id, name="O", valid_from=date(2026, 2, 1))


def test_schedule_task_supersede(sqlite_session):
    c, src = seed(sqlite_session)
    obj = ObjectRepository(sqlite_session).add(c.id, name="O", valid_from=date(2026, 1, 1))
    r = ScheduleTaskRepository(sqlite_session)
    old = r.add(
        c.id,
        object_id=obj.id,
        position_no=1,
        front=None,
        name="x",
        source_id=src.id,
        valid_from=date(2026, 1, 1),
    )
    new = r.supersede(c.id, old.id, {"days": 2}, "reissue", "tester", date(2026, 2, 1))
    assert new.days == 2 and old.valid_to is not None


def _article(session, code="MAT", category="direct"):
    row = CostArticleRow(code=code, category=category, name=code, is_active=True)
    session.add(row)
    session.flush()
    return row


def _cost_context(session):
    c, src = seed(session)
    obj = ObjectRepository(session).add(c.id, name="O", valid_from=date(2026, 1, 1))
    _article(session)
    return c, src, obj


def test_cost_fixed_shape(sqlite_session):
    c, src, obj = _cost_context(sqlite_session)
    row = CostEntryRepository(sqlite_session).add(
        c.id,
        object_id=obj.id,
        article_code="MAT",
        amount=D("10"),
        amount_type="fixed",
        vat_mode="net",
        source_id=src.id,
        valid_from=date(2026, 1, 1),
        created_by="t",
    )
    assert row.amount == D("10")


@pytest.mark.parametrize(
    "amount,amount_type,rate",
    [
        (None, "fixed", None),
        (D("1"), "fixed", D("0.1")),
        (D("1"), "share_of_revenue", D("0.1")),
        (None, "share_of_revenue", None),
    ],
)
def test_cost_shape_checks(sqlite_session, amount, amount_type, rate):
    c, src, obj = _cost_context(sqlite_session)
    sqlite_session.add(
        CostEntryRow(
            company_id=c.id,
            object_id=obj.id,
            article_code="MAT",
            amount=amount,
            amount_type=amount_type,
            rate_value=rate,
            vat_mode="net",
            source_id=src.id,
            valid_from=date(2026, 1, 1),
            created_by="t",
        )
    )
    with pytest.raises(IntegrityError):
        sqlite_session.flush()


def test_share_of_revenue_stores_null_amount(sqlite_session):
    c, src, obj = _cost_context(sqlite_session)
    row = CostEntryRepository(sqlite_session).add(
        c.id,
        object_id=obj.id,
        article_code="MAT",
        amount=None,
        amount_type="share_of_revenue",
        rate_value=D("0.027"),
        vat_mode="net",
        source_id=src.id,
        valid_from=date(2026, 1, 1),
        created_by="t",
    )
    assert (
        sqlite_session.scalar(select(CostEntryRow.amount).where(CostEntryRow.id == row.id)) is None
    )


def test_cost_supersede(sqlite_session):
    c, src, obj = _cost_context(sqlite_session)
    r = CostEntryRepository(sqlite_session)
    old = r.add(
        c.id,
        object_id=obj.id,
        article_code="MAT",
        amount=D("10"),
        amount_type="fixed",
        vat_mode="net",
        source_id=src.id,
        valid_from=date(2026, 1, 1),
        created_by="t",
    )
    new = r.supersede(c.id, old.id, {"amount": D("11")}, "fix", "tester", date(2026, 2, 1))
    assert old.valid_to and new.amount == D("11")


def test_scenario_param_checks_present():
    names = {c.name for c in Base.metadata.tables["scenario_params"].constraints if c.name}
    assert {
        "ck_scenario_param_type",
        "ck_scenario_param_scope",
        "ck_scenario_scope_all",
        "ck_scenario_scope_specific",
        "ck_scenario_param_positive",
    } <= names


def test_scenario_supersede(sqlite_session):
    c, src = seed(sqlite_session)
    obj = ObjectRepository(sqlite_session).add(c.id, name="O", valid_from=date(2026, 1, 1))
    r = ScenarioRepository(sqlite_session)
    old = r.add(
        c.id,
        name="S",
        object_id=obj.id,
        base_date=date(2026, 1, 1),
        source_id=src.id,
        created_by="t",
        valid_from=date(2026, 1, 1),
    )
    new = r.supersede(c.id, old.id, {"note": "v2"}, "change", "tester", date(2026, 2, 1))
    assert old.valid_to and new.note == "v2"
