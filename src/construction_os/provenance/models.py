from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

class SourceType(StrEnum):
    DOCUMENT="document"; USER_INPUT="user_input"; REFERENCE="reference"; ESTIMATE="estimate"; ASSUMPTION="assumption"; CALCULATED="calculated"
class Confidence(StrEnum):
    EXACT="exact"; CONFIRMED="confirmed"; NEEDS_REVIEW="needs_review"; ASSUMPTION="assumption"

@dataclass(frozen=True, slots=True)
class ValueSource:
    company_id: UUID
    source_type: SourceType
    id: UUID=field(default_factory=uuid4)
    document_id: UUID|None=None
    sheet: str|None=None
    cell_or_range: str|None=None
    row_no: int|None=None
    obtained_at: datetime=field(default_factory=lambda:datetime.now(timezone.utc))
    confidence: Confidence=Confidence.EXACT
    note: str|None=None

@dataclass(frozen=True, slots=True)
class ValueRef:
    company_id: UUID
    entity_name: str
    entity_id: UUID
    field_name: str
    source_id: UUID
    id: UUID=field(default_factory=uuid4)

@dataclass(frozen=True, slots=True)
class ValueConfirmation:
    company_id: UUID
    entity_name: str
    entity_id: UUID
    action: str
    actor: str
    id: UUID=field(default_factory=uuid4)
    field_name: str|None=None
    old_value: str|None=None
    new_value: str|None=None
    reason: str|None=None
    acted_at: datetime=field(default_factory=lambda:datetime.now(timezone.utc))
