from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from construction_os.calc.acts import payment_deadline, payment_term
from construction_os.money.core import money
from construction_os.references import Confidence, SourceType
from construction_os.storage.calendar import DbCalendar
from construction_os.storage.models import (
    AcceptanceActRow,
    CompanyRow,
    ContractRow,
    PaymentObligationRow,
    ValueRefRow,
    ValueSourceRow,
)
from construction_os.storage.repositories import (
    AcceptanceActRepository,
    DuplicateActiveVersionError,
    PaymentObligationRepository,
)


class ActFlowError(ValueError):
    """Invalid status transition or payment payload."""


def validate_act(
    status: str,
    placed_on: date | None,
    signed_on: date | None,
    refusal_on: date | None,
    refusal_reason: str | None,
) -> None:
    if signed_on is not None and refusal_on is not None:
        raise ActFlowError("act cannot be both signed and refused")
    if status == "placed" and placed_on is None:
        raise ActFlowError("act status placed requires placed_on")
    if status == "signed" and signed_on is None:
        raise ActFlowError("act status signed requires signed_on")
    if status == "refused" and not refusal_reason:
        raise ActFlowError("act status refused requires refusal_reason")
    if status == "refused" and refusal_on is None:
        raise ActFlowError("act status refused requires refusal_on")
    if status in {"signed", "refused"} and placed_on is None:
        raise ActFlowError(f"act status {status} requires placed_on")
    if status not in {"placed", "signed", "refused"}:
        raise ActFlowError(f"unknown act status {status}")
    if signed_on is not None and placed_on is not None and signed_on < placed_on:
        raise ActFlowError("signed_on before placed_on")
    if refusal_on is not None and placed_on is not None and refusal_on < placed_on:
        raise ActFlowError("refusal_on before placed_on")


def validate_payment(
    amount: Decimal, paid_on: date | None, paid_amount: Decimal | None
) -> None:
    if paid_amount is not None and paid_on is None:
        raise ActFlowError("paid_amount requires paid_on")
    if paid_on is not None and paid_amount is None:
        raise ActFlowError("paid_on requires paid_amount")
    if paid_amount is not None:
        if paid_amount <= 0:
            raise ActFlowError("paid_amount must be positive")
        if paid_amount > amount:
            raise ActFlowError("paid_amount cannot exceed obligation amount")


def _source(session, company_id: UUID, source_type: SourceType, actor: str):
    source = ValueSourceRow(
        company_id=company_id,
        source_type=source_type.value,
        confidence=Confidence.EXACT.value,
        note=f"actor={actor}",
    )
    session.add(source)
    session.flush()
    return source


def _refs(session, company_id: UUID, entity: str, row_id: UUID, source_id: UUID, fields):
    session.add_all(
        ValueRefRow(
            company_id=company_id,
            entity_name=entity,
            entity_id=row_id,
            field_name=field,
            source_id=source_id,
        )
        for field in fields
    )


def _create_obligation(session, company_id, act, contract, actor):
    warnings: list[str] = []
    term, basis = payment_term(contract, act.via_eis, warnings)
    due = payment_deadline(act.signed_on, term, DbCalendar(session).is_working)
    source = _source(session, company_id, SourceType.CALCULATED, actor)
    row = PaymentObligationRepository(session).add(
        company_id,
        act_id=act.id,
        amount=money(act.amount_gross),
        due_on=due,
        term_workdays=term,
        term_basis=basis,
        valid_from=act.signed_on,
    )
    _refs(
        session, company_id, "payment_obligations", row.id, source.id,
        ("due_on", "term_workdays", "term_basis", "amount"),
    )
    session.flush()
    return row, warnings


def create_act(
    session,
    company_id: UUID,
    contract: ContractRow,
    act_number: str,
    amount_gross: Decimal,
    placed_on: date | None,
    *,
    signed_on: date | None = None,
    refusal_on: date | None = None,
    refusal_reason: str | None = None,
    via_eis: bool | None = None,
    object_id: UUID | None = None,
    period_from: date | None = None,
    period_to: date | None = None,
    actor: str = "cli",
):
    """Create an act or re-place a refused act; caller owns the transaction."""
    status = "signed" if signed_on is not None else (
        "refused" if refusal_on is not None else "placed"
    )
    validate_act(status, placed_on, signed_on, refusal_on, refusal_reason)
    if amount_gross <= 0:
        raise ActFlowError("act amount must be positive")
    if contract.company_id != company_id:
        raise PermissionError("company mismatch")
    repo = AcceptanceActRepository(session)
    active = repo.list_current(
        company_id, contract_id=contract.id, act_number=act_number
    )
    source = _source(session, company_id, SourceType.USER_INPUT, actor)
    values = dict(
        contract_id=contract.id,
        object_id=object_id,
        act_number=act_number,
        amount_gross=money(amount_gross),
        placed_on=placed_on,
        signed_on=signed_on,
        refusal_on=refusal_on,
        refusal_reason=refusal_reason,
        via_eis=via_eis,
        period_from=period_from,
        period_to=period_to,
        status=status,
    )
    if active:
        old = active[0]
        if old.status != "refused" or status != "placed":
            raise DuplicateActiveVersionError(
                f"acceptance_acts: duplicate active version {act_number}"
            )
        act = repo.supersede(
            company_id,
            old.id,
            values,
            "повторное размещение после мотивированного отказа",
            actor,
            placed_on,
        )
    else:
        act = repo.add(company_id, **values, valid_from=placed_on)
    _refs(
        session, company_id, "acceptance_acts", act.id, source.id,
        ("act_number", "amount_gross", "placed_on", "signed_on", "refusal_on",
         "refusal_reason", "via_eis", "period_from", "period_to"),
    )
    obligation, warnings = (None, [])
    if status == "signed":
        obligation, warnings = _create_obligation(
            session, company_id, act, contract, actor
        )
    session.flush()
    return act, obligation, warnings


