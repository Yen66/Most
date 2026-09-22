from __future__ import annotations
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from construction_os.calc import CostArticle, ScenarioParam, validate_scenario_param
from construction_os.references import SourceType
from .models import CostArticleRow, ScenarioParamRow, ScenarioRow, ValueRefRow, ValueSourceRow
from .repositories import ScenarioRepository


def create_scenario(
    session,
    company_id,
    name: str,
    object_id,
    contract_id,
    base_date: date,
    params: list[ScenarioParam],
    actor: str,
    note: str | None = None,
) -> ScenarioRow:
    if not params:
        raise ValueError("сценарий без параметров: сравнивать не с чем")
    rows = list(session.scalars(select(CostArticleRow).where(CostArticleRow.is_active.is_(True))))
    articles = {r.code: CostArticle(r.code, r.category, r.name, r.sort_order) for r in rows}
    for p in params:
        validate_scenario_param(p, articles)
    source = ValueSourceRow(
        company_id=company_id,
        source_type=SourceType.USER_INPUT.value,
        confidence="confirmed",
        note=note,
    )
    session.add(source)
    session.flush()
    scenario = ScenarioRepository(session).add(
        company_id,
        name=name,
        object_id=object_id,
        contract_id=contract_id,
        base_date=base_date,
        note=note,
        source_id=source.id,
        created_by=actor,
        valid_from=base_date,
    )
    for p in params:
        row = ScenarioParamRow(
            company_id=company_id,
            scenario_id=scenario.id,
            param_type=p.param_type,
            scope=p.scope,
            scope_value=p.scope_value,
            param_value=p.param_value,
            created_by=actor,
        )
        session.add(row)
        session.flush()
        session.add(
            ValueRefRow(
                company_id=company_id,
                entity_name="scenario_params",
                entity_id=row.id,
                field_name="param_value",
                source_id=source.id,
            )
        )
    session.flush()
    return scenario


def scenario_params(session, company_id, scenario_id) -> list[ScenarioParam]:
    rows = list(
        session.scalars(
            select(ScenarioParamRow).where(
                ScenarioParamRow.company_id == company_id,
                ScenarioParamRow.scenario_id == scenario_id,
            )
        )
    )
    return [
        ScenarioParam(r.param_type, Decimal(r.param_value), r.scope, r.scope_value) for r in rows
    ]
