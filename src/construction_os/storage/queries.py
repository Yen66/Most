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


def object_revenues(session, on_date: date, company_name: str | None = None) -> list[ObjectRevenue]:
    query = select(CompanyRow, ObjectRow).join(ObjectRow, ObjectRow.company_id == CompanyRow.id)
    if company_name is not None:
        query = query.where(CompanyRow.name == company_name)
    rows = session.execute(query.order_by(CompanyRow.name, ObjectRow.name)).all()
    result: list[ObjectRevenue] = []
    for company, object_row in rows:
        total = session.scalar(
            select(func.sum(WorkItemRow.amount_gross)).where(
                WorkItemRow.company_id == company.id,
                WorkItemRow.object_id == object_row.id,
                WorkItemRow.valid_to.is_(None),
            )
        )
        if total is None:
            continue
        result.append(
            ObjectRevenue(
                company_id=company.id,
                company_name=company.name,
                object_id=object_row.id,
                object_name=object_row.name,
                revenue=calculate_revenue_for_date(money(total), on_date),
            )
        )
    return result


def portfolio_revenue(rows: list[ObjectRevenue], on_date: date) -> RevenueResult:
    gross = sum_positions(row.revenue.gross for row in rows)
    return calculate_revenue_for_date(gross, on_date)


def verify_object(session, company_name: str, object_name: str) -> list[tuple[int, str]]:
    object_row = session.scalar(
        select(ObjectRow)
        .join(CompanyRow, CompanyRow.id == ObjectRow.company_id)
        .where(CompanyRow.name == company_name, ObjectRow.name == object_name)
    )
    if object_row is None:
        raise LookupError(f"object not found: {object_name}")
    work_items = list(
        session.scalars(
            select(WorkItemRow).where(
                WorkItemRow.company_id == object_row.company_id,
                WorkItemRow.object_id == object_row.id,
                WorkItemRow.valid_to.is_(None),
            )
        )
    )
    tasks = list(
        session.scalars(
            select(ScheduleTaskRow).where(
                ScheduleTaskRow.company_id == object_row.company_id,
                ScheduleTaskRow.object_id == object_row.id,
            )
        )
    )
    quantities: dict[int, Decimal] = {}
    amounts: dict[int, Decimal] = {}
    for task in tasks:
        if task.position_no is None:
            continue
        quantities[task.position_no] = quantities.get(task.position_no, Decimal("0")) + (
            task.quantity or Decimal("0")
        )
        amounts[task.position_no] = amounts.get(task.position_no, Decimal("0")) + (
            task.amount or Decimal("0")
        )
    differences: list[tuple[int, str]] = []
    for item in work_items:
        if quantities.get(item.position_no, Decimal("0")) != item.quantity:
            differences.append((item.position_no, "quantity"))
        if money(amounts.get(item.position_no, Decimal("0"))) != money(item.amount_gross):
            differences.append((item.position_no, "amount"))
    return differences
