from __future__ import annotations
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, Uuid, Boolean, column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JSON_TYPE=JSON().with_variant(JSONB,"postgresql")
def utcnow(): return datetime.now(timezone.utc)
class Base(DeclarativeBase): pass

class CompanyRow(Base):
    __tablename__="companies"
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    name:Mapped[str]=mapped_column(Text,nullable=False)
    inn:Mapped[str|None]=mapped_column(Text)

class DocumentRow(Base):
    __tablename__="documents"
    __table_args__=(UniqueConstraint("company_id","sha256"),)
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    company_id:Mapped[UUID]=mapped_column(Uuid,ForeignKey("companies.id"),nullable=False,index=True)
    kind:Mapped[str]=mapped_column(Text,nullable=False)
    original_filename:Mapped[str]=mapped_column(Text,nullable=False)
    stored_path:Mapped[str]=mapped_column(Text,nullable=False)
    sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    uploaded_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,nullable=False)
    meta:Mapped[dict]=mapped_column(JSON_TYPE,default=dict,nullable=False)

class ValueSourceRow(Base):
    __tablename__="value_sources"
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    company_id:Mapped[UUID]=mapped_column(Uuid,ForeignKey("companies.id"),nullable=False,index=True)
    source_type:Mapped[str]=mapped_column(Text,nullable=False)
    document_id:Mapped[UUID|None]=mapped_column(Uuid,ForeignKey("documents.id"))
    sheet:Mapped[str|None]=mapped_column(Text)
    cell_or_range:Mapped[str|None]=mapped_column(Text)
    row_no:Mapped[int|None]=mapped_column(Integer)
    confidence:Mapped[str]=mapped_column(Text,nullable=False,default="exact")
    note:Mapped[str|None]=mapped_column(Text)

class ValueRefRow(Base):
    __tablename__="value_refs"
    __table_args__=(Index("ix_value_refs_entity","entity_name","entity_id","field_name"),)
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    company_id:Mapped[UUID]=mapped_column(Uuid,ForeignKey("companies.id"),nullable=False,index=True)
    entity_name:Mapped[str]=mapped_column(Text,nullable=False)
    entity_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    field_name:Mapped[str]=mapped_column(Text,nullable=False)
    source_id:Mapped[UUID]=mapped_column(Uuid,ForeignKey("value_sources.id"),nullable=False)

class ReferenceRateRow(Base):
    __tablename__="reference_rates"
    __table_args__=(UniqueConstraint("rate_type","valid_from"),)
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    rate_type:Mapped[str]=mapped_column(Text,nullable=False)
    value:Mapped[Decimal]=mapped_column(Numeric(12,6),nullable=False)
    valid_from:Mapped[date]=mapped_column(Date,nullable=False)
    valid_to:Mapped[date|None]=mapped_column(Date)
    document_number:Mapped[str|None]=mapped_column(Text)
    document_date:Mapped[date|None]=mapped_column(Date)

class ContractRow(Base):
    __tablename__="contracts"
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    company_id:Mapped[UUID]=mapped_column(Uuid,ForeignKey("companies.id"),nullable=False,index=True)
    contract_type:Mapped[str]=mapped_column(Text,nullable=False)
    number:Mapped[str|None]=mapped_column(Text)
    price_is_final:Mapped[bool]=mapped_column(Boolean,default=False,nullable=False)
    advance_pct:Mapped[Decimal|None]=mapped_column(Numeric(9,4))
    payment_delay_days:Mapped[int|None]=mapped_column(Integer)
    security_amount:Mapped[Decimal|None]=mapped_column(Numeric(18,2))
    warranty_retention_pct:Mapped[Decimal|None]=mapped_column(Numeric(9,4))
    treasury_account:Mapped[bool|None]=mapped_column(Boolean)
    currency:Mapped[str]=mapped_column(String(3),default="RUB",nullable=False)
    vat_rate_id:Mapped[UUID|None]=mapped_column(Uuid,ForeignKey("reference_rates.id"))

class ObjectRow(Base):
    __tablename__="objects"
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    company_id:Mapped[UUID]=mapped_column(Uuid,ForeignKey("companies.id"),nullable=False,index=True)
    contract_id:Mapped[UUID|None]=mapped_column(Uuid,ForeignKey("contracts.id"))
    name:Mapped[str]=mapped_column(Text,nullable=False)
    object_type:Mapped[str|None]=mapped_column(Text)
    location_text:Mapped[str|None]=mapped_column(Text)

