"""Cash-flow storage operations; only this module writes cash_flows."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import or_, select

from construction_os.money import money
from construction_os.references import Confidence, SourceType
from construction_os.storage.acts import find_company, find_contract
from construction_os.storage.models import (
    AcceptanceActRow,
    CashFlowRow,
    ContractRow,
    CostArticleRow,
    CostEntryRow,
    ObjectRow,
    PaymentObligationRow,
    ValueRefRow,
    ValueSourceRow,
)
from construction_os.storage.repositories import CashFlowRepository

INFLOW_CATEGORIES = frozenset({
    "advance", "act_payment", "retention_return", "penalty_in", "other_inflow"
})


class CashFlowError(ValueError):
    """Domain validation for cash-flow inputs and reporting windows."""


@dataclass(frozen=True, slots=True)
class BuildResult:
    created: int
    existed: int
    warnings: tuple[str, ...]


def validate_category(session, direction: str, category: str) -> None:
    if direction == "inflow":
        if category not in INFLOW_CATEGORIES:
            raise CashFlowError(f"unknown inflow category: {category}")
    elif direction == "outflow":
        active = session.scalar(select(CostArticleRow).where(
            CostArticleRow.code == category, CostArticleRow.is_active.is_(True)
        ))
        if active is None and category != "other_outflow":
            raise CashFlowError(f"unknown outflow category: {category}")
    else:
        raise CashFlowError(f"unknown direction: {direction}")


def _provenance(session, company_id, row, actor: str, kind: SourceType, force_plan=False):
    source = ValueSourceRow(
        company_id=company_id,
        source_type=kind.value,
        confidence=Confidence.EXACT.value,
        note=f"actor={actor}; forced_plan={int(force_plan)}",
    )
    session.add(source)
    session.flush()
    session.add_all(
        ValueRefRow(
            company_id=company_id,
            entity_name="cash_flows",
            entity_id=row.id,
            field_name=field,
            source_id=source.id,
        )
        for field in ("flow_date", "direction", "amount", "category", "plan_or_fact")
    )


def contract_ids(session, company_id: UUID, number: str | None) -> list[UUID] | None:
    if number is None:
        return None
    find_contract(session, company_id, number)
    return list(session.scalars(select(ContractRow.id).where(
        ContractRow.company_id == company_id, ContractRow.number == number
    )))


def missing_information(session, company_id, contract_filter=None) -> list[str]:
    warnings: list[str] = []
    query = select(ContractRow).where(
        ContractRow.company_id == company_id, ContractRow.valid_to.is_(None)
    )
    if contract_filter is not None:
        query = query.where(ContractRow.id.in_(contract_filter))
    for contract in session.scalars(query):
        if contract.advance_pct is not None:
            warnings.append(
                f"аванс {contract.advance_pct * 100}% — сумма и дата не вычисляются: "
                "нет цены контракта, введите вручную"
            )
    cost_query = select(CostEntryRow).where(
        CostEntryRow.company_id == company_id, CostEntryRow.valid_to.is_(None)
    )
    if contract_filter is not None:
        objects = select(ObjectRow.id).where(
            ObjectRow.company_id == company_id, ObjectRow.contract_id.in_(contract_filter)
        )
        cost_query = cost_query.where(or_(
            CostEntryRow.contract_id.in_(contract_filter),
            CostEntryRow.object_id.in_(objects),
        ))
    cost_rows = list(session.scalars(cost_query))
    if cost_rows:
        total = money(sum(
            (r.amount for r in cost_rows if r.amount is not None), Decimal("0")
        ))
        warnings.append(f"затраты {total} без дат — введите оттоки вручную")
    return warnings


def add_manual_flow(
    session, company_id, flow_date: date, direction: str, amount: Decimal,
    category: str, *, contract_id=None, object_id=None, note=None,
    force_plan=False, actor="cli",
) -> CashFlowRow:
    validate_category(session, direction, category)
    if amount <= 0:
        raise CashFlowError("cash-flow amount must be positive")
    if contract_id is not None:
        contract = session.get(ContractRow, contract_id)
        if contract is None or contract.company_id != company_id:
            raise PermissionError("company mismatch")
    if object_id is not None:
        obj = session.get(ObjectRow, object_id)
        if obj is None or obj.company_id != company_id:
            raise PermissionError("company mismatch")
    row = CashFlowRepository(session).add(
        company_id,
        contract_id=contract_id,
        object_id=object_id,
        flow_date=flow_date,
        direction=direction,
        amount=money(amount),
        category=category,
        plan_or_fact="plan" if force_plan or flow_date > date.today() else "fact",
        note=note,
        valid_from=flow_date,
    )
    _provenance(session, company_id, row, actor, SourceType.USER_INPUT, force_plan)
    session.flush()
    return row


def build_cash_flows(
    session, company_name: str, contract_number: str | None = None, actor: str = "cli"
) -> BuildResult:
    company = find_company(session, company_name)
    ids = contract_ids(session, company.id, contract_number)
    query = (
        select(PaymentObligationRow, AcceptanceActRow)
        .join(AcceptanceActRow, AcceptanceActRow.id == PaymentObligationRow.act_id)
        .where(
            PaymentObligationRow.company_id == company.id,
            PaymentObligationRow.valid_to.is_(None),
            AcceptanceActRow.valid_to.is_(None),
        )
    )
    if ids is not None:
        query = query.where(AcceptanceActRow.contract_id.in_(ids))
    repo = CashFlowRepository(session)
    created = existed = 0
    warnings = missing_information(session, company.id, ids)
    for obligation, act in session.execute(query.order_by(PaymentObligationRow.due_on)):
        old_flow = session.scalar(select(CashFlowRow).where(
            CashFlowRow.company_id == company.id,
            CashFlowRow.source_kind == "payment_obligation",
            CashFlowRow.source_id == obligation.id,
            CashFlowRow.valid_to.is_(None),
        ))
        if old_flow is not None:
            existed += 1
            continue
        historical = session.get(ContractRow, act.contract_id)
        contract = (
            find_contract(session, company.id, historical.number)
            if historical.number is not None else historical
        )
        retention = contract.warranty_retention_pct or Decimal("0")
        amount = money(obligation.amount * (Decimal("1") - retention))
        if amount <= 0:
            warnings.append(f"акт {act.act_number}: удержание 100% — нет притока")
            continue
        if retention:
            withheld = money(obligation.amount - amount)
            warnings.append(
                f"гарантийное удержание {withheld} — дата возврата неизвестна"
            )
        values = {
            "contract_id": contract.id,
            "object_id": act.object_id,
            "flow_date": obligation.paid_on or obligation.due_on,
            "direction": "inflow",
            "amount": amount,
            "category": "act_payment",
            "plan_or_fact": "fact" if obligation.paid_on is not None else "plan",
            "source_kind": "payment_obligation",
            "source_id": obligation.id,
            "note": act.act_number,
        }
        older_ids = list(session.scalars(select(PaymentObligationRow.id).where(
            PaymentObligationRow.company_id == company.id,
            PaymentObligationRow.act_id == obligation.act_id,
            PaymentObligationRow.id != obligation.id,
        )))
        superseded = session.scalar(select(CashFlowRow).where(
            CashFlowRow.company_id == company.id,
            CashFlowRow.source_kind == "payment_obligation",
            CashFlowRow.source_id.in_(older_ids) if older_ids else CashFlowRow.id.is_(None),
            CashFlowRow.valid_to.is_(None),
        ))
        if superseded is not None:
            row = repo.supersede(
                company.id, superseded.id, values, "новая версия обязательства",
                actor, values["flow_date"],
            )
        else:
            row = repo.add(company.id, **values, valid_from=values["flow_date"])
        _provenance(session, company.id, row, actor, SourceType.CALCULATED)
        created += 1
    session.flush()
    return BuildResult(created, existed, tuple(warnings))


def manual_plan_override(session, company_id, flow_id) -> bool:
    source = session.scalar(
        select(ValueSourceRow)
        .join(ValueRefRow, ValueRefRow.source_id == ValueSourceRow.id)
        .where(
            ValueRefRow.company_id == company_id,
            ValueRefRow.entity_name == "cash_flows",
            ValueRefRow.entity_id == flow_id,
            ValueRefRow.field_name == "plan_or_fact",
        )
    )
    return bool(source and source.note and "forced_plan=1" in source.note)
