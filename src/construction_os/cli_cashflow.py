"""CLI cash-flow build, manual input and dated gap reporting."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from construction_os.calc.cashflow import Flow, daily_balances, financing_cost, gap_report
from construction_os.money import money
from construction_os.references import RateType, get_rate
from construction_os.storage.acts import find_company, find_contract
from construction_os.storage.cashflow import (
    CashFlowError,
    add_manual_flow,
    build_cash_flows,
    contract_ids,
    manual_plan_override,
    missing_information,
)
from construction_os.storage.models import CashFlowRow, ContractRow, PaymentObligationRow


def configure_cashflow(sub) -> None:
    commands = sub.add_parser("cash-flow").add_subparsers(
        dest="cashflow_command", required=True
    )
    p = commands.add_parser("build")
    p.add_argument("--company", required=True)
    p.add_argument("--contract-number")
    p.add_argument("--actor", default="cli")
    p = commands.add_parser("add")
    p.add_argument("--company", required=True)
    p.add_argument("--date", type=date.fromisoformat, required=True)
    p.add_argument("--direction", choices=["in", "out"], required=True)
    p.add_argument("--amount", type=Decimal, required=True)
    p.add_argument("--category", required=True)
    p.add_argument("--contract-number")
    p.add_argument("--note")
    p.add_argument("--plan", action="store_true")
    p.add_argument("--actor", default="cli")
    p = commands.add_parser("report")
    p.add_argument("--company", required=True)
    p.add_argument("--contract-number")
    p.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    p.add_argument("--rate", type=Decimal)


def run_cashflow(args, session) -> int:
    try:
        company = find_company(session, args.company)
        if args.cashflow_command == "build":
            result = build_cash_flows(
                session, args.company, args.contract_number, args.actor
            )
            session.commit()
            print(f"создано: {result.created}, существует: {result.existed}")
            for warning in result.warnings:
                print(f"нет данных: {warning}")
            return 0
        if args.cashflow_command == "add":
            contract = (
                find_contract(session, company.id, args.contract_number)
                if args.contract_number else None
            )
            row = add_manual_flow(
                session, company.id, args.date,
                "inflow" if args.direction == "in" else "outflow",
                args.amount, args.category,
                contract_id=contract.id if contract else None,
                note=args.note, force_plan=args.plan, actor=args.actor,
            )
            session.commit()
            print(f"Добавлен поток {row.id}: {row.flow_date} {row.direction} {money(row.amount)}")
            return 0
        ids = contract_ids(session, company.id, args.contract_number)
        query = select(CashFlowRow).where(
            CashFlowRow.company_id == company.id,
            CashFlowRow.valid_to.is_(None),
        )
        if ids is not None:
            query = query.where(CashFlowRow.contract_id.in_(ids))
        rows = list(session.scalars(query.order_by(
            CashFlowRow.flow_date, CashFlowRow.direction, CashFlowRow.id
        )))
        print(f"Денежные потоки: {company.name}; as_of={args.as_of}")
        if not rows:
            print("нет данных")
            return 0
        first = rows[0].flow_date
        if args.as_of < first:
            raise CashFlowError("cash-flow report: as_of earlier than first flow")
        flows = []
        for row in rows:
            status = row.plan_or_fact
            if row.source_kind is None and not manual_plan_override(
                session, company.id, row.id
            ):
                status = "fact" if row.flow_date <= args.as_of else "plan"
            flows.append(Flow(
                row.flow_date, row.direction, row.amount, row.category,
                status, row.source_kind,
            ))
        inside = [f for f in flows if f.flow_date <= args.as_of]
        future = [f for f in flows if f.flow_date > args.as_of]
        print("Дата | направление | сумма | категория | план/факт | источник")
        for flow in inside:
            print(
                f"{flow.flow_date} | {flow.direction} | {flow.amount:.2f} | "
                f"{flow.category} | {flow.plan_or_fact} | "
                f"{flow.source_kind or 'USER_INPUT'}"
            )
        balances = daily_balances(inside, first, args.as_of)
        gap = gap_report(balances)
        print(f"Баланс на {args.as_of}: {balances[-1].balance:+.2f}")
        print("## За горизонтом (план)")
        if not future:
            print("нет")
        for flow in future:
            print(f"{flow.flow_date} | {flow.direction} | {flow.amount:.2f} | {flow.category} | plan")
        print("## КАССОВЫЙ РАЗРЫВ")
        print(f"Первый минус: {gap.first_negative_date or 'нет'}")
        print(
            f"Максимальный разрыв: {gap.max_deficit:.2f}; "
            f"первая дата: {gap.max_deficit_date or 'нет'}"
        )
        print(f"Дней в минусе: {gap.deficit_days}")
        print(
            f"Выход в плюс: {gap.recovered_date}"
            if gap.recovered_date is not None else (
                f"не закрыт к {args.as_of}" if gap.deficit_days else "разрыва нет"
            )
        )
        if args.rate is None:
            selected = get_rate(RateType.KEY_RATE, args.as_of)
            rate = selected.value
            passport = (
                f"KEY_RATE {selected.value} от {selected.valid_from}; "
                f"документ {selected.document_number or 'нет данных'}"
            )
        else:
            rate = args.rate
            passport = f"USER_INPUT {rate}; as_of={args.as_of}"
        print(
            f"Финансирование [ОЦЕНКА]: {financing_cost(balances, rate):.2f}; "
            f"ставка: {passport}; дней календарных"
        )
        print("## Нет данных")
        warnings = missing_information(session, company.id, ids)
        for row in rows:
            if row.source_kind != "payment_obligation":
                continue
            # Current contract version controls withholding assumptions.
            contract = session.get(ContractRow, row.contract_id)
            if contract is not None and contract.warranty_retention_pct:
                obligation = session.get(PaymentObligationRow, row.source_id)
                if obligation is not None:
                    withheld = money(obligation.amount - row.amount)
                    warnings.append(
                        f"гарантийное удержание {withheld} — дата возврата неизвестна"
                    )
        if not warnings:
            print("нет")
        for warning in dict.fromkeys(warnings):
            print(warning)
        return 0
    except (CashFlowError, LookupError, ValueError) as error:
        session.rollback()
        print(str(error))
        return 2
