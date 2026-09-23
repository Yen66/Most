from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from construction_os.calc.acts import signing_deadline
from construction_os.calc.penalty import calculate_penalty
from construction_os.domain.calendar import CalendarNotCoveredError
from construction_os.money.core import money
from construction_os.storage.acts import (
    ActFlowError,
    create_act,
    current_obligation,
    find_act,
    find_company,
    find_contract,
    register_payment,
)
from construction_os.storage.calendar import DbCalendar
from construction_os.storage.models import AcceptanceActRow, ContractRow


def configure_acts(sub) -> None:
    acts = sub.add_parser("acts")
    actions = acts.add_subparsers(dest="acts_command", required=True)
    add = actions.add_parser("add")
    add.add_argument("--company", required=True)
    add.add_argument("--contract-number", required=True)
    add.add_argument("--act-number", required=True)
    add.add_argument("--amount-gross", type=Decimal, required=True)
    add.add_argument("--placed-on", type=date.fromisoformat, required=True)
    add.add_argument("--signed-on", type=date.fromisoformat)
    add.add_argument("--refusal-on", type=date.fromisoformat)
    add.add_argument("--refusal-reason")
    eis = add.add_mutually_exclusive_group()
    eis.add_argument("--via-eis", action="store_true", dest="via_eis")
    eis.add_argument("--no-eis", action="store_false", dest="via_eis")
    add.set_defaults(via_eis=None)
    add.add_argument("--period-from", type=date.fromisoformat)
    add.add_argument("--period-to", type=date.fromisoformat)
    pay = actions.add_parser("pay")
    pay.add_argument("--company", required=True)
    pay.add_argument("--contract-number", required=True)
    pay.add_argument("--act-number", required=True)
    pay.add_argument("--paid-on", type=date.fromisoformat, required=True)
    pay.add_argument("--amount", type=Decimal, required=True)
    listing = actions.add_parser("list")
    listing.add_argument("--company", required=True)
    report = actions.add_parser("report")
    report.add_argument("--company", required=True)
    report.add_argument("--contract-number")
    report.add_argument("--as-of", type=date.fromisoformat, default=date.today())


def run_acts(args, session) -> int:
    try:
        company = find_company(session, args.company)
        if args.acts_command == "add":
            contract = find_contract(session, company.id, args.contract_number)
            act, obligation, warnings = create_act(
                session,
                company.id,
                contract,
                args.act_number,
                args.amount_gross,
                args.placed_on,
                signed_on=args.signed_on,
                refusal_on=args.refusal_on,
                refusal_reason=args.refusal_reason,
                via_eis=args.via_eis,
                period_from=args.period_from,
                period_to=args.period_to,
            )
            session.commit()
            print(f"Акт {act.act_number}: {act.status}; сумма {money(act.amount_gross)}")
            deadline = signing_deadline(act.placed_on, DbCalendar(session).is_working)
            print(f"Срок подписания: {deadline}")
            if obligation is not None:
                print(
                    f"Обязательство: {money(obligation.amount)}; "
                    f"due_on={obligation.due_on}; basis={obligation.term_basis}"
                )
            for warning in warnings:
                print(f"ПРЕДУПРЕЖДЕНИЕ: {warning}")
            if act.via_eis is None and obligation is None:
                print("ПРЕДУПРЕЖДЕНИЕ: via_eis: нет данных — принято ЕИС-актирование")
            return 0
        if args.acts_command == "pay":
            contract = find_contract(session, company.id, args.contract_number)
            act = find_act(session, company.id, args.act_number, contract.id)
            obligation = current_obligation(session, company.id, act.id)
            if obligation is None:
                raise LookupError("нет данных: обязательство оплаты")
            paid = register_payment(
                session, company.id, obligation, args.paid_on, args.amount
            )
            session.commit()
            print(
                f"Оплата акта {act.act_number}: {money(paid.paid_amount)}; "
                f"дата {paid.paid_on}; остаток {money(paid.amount - paid.paid_amount)}"
            )
            return 0
        if args.acts_command == "list":
            rows = session.scalars(
                select(AcceptanceActRow).where(
                    AcceptanceActRow.company_id == company.id,
                    AcceptanceActRow.valid_to.is_(None),
                ).order_by(AcceptanceActRow.act_number)
            )
            for row in rows:
                print(f"{row.act_number}: {row.status}; {money(row.amount_gross)}")
            return 0
        contract_id = None
        if args.contract_number:
            contract_id = find_contract(session, company.id, args.contract_number).id
        query = select(AcceptanceActRow).where(
            AcceptanceActRow.company_id == company.id,
            AcceptanceActRow.valid_to.is_(None),
        )
        if contract_id is not None:
            query = query.where(AcceptanceActRow.contract_id == contract_id)
        for act in session.scalars(query.order_by(AcceptanceActRow.act_number)):
            cal = DbCalendar(session)
            deadline = signing_deadline(act.placed_on, cal.is_working)
            delta = (deadline - args.as_of).days
            status = (
                f"осталось {delta} календ. дн."
                if delta >= 0 else f"просрочено {-delta} календ. дн."
            )
            print(
                f"Акт {act.act_number}: {act.status}; сумма {money(act.amount_gross)}; "
                f"срок подписания {deadline} ({status}); "
                f"подписан {act.signed_on or 'нет данных'}"
            )
            previous_refusal = session.scalar(
                select(AcceptanceActRow).where(
                    AcceptanceActRow.company_id == company.id,
                    AcceptanceActRow.contract_id == act.contract_id,
                    AcceptanceActRow.act_number == act.act_number,
                    AcceptanceActRow.status == "refused",
                    AcceptanceActRow.valid_to.is_not(None),
                )
            )
            if previous_refusal is not None and act.status == "placed":
                print(f"срок сброшен: новый акт от {act.placed_on}")
            obligation = current_obligation(session, company.id, act.id)
            if obligation is None:
                print("Оплата: обязательство не возникло")
                continue
            paid = obligation.paid_amount or Decimal("0")
            contract = session.get(ContractRow, act.contract_id)
            penalty = calculate_penalty(
                obligation.amount, obligation.due_on,
                as_of=args.as_of, paid_on=obligation.paid_on,
                paid_amount=obligation.paid_amount,
                penalty_cap_pct=contract.penalty_cap_pct,
            )
            print(f"Пеня: {money(penalty.total)}")
            print(
                f"Оплата: due_on={obligation.due_on}; basis={obligation.term_basis}; "
                f"оплачено={money(paid)}; осталось={money(obligation.amount - paid)}; "
                f"просрочка={'да' if args.as_of > obligation.due_on and paid < obligation.amount else 'нет'}"
            )
        return 0
    except (LookupError, ActFlowError, CalendarNotCoveredError, ValueError) as error:
        session.rollback()
        print(str(error))
        return 2