def change_act_status(
    session,
    company_id: UUID,
    act: AcceptanceActRow,
    *,
    signed_on: date | None = None,
    refusal_on: date | None = None,
    refusal_reason: str | None = None,
    actor: str = "cli",
):
    """Placed → signed/refused by supersede; historical version remains."""
    if act.company_id != company_id or act.status != "placed":
        raise ActFlowError("only placed act can change status")
    status = "signed" if signed_on is not None else "refused"
    validate_act(status, act.placed_on, signed_on, refusal_on, refusal_reason)
    effective_on = signed_on if signed_on is not None else refusal_on
    source = _source(session, company_id, SourceType.USER_INPUT, actor)
    new = AcceptanceActRepository(session).supersede(
        company_id,
        act.id,
        {
            "status": status,
            "signed_on": signed_on,
            "refusal_on": refusal_on,
            "refusal_reason": refusal_reason,
        },
        "подписание акта" if status == "signed" else "мотивированный отказ",
        actor,
        effective_on,
    )
    _refs(
        session, company_id, "acceptance_acts", new.id, source.id,
        ("status", "signed_on", "refusal_on", "refusal_reason"),
    )
    obligation, warnings = (None, [])
    if status == "signed":
        contract = session.get(ContractRow, act.contract_id)
        obligation, warnings = _create_obligation(
            session, company_id, new, contract, actor
        )
    session.flush()
    return new, obligation, warnings


def register_payment(
    session,
    company_id: UUID,
    obligation: PaymentObligationRow,
    paid_on: date | None,
    paid_amount: Decimal | None,
    actor: str = "cli",
):
    validate_payment(obligation.amount, paid_on, paid_amount)
    if obligation.company_id != company_id:
        raise PermissionError("company mismatch")
    if obligation.paid_on is not None:
        raise ActFlowError(
            "оплата уже зарегистрирована; несколько частичных платежей — "
            "задача 13 (график платежей)"
        )
    if paid_on is None:
        raise ActFlowError("paid_on requires paid_amount")
    source = _source(session, company_id, SourceType.USER_INPUT, actor)
    new = PaymentObligationRepository(session).supersede(
        company_id,
        obligation.id,
        {"paid_on": paid_on, "paid_amount": money(paid_amount)},
        "регистрация оплаты",
        actor,
        paid_on,
    )
    _refs(
        session, company_id, "payment_obligations", new.id, source.id,
        ("paid_on", "paid_amount"),
    )
    session.flush()
    return new


def find_company(session, name: str) -> CompanyRow:
    row = session.scalar(select(CompanyRow).where(CompanyRow.name == name))
    if row is None:
        raise LookupError(f"нет данных: компания {name}")
    return row


def find_contract(session, company_id: UUID, number: str) -> ContractRow:
    row = session.scalar(
        select(ContractRow).where(
            ContractRow.company_id == company_id,
            ContractRow.number == number,
            ContractRow.valid_to.is_(None),
        )
    )
    if row is None:
        raise LookupError(f"нет данных: договор {number}")
    return row


def find_act(session, company_id: UUID, number: str, contract_id=None):
    query = select(AcceptanceActRow).where(
        AcceptanceActRow.company_id == company_id,
        AcceptanceActRow.act_number == number,
        AcceptanceActRow.valid_to.is_(None),
    )
    if contract_id is not None:
        query = query.where(AcceptanceActRow.contract_id == contract_id)
    rows = list(session.scalars(query))
    if not rows:
        raise LookupError(f"нет данных: акт {number}")
    if len(rows) > 1:
        raise LookupError("неоднозначность: уточните договор")
    return rows[0]


def current_obligation(session, company_id: UUID, act_id: UUID):
    return session.scalar(
        select(PaymentObligationRow).where(
            PaymentObligationRow.company_id == company_id,
            PaymentObligationRow.act_id == act_id,
            PaymentObligationRow.valid_to.is_(None),
        )
    )
