from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from construction_os.calc import CostArticle, ScenarioParam, validate_scenario_param
from construction_os.references import DEFAULT_COST_ARTICLES
from construction_os.storage.models import (
    CompanyRow,
    CostArticleRow,
    ObjectRow,
    ScenarioParamRow,
    ValueRefRow,
)
from construction_os.storage.scenarios import create_scenario

D = Decimal


def articles():
    return {c: CostArticle(c, k, n) for c, k, n in DEFAULT_COST_ARTICLES}


def test_schedule_shift_integer():
    validate_scenario_param(ScenarioParam("schedule_shift_days", D("5")), articles())


def test_schedule_shift_fraction_rejected():
    with pytest.raises(ValueError, match="целым"):
        validate_scenario_param(ScenarioParam("schedule_shift_days", D("1.5")), articles())


def test_unknown_cost_item_rejected():
    with pytest.raises(ValueError, match="неизвестная статья"):
        validate_scenario_param(
            ScenarioParam("cost_multiplier", D("1.1"), "cost_item", "BAD"), articles()
        )


def test_unknown_category_rejected():
    with pytest.raises(ValueError, match="неизвестная категория"):
        validate_scenario_param(
            ScenarioParam("cost_multiplier", D("1.1"), "category", "bad"), articles()
        )


def seed(session):
    for i, (code, cat, name) in enumerate(DEFAULT_COST_ARTICLES, 1):
        session.add(
            CostArticleRow(code=code, category=cat, name=name, is_active=True, sort_order=i)
        )
    c = CompanyRow(name="A")
    session.add(c)
    session.flush()
    o = ObjectRow(company_id=c.id, name="O", valid_from=date(2026, 1, 1))
    session.add(o)
    session.flush()
    return c, o


def test_create_scenario_writes_value_ref(sqlite_session):
    c, o = seed(sqlite_session)
    s = create_scenario(
        sqlite_session,
        c.id,
        "S",
        o.id,
        None,
        date(2026, 1, 1),
        [ScenarioParam("cost_multiplier", D("1.1"))],
        "tester",
    )
    ref = sqlite_session.scalar(
        select(ValueRefRow).where(ValueRefRow.entity_name == "scenario_params")
    )
    assert ref is not None and ref.entity_id != s.id


def test_create_scenario_without_params_rejected(sqlite_session):
    c, o = seed(sqlite_session)
    with pytest.raises(ValueError, match="сравнивать не с чем"):
        create_scenario(sqlite_session, c.id, "S", o.id, None, date(2026, 1, 1), [], "tester")


@pytest.mark.parametrize("param_type", ["bad", "cost", "multiplier"])
def test_param_type_db_check(sqlite_session, param_type):
    c, o = seed(sqlite_session)
    from construction_os.storage.models import ScenarioRow, ValueSourceRow

    src = ValueSourceRow(company_id=c.id, source_type="user_input", confidence="confirmed")
    sqlite_session.add(src)
    sqlite_session.flush()
    s = ScenarioRow(
        company_id=c.id,
        name="S",
        object_id=o.id,
        base_date=date(2026, 1, 1),
        source_id=src.id,
        created_by="t",
        valid_from=date(2026, 1, 1),
    )
    sqlite_session.add(s)
    sqlite_session.flush()
    sqlite_session.add(
        ScenarioParamRow(
            company_id=c.id,
            scenario_id=s.id,
            param_type=param_type,
            scope="all",
            scope_value=None,
            param_value=D("1"),
            created_by="t",
        )
    )
    with pytest.raises(IntegrityError):
        sqlite_session.flush()
