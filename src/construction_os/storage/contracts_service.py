from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from construction_os.calc.acts import LONG_CONTRACT_WARNING
from construction_os.references import Confidence, SourceType

from .models import CompanyRow, ContractRow, ObjectRow, ValueRefRow, ValueSourceRow
from .repositories import ContractRepository, ObjectRepository

TERM_FIELDS = (
    "contract_type",
    "signed_on",
    "advance_pct",
    "payment_delay_days",
    "security_amount",
    "warranty_retention_pct",
    "treasury_account",
    "award_reduction_factor",
    "price_is_final",
    "penalty_cap_pct",
)


def validate_contract(number: str | None, **terms) -> None:
    if not number or not number.strip():
        raise ValueError("contract number is required")
    ranges = (
        ("advance_pct", Decimal("0"), Decimal("100"), "advance_pct must be within 0..100"),
        (
            "warranty_retention_pct",
            Decimal("0"),
            Decimal("20"),
            "warranty_retention_pct must be within 0..20",
        ),
        ("penalty_cap_pct", Decimal("0"), Decimal("50"), "penalty_cap_pct must be within 0..50"),
    )
    for field, lower, upper, message in ranges:
        value = terms.get(field)
        if value is not None and (not value.is_finite() or not lower <= value <= upper):
            raise ValueError(message)
    delay = terms.get("payment_delay_days")
    if delay is not None and not 1 <= delay <= 30:
        raise ValueError("payment_delay_days must be within 1..30")
    factor = terms.get("award_reduction_factor")
    if factor is not None and (not factor.is_finite() or not Decimal("0") < factor <= Decimal("1")):
        raise ValueError("award_reduction_factor must be within (0, 1]")
    security = terms.get("security_amount")
    if security is not None and (not security.is_finite() or security < 0):
        raise ValueError("security_amount must be non-negative")


def get_contract(session, company_name: str, number: str):
    company = session.scalar(select(CompanyRow).where(CompanyRow.name == company_name))
    if company is None:
        raise LookupError(f"нет данных: компания {company_name}")
    row = session.scalar(
        select(ContractRow).where(
            ContractRow.company_id == company.id,
            ContractRow.number == number,
            ContractRow.valid_to.is_(None),
        )
    )
    if row is None:
        raise LookupError(f"нет данных: договор {number}")
    count = session.scalar(
        select(func.count())
        .select_from(ContractRow)
        .where(
            ContractRow.company_id == company.id,
            ContractRow.number == number,
        )
    )
    return company, row, count


def set_contract(
    session,
    company_name: str,
    number: str,
    *,
    signed_on: date | None = None,
    contract_type: str | None = None,
    advance_pct: Decimal | None = None,
    payment_delay_days: int | None = None,
    security_amount: Decimal | None = None,
    warranty_retention_pct: Decimal | None = None,
    treasury_account: bool | None = None,
    award_reduction_factor: Decimal | None = None,
    price_is_final: bool | None = None,
    penalty_cap_pct: Decimal | None = None,
    actor: str = "cli",
    reason: str | None = None,
    effective_on: date | None = None,
):
    terms = {
        "signed_on": signed_on,
        "contract_type": contract_type,
        "advance_pct": advance_pct,
        "payment_delay_days": payment_delay_days,
        "security_amount": security_amount,
        "warranty_retention_pct": warranty_retention_pct,
        "treasury_account": treasury_account,
        "award_reduction_factor": award_reduction_factor,
        "price_is_final": price_is_final,
        "penalty_cap_pct": penalty_cap_pct,
    }
    validate_contract(number, **terms)
    company = session.scalar(select(CompanyRow).where(CompanyRow.name == company_name))
    if company is None:
        raise LookupError(f"нет данных: компания {company_name}")
    effective_on = effective_on or date.today()
    changes = {field: value for field, value in terms.items() if value is not None}
    current = session.scalar(
        select(ContractRow).where(
            ContractRow.company_id == company.id,
            ContractRow.number == number,
            ContractRow.valid_to.is_(None),
        )
    )
    repo = ContractRepository(session)
    replacement_reason = reason or "уточнение условий владельцем"
    if current is None:
        values = {
            "number": number,
            "contract_type": "unknown",
            "price_is_final": False,
            "valid_from": effective_on,
        }
        values.update(changes)
        contract = repo.add(company.id, **values)
    else:
        contract = repo.supersede(
            company.id, current.id, changes, replacement_reason, actor, effective_on
        )
    source = ValueSourceRow(
        company_id=company.id,
        source_type=SourceType.USER_INPUT.value,
        confidence=Confidence.EXACT.value,
        note=f"actor={actor}; reason={replacement_reason}",
    )
    session.add(source)
    session.flush()
    fields = ("number", *changes) if current is None else tuple(changes)
    for field in fields:
        session.add(
            ValueRefRow(
                company_id=company.id,
                entity_name="contracts",
                entity_id=contract.id,
                field_name=field,
                source_id=source.id,
            )
        )
    objects = list(
        session.scalars(
            select(ObjectRow).where(
                ObjectRow.company_id == company.id, ObjectRow.valid_to.is_(None)
            )
        )
    )
    linked = [obj for obj in objects if current is not None and obj.contract_id == current.id]
    if not linked and len(objects) == 1:
        # With one object, the contract association is unambiguous.
        linked = objects
    for obj in linked:
        if obj.contract_id != contract.id:
            ObjectRepository(session).supersede(
                company.id,
                obj.id,
                {"contract_id": contract.id},
                "привязка актуальной версии договора",
                actor,
                effective_on,
            )
    session.flush()
    warnings = []
    if contract.payment_delay_days is not None and contract.payment_delay_days > 10:
        warnings.append(LONG_CONTRACT_WARNING)
    return contract, warnings
