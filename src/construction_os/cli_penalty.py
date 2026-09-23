from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from construction_os.calc.penalty import calculate_penalty
from construction_os.reports import format_money_ru, format_percent
from construction_os.storage.acts import (
    current_obligation,
    find_act,
    find_company,
    find_contract,
)
from construction_os.storage.models import ContractRow


def configure_penalty(sub) -> None:
    parser = sub.add_parser("penalty")
    parser.add_argument("--company", required=True)
    parser.add_argument("--act-number", required=True)
    parser.add_argument("--contract-number")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--rate-date", type=date.fromisoformat)


def run_penalty(args, session: Session) -> int:
    try:
        company = find_company(session, args.company)
        contract = (
            find_contract(session, company.id, args.contract_number)
            if args.contract_number else None
        )
        act = find_act(
            session, company.id, args.act_number,
            contract.id if contract is not None else None,
        )
        if contract is None:
            historical = session.get(ContractRow, act.contract_id)
            contract = find_contract(session, company.id, historical.number)
        obligation = current_obligation(session, company.id, act.id)
        if obligation is None:
            raise LookupError("нет данных: обязательство оплаты")
        result = calculate_penalty(
            obligation.amount, obligation.due_on,
            as_of=args.as_of, paid_on=obligation.paid_on,
            paid_amount=obligation.paid_amount,
            penalty_cap_pct=contract.penalty_cap_pct,
            rate_date=args.rate_date,
        )
        print(
            f"Акт {act.act_number}: долг {format_money_ru(obligation.amount)}; "
            f"due_on={obligation.due_on}; basis={obligation.term_basis}; "
            f"дней просрочки={result.days}"
        )
        if result.days == 0:
            print("просрочки нет, пеня 0,00")
        for i, segment in enumerate(result.segments, 1):
            print(
                f"Сегмент {i}: долг {format_money_ru(segment.debt)}; "
                f"{segment.start}–{segment.end}; дней {segment.days}; "
                f"ставка {format_percent(segment.rate * 100)}; "
                f"пеня {format_money_ru(segment.amount)}"
            )
        print(
            f"Ставка: {format_percent(result.rate_used * 100)}; "
            f"с {result.rate_effective_from}; {result.document_number}"
        )
        for entry in result.rate_history:
            print(
                f"История ставок (справочно): {entry.start}–{entry.end}; "
                f"{format_percent(entry.rate * 100)}; {entry.document_number}"
            )
        if result.cap_value is not None:
            print(
                f"Потолок: {format_money_ru(result.cap_value)}; "
                f"применён={result.cap_applied}; день достижения={result.cap_reached_day}"
            )
        print(f"ИТОГ: {format_money_ru(result.total)}")
        for warning in result.warnings:
            print(f"ПРЕДУПРЕЖДЕНИЕ: {warning}")
        return 0
    except (LookupError, ValueError) as error:
        print(str(error))
        return 2
