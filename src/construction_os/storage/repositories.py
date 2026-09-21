from __future__ import annotations

from datetime import date
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import select, text

from .models import (
    CompanyRow,
    ContractRow,
    DocumentRow,
    ObjectRow,
    ReferenceRateRow,
    ScheduleNoteRow,
    ScheduleTaskRow,
    ValueConfirmationRow,
    ValueRefRow,
    ValueSourceRow,
    WorkItemRow,
)


class ImmutableRecordError(RuntimeError):
    pass


class BaseRepository:
    model: ClassVar[type]
    tenant_scoped: ClassVar[bool] = True
    immutable: ClassVar[bool] = True

    def __init__(self, session):
        self.session = session

    def add(self, company_id: UUID, **values):
        if self.tenant_scoped:
            supplied = values.pop("company_id", company_id)
            if supplied != company_id:
                raise PermissionError("company mismatch")
            values["company_id"] = company_id
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


class ObjectRepository(BaseRepository):
    model = ObjectRow


class ScheduleTaskRepository(BaseRepository):
    model = ScheduleTaskRow


class ScheduleNoteRepository(BaseRepository):
    model = ScheduleNoteRow


class ValueConfirmationRepository(BaseRepository):
    model = ValueConfirmationRow


class WorkItemRepository(BaseRepository):
    model = WorkItemRow

    def list_current(self, company_id: UUID, **filters):
        query = select(WorkItemRow).where(
            WorkItemRow.company_id == company_id,
            WorkItemRow.valid_to.is_(None),
        )
        for field_name, value in filters.items():
            query = query.where(getattr(WorkItemRow, field_name) == value)
        return list(self.session.scalars(query.order_by(WorkItemRow.position_no)))

    def get_on_date(self, company_id: UUID, row_id: UUID, on_date: date):
        query = select(WorkItemRow).where(
            WorkItemRow.company_id == company_id,
            WorkItemRow.id == row_id,
            WorkItemRow.valid_from <= on_date,
            (WorkItemRow.valid_to.is_(None)) | (WorkItemRow.valid_to > on_date),
        )
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
        if self.session.bind.dialect.name == "postgresql":
            self.session.execute(text("SET LOCAL construction_os.allow_supersede='on'"))
        old.valid_to = effective_on
        old.replace_reason = reason
        self.session.flush()
        excluded = {"id", "valid_to", "superseded_by", "replace_reason"}
        values = {
            column.name: getattr(old, column.name)
            for column in WorkItemRow.__table__.columns
            if column.name not in excluded
        }
        values.update(new_values)
        values["company_id"] = company_id
        values["valid_from"] = effective_on
        new = WorkItemRow(**values, replace_reason=reason)
        self.session.add(new)
        self.session.flush()
        old.superseded_by = new.id
        self.session.add(
            ValueConfirmationRow(
                company_id=company_id,
                entity_name="work_items",
                entity_id=old.id,
                action="replaced",
                old_value=str(old.price_gross),
                new_value=str(new.price_gross),
                reason=reason,
                actor=actor,
            )
        )
        self.session.flush()
        return new


TENANT_REPOSITORIES = (
    DocumentRepository,
    ValueSourceRepository,
    ValueRefRepository,
    ContractRepository,
    ObjectRepository,
    WorkItemRepository,
    ScheduleTaskRepository,
    ScheduleNoteRepository,
    ValueConfirmationRepository,
)
ALL_REPOSITORIES = (CompanyRepository, ReferenceRateRepository, *TENANT_REPOSITORIES)