class WorkItemRow(Base):
    __tablename__="work_items"
    __table_args__=(Index("uq_work_item_current","company_id","object_id","position_no",unique=True,postgresql_where=column("valid_to").is_(None),sqlite_where=column("valid_to").is_(None)),)
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    company_id:Mapped[UUID]=mapped_column(Uuid,ForeignKey("companies.id"),nullable=False,index=True)
    object_id:Mapped[UUID]=mapped_column(Uuid,ForeignKey("objects.id"),nullable=False)
    contract_id:Mapped[UUID|None]=mapped_column(Uuid,ForeignKey("contracts.id"))
    position_no:Mapped[int]=mapped_column(Integer,nullable=False)
    name:Mapped[str]=mapped_column(Text,nullable=False)
    unit:Mapped[str]=mapped_column(Text,nullable=False)
    quantity:Mapped[Decimal]=mapped_column(Numeric(18,4),nullable=False)
    price_gross:Mapped[Decimal]=mapped_column(Numeric(18,4),nullable=False)
    amount_gross:Mapped[Decimal]=mapped_column(Numeric(18,2),nullable=False)
    vat_rate:Mapped[Decimal]=mapped_column(Numeric(9,6),nullable=False)
    document_id:Mapped[UUID|None]=mapped_column(Uuid,ForeignKey("documents.id"))
    source_id:Mapped[UUID]=mapped_column(Uuid,ForeignKey("value_sources.id"),nullable=False)
    valid_from:Mapped[date]=mapped_column(Date,nullable=False)
    valid_to:Mapped[date|None]=mapped_column(Date)
    superseded_by:Mapped[UUID|None]=mapped_column(Uuid,ForeignKey("work_items.id"))
    replace_reason:Mapped[str|None]=mapped_column(Text)

class ScheduleTaskRow(Base):
    __tablename__="schedule_tasks"
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    company_id:Mapped[UUID]=mapped_column(Uuid,ForeignKey("companies.id"),nullable=False,index=True)
    object_id:Mapped[UUID]=mapped_column(Uuid,ForeignKey("objects.id"),nullable=False)
    position_no:Mapped[int|None]=mapped_column(Integer)
    front:Mapped[str|None]=mapped_column(Text)
    unit:Mapped[str|None]=mapped_column(Text)
    quantity:Mapped[Decimal|None]=mapped_column(Numeric(18,4))
    start_on:Mapped[date|None]=mapped_column(Date)
    end_on:Mapped[date|None]=mapped_column(Date)
    days:Mapped[int|None]=mapped_column(Integer)
    crew_size:Mapped[Decimal|None]=mapped_column(Numeric(9,2))
    amount:Mapped[Decimal|None]=mapped_column(Numeric(18,2))
    period_volumes:Mapped[list]=mapped_column(JSON_TYPE,default=list,nullable=False)
    source_id:Mapped[UUID]=mapped_column(Uuid,ForeignKey("value_sources.id"),nullable=False)

class ScheduleNoteRow(Base):
    __tablename__="schedule_notes"
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    company_id:Mapped[UUID]=mapped_column(Uuid,ForeignKey("companies.id"),nullable=False,index=True)
    object_id:Mapped[UUID]=mapped_column(Uuid,ForeignKey("objects.id"),nullable=False)
    note_type:Mapped[str]=mapped_column(Text,nullable=False)
    text:Mapped[str]=mapped_column(Text,nullable=False)
    parsed:Mapped[dict]=mapped_column(JSON_TYPE,default=dict,nullable=False)
    cell:Mapped[str|None]=mapped_column(Text)
    source_id:Mapped[UUID]=mapped_column(Uuid,ForeignKey("value_sources.id"),nullable=False)

class ValueConfirmationRow(Base):
    __tablename__="value_confirmations"
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    company_id:Mapped[UUID]=mapped_column(Uuid,ForeignKey("companies.id"),nullable=False,index=True)
    entity_name:Mapped[str]=mapped_column(Text,nullable=False)
    entity_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    field_name:Mapped[str|None]=mapped_column(Text)
    action:Mapped[str]=mapped_column(Text,nullable=False)
    old_value:Mapped[str|None]=mapped_column(Text)
    new_value:Mapped[str|None]=mapped_column(Text)
    reason:Mapped[str|None]=mapped_column(Text)
    actor:Mapped[str]=mapped_column(Text,nullable=False)
    acted_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,nullable=False)
