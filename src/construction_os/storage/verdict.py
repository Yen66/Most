from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select

from construction_os.calc.verdict import (
    BidRow,
    Completeness,
    bid_grid,
    cost_completeness,
    traffic_light,
    vat_warnings,
)
from construction_os.references import RateType, get_rate
from construction_os.storage.economics import EconomicsReport, load_economics_report

from .models import ContractRow, CostArticleRow, CostEntryRow, ObjectRow, WorkItemRow
from .queries import object_lineage_ids


@dataclass(frozen=True, slots=True)
class ObjectVerdict:
    report: EconomicsReport
    positions: int
    bids: tuple[BidRow, ...]
    completeness: Completeness
    article_names: dict[str, str]
    warnings: tuple[str, ...]
    status: str | None


def resolve_contract(session, company_id, obj: ObjectRow) -> ContractRow | None:
    """Only infer a named contract when exactly one active object and one named contract exist."""
    if obj.contract_id is not None:
        linked = session.get(ContractRow, obj.contract_id)
        if linked is not None and linked.number and linked.valid_to is None:
            return linked
    objects = list(
        session.scalars(
            select(ObjectRow).where(
                ObjectRow.company_id == company_id, ObjectRow.valid_to.is_(None)
            )
        )
    )
    named = list(
        session.scalars(
            select(ContractRow).where(
                ContractRow.company_id == company_id,
                ContractRow.number.is_not(None),
                ContractRow.valid_to.is_(None),
            )
        )
    )
    if len(objects) == 1 and len(named) == 1:
        return named[0]
    return session.get(ContractRow, obj.contract_id) if obj.contract_id else None


def load_verdict(session, company_name: str, object_name: str, on_date: date) -> ObjectVerdict:
    try:
        report = load_economics_report(session, company_name, object_name, on_date)
    except LookupError as exc:
        raise LookupError(f"нет данных: объект {object_name} компании {company_name}") from exc
    lineage = object_lineage_ids(session, report.object_row)
    works = list(
        session.scalars(
            select(WorkItemRow)
            .where(
                WorkItemRow.company_id == report.company.id,
                WorkItemRow.object_id.in_(lineage),
                WorkItemRow.valid_to.is_(None),
            )
            .order_by(WorkItemRow.position_no)
        )
    )
    contract = resolve_contract(session, report.company.id, report.object_row)
    from dataclasses import replace

    report = replace(report, contract=contract)
    bids = bid_grid(
        [work.amount_gross for work in works],
        report.vat_rate,
        contract.award_reduction_factor if contract is not None else None,
    )
    catalog = list(
        session.scalars(
            select(CostArticleRow)
            .where(CostArticleRow.is_active.is_(True))
            .order_by(CostArticleRow.sort_order, CostArticleRow.code)
        )
    )
    present = set(
        session.scalars(
            select(CostEntryRow.article_code).where(
                CostEntryRow.company_id == report.company.id,
                CostEntryRow.object_id.in_(lineage),
                CostEntryRow.valid_to.is_(None),
            )
        )
    )
    completeness = cost_completeness(present, [article.code for article in catalog])
    status = (
        traffic_light(report.profit.profit_before_tax, report.revenue_net)
        if report.profit is not None
        else None
    )
    return ObjectVerdict(
        report,
        len(works),
        bids,
        completeness,
        {article.code: article.name for article in catalog},
        vat_warnings(
            {work.vat_rate for work in works}, get_rate(RateType.VAT_RATE, on_date).value, on_date
        ),
        status,
    )
