from __future__ import annotations

import json
from datetime import date
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import select, text

from .models import (
    AcceptanceActRow,
    CompanyRow,
    ContractRow,
    CostArticleRow,
    CostEntryRow,
    DocumentRow,
    ObjectRow,
    PaymentObligationRow,
    ReferenceRateRow,
    ScenarioParamRow,
    ScenarioRow,
    ScheduleNoteRow,
    ScheduleTaskRow,
    ValueConfirmationRow,
    ValueRefRow,
    ValueSourceRow,
    WorkItemRow,
    WorkCalendarRow,
)


class ImmutableRecordError(RuntimeError):
    """Raised when immutable repository data is mutated in place."""


class DuplicateActiveVersionError(ValueError):
    """Raised when a second active row has the same business key."""


class InvalidBusinessKeyError(ValueError):
    """Raised when a row cannot be identified safely."""


class BaseRepository:
    model: ClassVar[type]
    tenant_scoped: ClassVar[bool] = True
    immutable: ClassVar[bool] = True
    business_key: ClassVar[tuple[str, ...]] = ()

    def __init__(self, session):
        self.session = session

    def _business_values(self, values: dict[str, Any]) -> dict[str, Any]:
        return {field: values.get(field) for field in self.business_key}

    def _validate_business_key(self, values: dict[str, Any]) -> None:
        return None

    def _ensure_unique_active(
        self, company_id: UUID, values: dict[str, Any], exclude_id=None
    ) -> None:
        if not self.business_key:
            return
        self._validate_business_key(values)
        query = select(self.model).where(self.model.valid_to.is_(None))
        if self.tenant_scoped:
            query = query.where(self.model.company_id == company_id)
        key_values = self._business_values(values)
        for field, value in key_values.items():
            column = getattr(self.model, field)
            query = query.where(column.is_(None) if value is None else column == value)
        if exclude_id is not None:
            query = query.where(self.model.id != exclude_id)
        if self.session.scalar(query) is not None:
            raise DuplicateActiveVersionError(
                f"{self.model.__tablename__}: duplicate active version {key_values}"
            )

    def add(self, tenant_id: UUID, **values):
        if self.tenant_scoped:
            supplied = values.pop("company_id", tenant_id)
            if supplied != tenant_id:
                raise PermissionError("company mismatch")
            values["company_id"] = tenant_id
        self._ensure_unique_active(tenant_id, values)
        row = self.model(**values)
        self.session.add(row)
        self.session.flush()
        return row

    def get(self, company_id: UUID, row_id: UUID):
        query = select(self.model).where(self.model.id == row_id)
        if self.tenant_scoped:
            query = query.where(self.model.company_id == company_id)
        return self.session.scalar(query)

    def list_current(self, company_id: UUID, **filters):
        query = select(self.model)
        if self.tenant_scoped:
            query = query.where(self.model.company_id == company_id)
        for field_name, value in filters.items():
            query = query.where(getattr(self.model, field_name) == value)
        if hasattr(self.model, "valid_to"):
            query = query.where(self.model.valid_to.is_(None))
        return list(self.session.scalars(query))

    def get_on_date(self, company_id: UUID, row_id: UUID, on_date: date):
        query = select(self.model).where(
            self.model.id == row_id,
            self.model.valid_from <= on_date,
            (self.model.valid_to.is_(None)) | (self.model.valid_to > on_date),
        )
        if self.tenant_scoped:
            query = query.where(self.model.company_id == company_id)
        return self.session.scalar(query)

    def supersede(
        self,
        company_id: UUID,
        old_id: UUID,
        new_values: dict[str, Any],
        reason: str,
        actor: str,
        effective_on: date,
    ):
        old = self.get(company_id, old_id)
        if old is None:
            raise KeyError(old_id)
        if not hasattr(old, "valid_to"):
            raise ImmutableRecordError(f"{self.model.__tablename__} is not versioned")
        values = {
            column.name: getattr(old, column.name)
            for column in self.model.__table__.columns
            if column.name not in {"id", "valid_to", "superseded_by", "replace_reason"}
        }
        values.update(new_values)
        values["company_id"] = company_id
        values["valid_from"] = effective_on
        self._ensure_unique_active(company_id, values, exclude_id=old.id)
        if self.session.bind.dialect.name == "postgresql":
            self.session.execute(text("SET LOCAL construction_os.allow_supersede='on'"))
        old.valid_to = effective_on
        old.replace_reason = reason
        self.session.flush()
        new = self.model(**values, replace_reason=reason)
        self.session.add(new)
        self.session.flush()
        old.superseded_by = new.id
        changed = {
            field: {"old": str(getattr(old, field)), "new": str(value)}
            for field, value in new_values.items()
            if str(getattr(old, field)) != str(value)
        }
        self.session.add(
            ValueConfirmationRow(
                company_id=company_id,
                entity_name=self.model.__tablename__,
                entity_id=old.id,
                action="replaced",
                old_value=json.dumps({k: v["old"] for k, v in changed.items()}, ensure_ascii=False),
                new_value=json.dumps({k: v["new"] for k, v in changed.items()}, ensure_ascii=False),
                reason=reason,
                actor=actor,
            )
        )
        self.session.flush()
        if self.session.bind.dialect.name == "postgresql":
            self.session.execute(text("SET LOCAL construction_os.allow_supersede='off'"))
        return new

    def update(self, *args, **kwargs):
        raise ImmutableRecordError("immutable record; create or supersede instead")

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError("delete forbidden")


