from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    column,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base for persistence models."""


class CompanyRow(Base):
    __tablename__ = "companies"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    inn: Mapped[str | None] = mapped_column(Text)


class DocumentRow(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("company_id", "sha256"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    meta: Mapped[dict] = mapped_column(JSON_TYPE, default=dict, nullable=False)


class ValueSourceRow(Base):
    __tablename__ = "value_sources"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    document_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("documents.id"))
    sheet: Mapped[str | None] = mapped_column(Text)
    cell_or_range: Mapped[str | None] = mapped_column(Text)
    row_no: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[str] = mapped_column(Text, nullable=False, default="exact")
    note: Mapped[str | None] = mapped_column(Text)


class ValueRefRow(Base):
    __tablename__ = "value_refs"
    __table_args__ = (Index("ix_value_refs_entity", "entity_name", "entity_id", "field_name"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id"), nullable=False, index=True
    )
    entity_name: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    field_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("value_sources.id"), nullable=False)


class ReferenceRateRow(Base):
    __tablename__ = "reference_rates"
    __table_args__ = (UniqueConstraint("rate_type", "valid_from"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    rate_type: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    document_number: Mapped[str | None] = mapped_column(Text)
    document_date: Mapped[date | None] = mapped_column(Date)


class ContractRow(Base):
    __tablename__ = "contracts"
    __table_args__ = (
        Index("uq_contract_current", "company_id", "number", unique=True,
              postgresql_where=column("valid_to").is_(None), sqlite_where=column("valid_to").is_(None)),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    contract_type: Mapped[str] = mapped_column(Text, nullable=False)
    number: Mapped[str | None] = mapped_column(Text)
    signed_on: Mapped[date | None] = mapped_column(Date)
    award_reduction_factor: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    price_is_final: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    advance_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    payment_delay_days: Mapped[int | None] = mapped_column(Integer)
    security_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    warranty_retention_pct: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    treasury_account: Mapped[bool | None] = mapped_column(Boolean)
    currency: Mapped[str] = mapped_column(String(3), default="RUB", nullable=False)
    vat_rate_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("reference_rates.id"))
    valid_from: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    valid_to: Mapped[date | None] = mapped_column(Date)
    superseded_by: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("contracts.id"))
    replace_reason: Mapped[str | None] = mapped_column(Text)


class ObjectRow(Base):
    __tablename__ = "objects"
    __table_args__ = (
        Index("uq_object_current", "company_id", "name", unique=True,
              postgresql_where=column("valid_to").is_(None), sqlite_where=column("valid_to").is_(None)),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    contract_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("contracts.id"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    object_type: Mapped[str | None] = mapped_column(Text)
    location_text: Mapped[str | None] = mapped_column(Text)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    valid_to: Mapped[date | None] = mapped_column(Date)
    superseded_by: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("objects.id"))
    replace_reason: Mapped[str | None] = mapped_column(Text)


class WorkItemRow(Base):
    __tablename__ = "work_items"
    __table_args__ = (
        Index(
            "uq_work_item_current",
            "company_id",
            "object_id",
            "position_no",
            unique=True,
            postgresql_where=column("valid_to").is_(None),
            sqlite_where=column("valid_to").is_(None),
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id"), nullable=False, index=True
    )
    object_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("objects.id"), nullable=False)
    contract_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("contracts.id"))
    position_no: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    price_gross: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    amount_gross: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    document_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("documents.id"))
    source_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("value_sources.id"), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    superseded_by: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("work_items.id"))
    replace_reason: Mapped[str | None] = mapped_column(Text)


class ScheduleTaskRow(Base):
    __tablename__ = "schedule_tasks"
    __table_args__ = (
        Index("uq_schedule_task_current", "company_id", "object_id", "position_no", "front", unique=True,
              postgresql_where=column("valid_to").is_(None), sqlite_where=column("valid_to").is_(None)),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    object_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("objects.id"), nullable=False)
    position_no: Mapped[int | None] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    front: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    start_on: Mapped[date | None] = mapped_column(Date)
    end_on: Mapped[date | None] = mapped_column(Date)
    days: Mapped[int | None] = mapped_column(Integer)
    crew_size: Mapped[Decimal | None] = mapped_column(Numeric(9, 2))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    period_volumes: Mapped[list] = mapped_column(JSON_TYPE, default=list, nullable=False)
    source_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("value_sources.id"), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    valid_to: Mapped[date | None] = mapped_column(Date)
    superseded_by: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("schedule_tasks.id"))
    replace_reason: Mapped[str | None] = mapped_column(Text)


class ScheduleNoteRow(Base):
    __tablename__ = "schedule_notes"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id"), nullable=False, index=True
    )
    object_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("objects.id"), nullable=False)
    note_type: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed: Mapped[dict] = mapped_column(JSON_TYPE, default=dict, nullable=False)
    cell: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("value_sources.id"), nullable=False)


class ValueConfirmationRow(Base):
    __tablename__ = "value_confirmations"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("companies.id"), nullable=False, index=True
    )
    entity_name: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    field_name: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    acted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class CostArticleRow(Base):
    __tablename__ = "cost_articles"
    __table_args__ = (CheckConstraint("category IN ('direct','indirect','financial','other')", name="ck_cost_article_category"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int | None] = mapped_column(Integer)


class CostEntryRow(Base):
    __tablename__ = "cost_entries"
    __table_args__ = (
        CheckConstraint("amount_type IN ('fixed','share_of_revenue')", name="ck_cost_entry_amount_type"),
        CheckConstraint("vat_mode IN ('gross','net','unknown')", name="ck_cost_entry_vat_mode"),
        CheckConstraint("(amount_type = 'fixed' AND amount IS NOT NULL AND rate_value IS NULL) OR (amount_type = 'share_of_revenue' AND amount IS NULL AND rate_value IS NOT NULL)", name="ck_cost_entry_amount_shape"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    object_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("objects.id"), nullable=False)
    contract_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("contracts.id"))
    work_item_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("work_items.id"))
    article_code: Mapped[str] = mapped_column(Text, ForeignKey("cost_articles.code"), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    unit: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    amount_type: Mapped[str] = mapped_column(Text, nullable=False, default="fixed")
    rate_value: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    vat_mode: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    vat_rate: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    source_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("value_sources.id"), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    valid_to: Mapped[date | None] = mapped_column(Date)
    superseded_by: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("cost_entries.id"))
    replace_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)


class ScenarioRow(Base):
    __tablename__ = "scenarios"
    __table_args__ = (
        Index("uq_scenario_current", "company_id", "object_id", "name", unique=True,
              postgresql_where=column("valid_to").is_(None), sqlite_where=column("valid_to").is_(None)),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    object_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("objects.id"))
    contract_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("contracts.id"))
    base_date: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("value_sources.id"), nullable=False)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    valid_to: Mapped[date | None] = mapped_column(Date)
    superseded_by: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("scenarios.id"))
    replace_reason: Mapped[str | None] = mapped_column(Text)


class ScenarioParamRow(Base):
    __tablename__ = "scenario_params"
    __table_args__ = (
        CheckConstraint("param_type IN ('cost_multiplier','price_reduction','schedule_shift_days','winter_surcharge_pct','financial_share_override')", name="ck_scenario_param_type"),
        CheckConstraint("scope IN ('all','category','cost_item')", name="ck_scenario_param_scope"),
        CheckConstraint("scope <> 'all' OR scope_value IS NULL", name="ck_scenario_scope_all"),
        CheckConstraint("scope = 'all' OR scope_value IS NOT NULL", name="ck_scenario_scope_specific"),
        CheckConstraint("param_value > 0", name="ck_scenario_param_positive"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("companies.id"), nullable=False, index=True)
    scenario_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("scenarios.id"), nullable=False)
    param_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False, default="all")
    scope_value: Mapped[str | None] = mapped_column(Text)
    param_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
