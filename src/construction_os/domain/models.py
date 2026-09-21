from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class Company:
    name: str
    id: UUID = field(default_factory=uuid4)
    inn: str | None = None


@dataclass(frozen=True, slots=True)
class Document:
    company_id: UUID
    kind: str
    original_filename: str
    stored_path: str
    sha256: str
    id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True, slots=True)
class Contract:
    company_id: UUID
    contract_type: str
    id: UUID = field(default_factory=uuid4)
    number: str | None = None
    price_is_final: bool = False


@dataclass(frozen=True, slots=True)
class ConstructionObject:
    company_id: UUID
    name: str
    id: UUID = field(default_factory=uuid4)
    contract_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class WorkItem:
    company_id: UUID
    object_id: UUID
    position_no: int
    name: str
    unit: str
    quantity: Decimal
    price_gross: Decimal
    amount_gross: Decimal
    vat_rate: Decimal
    source_id: UUID
    valid_from: date
    id: UUID = field(default_factory=uuid4)
    valid_to: date | None = None


@dataclass(frozen=True, slots=True)
class ScheduleTask:
    company_id: UUID
    object_id: UUID
    source_id: UUID
    id: UUID = field(default_factory=uuid4)
    position_no: int | None = None
    quantity: Decimal | None = None
    amount: Decimal | None = None