class CompanyRepository(BaseRepository):
    model = CompanyRow
    tenant_scoped = False

    def add(self, company_id: UUID, **values):
        row = CompanyRow(id=company_id, **values)
        self.session.add(row)
        self.session.flush()
        return row

    def get(self, company_id: UUID, row_id: UUID | None = None):
        return self.session.scalar(select(CompanyRow).where(CompanyRow.id == company_id))

    def list_current(self, company_id: UUID, **filters):
        query = select(CompanyRow).where(CompanyRow.id == company_id)
        for field_name, value in filters.items():
            query = query.where(getattr(CompanyRow, field_name) == value)
        return list(self.session.scalars(query))


class DocumentRepository(BaseRepository):
    model = DocumentRow


class ValueSourceRepository(BaseRepository):
    model = ValueSourceRow


class ValueRefRepository(BaseRepository):
    model = ValueRefRow


class ReferenceRateRepository(BaseRepository):
    model = ReferenceRateRow
    tenant_scoped = False


class ContractRepository(BaseRepository):
    model = ContractRow
    business_key = ("number", "signed_on")

    def _business_values(self, values: dict[str, Any]) -> dict[str, Any]:
        return (
            {"number": values.get("number")}
            if values.get("number") is not None
            else {"number": None, "signed_on": values.get("signed_on")}
        )

    def _validate_business_key(self, values: dict[str, Any]) -> None:
        if values.get("number") is None and values.get("signed_on") is None:
            raise InvalidBusinessKeyError(
                "договор без номера и без даты: заполните хотя бы одно поле"
            )


class ObjectRepository(BaseRepository):
    model = ObjectRow
    business_key = ("name",)


class ScheduleTaskRepository(BaseRepository):
    model = ScheduleTaskRow
    business_key = ("object_id", "position_no", "front")


class ScheduleNoteRepository(BaseRepository):
    model = ScheduleNoteRow


class ValueConfirmationRepository(BaseRepository):
    model = ValueConfirmationRow


class WorkItemRepository(BaseRepository):
    model = WorkItemRow
    business_key = ("object_id", "position_no")

    def list_current(self, company_id: UUID, object_id: UUID | None = None, **filters):
        query = select(WorkItemRow).where(
            WorkItemRow.company_id == company_id, WorkItemRow.valid_to.is_(None)
        )
        if object_id is not None:
            query = query.where(WorkItemRow.object_id == object_id)
        for field_name, value in filters.items():
            query = query.where(getattr(WorkItemRow, field_name) == value)
        return list(self.session.scalars(query.order_by(WorkItemRow.position_no)))


class CostArticleRepository(BaseRepository):
    model = CostArticleRow
    tenant_scoped = False


class CostEntryRepository(BaseRepository):
    model = CostEntryRow


class ScenarioRepository(BaseRepository):
    model = ScenarioRow
    business_key = ("object_id", "name")


class ScenarioParamRepository(BaseRepository):
    model = ScenarioParamRow


class WorkCalendarRepository(BaseRepository):
    model = WorkCalendarRow
    tenant_scoped = False

    def get_by_date(self, day: date):
        return self.session.scalar(
            select(WorkCalendarRow).where(WorkCalendarRow.cal_date == day)
        )


EXCLUDED_TABLES = frozenset(
    {"companies", "reference_rates", "cost_articles", "work_calendar"}
)


class AcceptanceActRepository(BaseRepository):
    model = AcceptanceActRow
    business_key = ("contract_id", "act_number")


class PaymentObligationRepository(BaseRepository):
    model = PaymentObligationRow
    business_key = ("act_id",)


TENANT_REPOSITORIES = (
    DocumentRepository,
    ValueSourceRepository,
    ValueRefRepository,
    ContractRepository,
    AcceptanceActRepository,
    PaymentObligationRepository,
    ObjectRepository,
    WorkItemRepository,
    ScheduleTaskRepository,
    ScheduleNoteRepository,
    ValueConfirmationRepository,
    CostEntryRepository,
    ScenarioRepository,
    ScenarioParamRepository,
)
ALL_REPOSITORIES = (
    CompanyRepository,
    ReferenceRateRepository,
    CostArticleRepository,
    WorkCalendarRepository,
    *TENANT_REPOSITORIES,
)
