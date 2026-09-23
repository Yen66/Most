from __future__ import annotations

from datetime import date

from construction_os.domain.calendar import WorkingLookup, add_working_days

SIGNING_MAX_WORKDAYS = 20  # 44-FZ article 94 part 13(4)
PAYMENT_EIS_WORKDAYS = 7  # 44-FZ article 34 part 13.1
PAYMENT_EXCEPTION_WORKDAYS = 10  # 44-FZ article 34 part 13.1(2)-(3)
LONG_CONTRACT_WARNING = (
    "договорной срок оплаты превышает максимальный по ч. 13.1 ст. 34 44-ФЗ — "
    "проверьте данные договора"
)
UNKNOWN_EIS_WARNING = "via_eis: нет данных — принято ЕИС-актирование"


def signing_deadline(placed_on: date, cal: WorkingLookup) -> date:
    """Maximum signing period, 44-FZ article 94 part 13(4)."""
    return add_working_days(placed_on, SIGNING_MAX_WORKDAYS, cal)


def payment_term(contract, via_eis: bool | None, warnings: list[str] | None = None):
    """Workday terms, 44-FZ article 34 part 13.1; no guessed contract terms."""
    notes = warnings if warnings is not None else []
    if via_eis is None:
        notes.append(UNKNOWN_EIS_WARNING)
    if contract.payment_delay_days is not None:
        days = contract.payment_delay_days
        if days <= 0:
            raise ValueError("payment_delay_days must be positive")
        if days > PAYMENT_EXCEPTION_WORKDAYS:
            notes.append(LONG_CONTRACT_WARNING)
        return days, "contract"
    if contract.treasury_account is True:
        return PAYMENT_EXCEPTION_WORKDAYS, "law_treasury_10"
    if via_eis is False:
        return PAYMENT_EXCEPTION_WORKDAYS, "law_non_eis_10"
    return PAYMENT_EIS_WORKDAYS, "law_eis_7"


def payment_deadline(signed_on: date, term_workdays: int, cal: WorkingLookup) -> date:
    """Payment term begins the day AFTER signing (GK article 191)."""
    return add_working_days(signed_on, term_workdays, cal)
