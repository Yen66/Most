from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID
from sqlalchemy import func, select
from construction_os.calc import RevenueResult, calculate_revenue_for_date
from construction_os.money import money, sum_positions
from .models import CompanyRow, ObjectRow, ScheduleTaskRow, WorkItemRow


@dataclass(frozen=True, slots=True)
class ObjectRevenue:
    company_id: UUID
    company_name: str
    object_id: UUID
    object_name: str
    revenue: RevenueResult


def object_lineage_ids(session, current: ObjectRow) -> set[UUID]:
    ids = {current.id}
    frontier = {current.id}
    while frontier:
        parents = list(
            session.scalars(select(ObjectRow).where(ObjectRow.superseded_by.in_(frontier)))
        )
        new_ids = {row.id for row in parents} - ids
        if not new_ids:
            break
        ids.update(new_ids)
        frontier = new_ids
    return ids


def object_revenues(session, on_date: date, company_name: str | None = None) -> list[ObjectRevenue]:
    query = (
        select(CompanyRow, ObjectRow)
        .join(ObjectRow, ObjectRow.company_id == CompanyRow.id)
        .where(ObjectRow.valid_to.is_(None))
    )
    if company_name is not None:
        query = query.where(CompanyRow.name == company_name)
    result = []
    for company, obj in session.execute(query.order_by(CompanyRow.name, ObjectRow.name)).all():
        lineage = object_lineage_ids(session, obj)
        total = session.scalar(
            select(func.sum(WorkItemRow.amount_gross)).where(
                WorkItemRow.company_id == company.id,
                WorkItemRow.object_id.in_(lineage),
                WorkItemRow.valid_to.is_(None),
            )
        )
        if total is not None:
            result.append(
                ObjectRevenue(
                    company.id,
                    company.name,
                    obj.id,
                    obj.name,
                    calculate_revenue_for_date(money(total), on_date),
                )
            )
    return result


def portfolio_revenue(rows: list[ObjectRevenue], on_date: date) -> RevenueResult:
    return calculate_revenue_for_date(sum_positions(row.revenue.gross for row in rows), on_date)


def verify_object(session, company_name: str, object_name: str) -> list[tuple[int, str]]:
    obj = session.scalar(
        select(ObjectRow)
        .join(CompanyRow, CompanyRow.id == ObjectRow.company_id)
        .where(
            CompanyRow.name == company_name,
            ObjectRow.name == object_name,
            ObjectRow.valid_to.is_(None),
        )
    )
    if obj is None:
        raise LookupError(f"object not found: {object_name}")
    lineage = object_lineage_ids(session, obj)
    work = list(
        session.scalars(
            select(WorkItemRow).where(
                WorkItemRow.company_id == obj.company_id,
                WorkItemRow.object_id.in_(lineage),
                WorkItemRow.valid_to.is_(None),
            )
        )
    )
    tasks = list(
        session.scalars(
            select(ScheduleTaskRow).where(
                ScheduleTaskRow.company_id == obj.company_id,
                ScheduleTaskRow.object_id.in_(lineage),
                ScheduleTaskRow.valid_to.is_(None),
            )
        )
    )
    quantities = {}
    amounts = {}
    for task in tasks:
        if task.position_no is None:
            continue
        quantities[task.position_no] = quantities.get(task.position_no, Decimal("0")) + (
            task.quantity or Decimal("0")
        )
        amounts[task.position_no] = amounts.get(task.position_no, Decimal("0")) + (
            task.amount or Decimal("0")
        )
    differences = []
    for item in work:
        if quantities.get(item.position_no, Decimal("0")) != item.quantity:
            differences.append((item.position_no, "quantity"))
        if money(amounts.get(item.position_no, Decimal("0"))) != money(item.amount_gross):
            differences.append((item.position_no, "amount"))
    return differences
