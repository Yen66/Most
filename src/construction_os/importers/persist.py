from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select

from construction_os.references import ContractType, SourceType
from construction_os.storage.models import (
    CompanyRow,
    ContractRow,
    DocumentRow,
    ObjectRow,
    ScheduleNoteRow,
    ScheduleTaskRow,
    ValueConfirmationRow,
    ValueRefRow,
    ValueSourceRow,
    WorkItemRow,
)

from .schedule import ParsedSchedule
from .vor import ParsedVor


@dataclass(frozen=True, slots=True)
class PersistResult:
    document_id: UUID
    company_id: UUID
    object_id: UUID | None
    created_entities: int
    skipped_duplicate: bool


def _company(session, name: str) -> CompanyRow:
    existing = session.scalar(select(CompanyRow).where(CompanyRow.name == name))
    if existing is not None:
        return existing
    row = CompanyRow(name=name)
    session.add(row)
    session.flush()
    return row


def _existing_document(session, company_id: UUID, digest: str) -> DocumentRow | None:
    return session.scalar(
        select(DocumentRow).where(
            DocumentRow.company_id == company_id,
            DocumentRow.sha256 == digest,
        )
    )


def _create_document(session, company_id: UUID, path: Path, kind: str, digest: str) -> DocumentRow:
    row = DocumentRow(
        company_id=company_id,
        kind=kind,
        original_filename=path.name,
        stored_path=str(path),
        sha256=digest,
    )
    session.add(row)
    session.flush()
    return row


def _create_source(session, company_id: UUID, document_id: UUID, sheet_name: str) -> ValueSourceRow:
    row = ValueSourceRow(
        company_id=company_id,
        source_type=SourceType.DOCUMENT.value,
        document_id=document_id,
        sheet=sheet_name,
        confidence="exact",
    )
    session.add(row)
    session.flush()
    return row


def _new_object_with_contract(
    session,
    company_id: UUID,
    object_name: str,
    price_is_final: bool,
) -> ObjectRow:
    contract = ContractRow(
        company_id=company_id,
        contract_type=ContractType.UNKNOWN.value,
        price_is_final=price_is_final,
    )
    session.add(contract)
    session.flush()
    object_row = ObjectRow(company_id=company_id, contract_id=contract.id, name=object_name)
    session.add(object_row)
    session.flush()
    return object_row


def persist_vor(
    session,
    company_name: str,
    parsed: ParsedVor,
    source_path: str | Path,
    imported_on: date | None = None,
) -> PersistResult:
    path = Path(source_path)
    company = _company(session, company_name)
    existing_document = _existing_document(session, company.id, parsed.sha256)
    if existing_document is not None:
        return PersistResult(existing_document.id, company.id, None, 0, True)
    document = _create_document(session, company.id, path, "vor", parsed.sha256)
    source = _create_source(session, company.id, document.id, parsed.sheet_name)
    object_name = path.stem
    object_row = session.scalar(
        select(ObjectRow).where(ObjectRow.company_id == company.id, ObjectRow.name == object_name)
    )
    if object_row is None:
        object_row = _new_object_with_contract(
            session, company.id, object_name, parsed.price_is_final
        )
    effective_on = imported_on or date.today()
    created = 4
    for item in parsed.items:
        work_item = WorkItemRow(
            company_id=company.id,
            object_id=object_row.id,
            contract_id=object_row.contract_id,
            position_no=item.position_no,
            name=item.name,
            unit=item.unit,
            quantity=item.quantity,
            price_gross=item.price_gross,
            amount_gross=item.amount_gross,
            vat_rate=parsed.vat_rate,
            document_id=document.id,
            source_id=source.id,
            valid_from=effective_on,
        )
        session.add(work_item)
        session.flush()
        for field_name, cell in (
            ("quantity", item.quantity_cell),
            ("price_gross", item.price_cell),
            ("amount_gross", item.amount_cell),
        ):
            cell_source = ValueSourceRow(
                company_id=company.id,
                source_type=SourceType.DOCUMENT.value,
                document_id=document.id,
                sheet=parsed.sheet_name,
                cell_or_range=cell,
                row_no=item.row_no,
                confidence="exact",
            )
            session.add(cell_source)
            session.flush()
            session.add(
                ValueRefRow(
                    company_id=company.id,
                    entity_name="work_items",
                    entity_id=work_item.id,
                    field_name=field_name,
                    source_id=cell_source.id,
                )
            )
            created += 2
        session.add(
            ValueConfirmationRow(
                company_id=company.id,
                entity_name="work_items",
                entity_id=work_item.id,
                action="imported",
                actor="importer",
                new_value=str(item.amount_gross),
            )
        )
        created += 2
    session.flush()
    return PersistResult(document.id, company.id, object_row.id, created, False)


def _object_for_schedule(
    session, company_id: UUID, parsed: ParsedSchedule, path: Path
) -> ObjectRow:
    candidates = list(session.scalars(select(ObjectRow).where(ObjectRow.company_id == company_id)))
    matching: list[ObjectRow] = []
    for candidate in candidates:
        total = session.scalar(
            select(func.coalesce(func.sum(WorkItemRow.amount_gross), 0)).where(
                WorkItemRow.company_id == company_id,
                WorkItemRow.object_id == candidate.id,
                WorkItemRow.valid_to.is_(None),
            )
        )
        if total is not None and parsed.total_amount == total:
            matching.append(candidate)
    if len(matching) == 1:
        return matching[0]
    if parsed.object_name:
        named = session.scalar(
            select(ObjectRow).where(
                ObjectRow.company_id == company_id,
                ObjectRow.name == parsed.object_name,
            )
        )
        if named is not None:
            return named
    return _new_object_with_contract(session, company_id, path.stem, False)


def persist_schedule(
    session,
    company_name: str,
    parsed: ParsedSchedule,
    source_path: str | Path,
) -> PersistResult:
    path = Path(source_path)
    company = _company(session, company_name)
    existing_document = _existing_document(session, company.id, parsed.sha256)
    if existing_document is not None:
        return PersistResult(existing_document.id, company.id, None, 0, True)
    document = _create_document(session, company.id, path, "schedule", parsed.sha256)
    source = _create_source(session, company.id, document.id, parsed.sheet_name)
    object_row = _object_for_schedule(session, company.id, parsed, path)
    created = 2
    for task in parsed.tasks:
        session.add(
            ScheduleTaskRow(
                company_id=company.id,
                object_id=object_row.id,
                position_no=task.position_no,
                name=task.name,
                front=task.front,
                unit=task.unit,
                quantity=task.quantity,
                start_on=task.start_on,
                end_on=task.end_on,
                days=task.days,
                crew_size=task.crew_size,
                amount=task.amount,
                period_volumes=[
                    str(value) if value is not None else None for value in task.period_volumes
                ],
                source_id=source.id,
            )
        )
        created += 1
    for note in parsed.notes:
        note_data = dict(note)
        note_type = str(note_data.pop("type"))
        cell = note_data.pop("cell", None)
        text_value = str(note_data.pop("text", ""))
        session.add(
            ScheduleNoteRow(
                company_id=company.id,
                object_id=object_row.id,
                note_type=note_type,
                text=text_value,
                parsed=note_data,
                cell=cell,
                source_id=source.id,
            )
        )
        created += 1
    session.flush()
    return PersistResult(document.id, company.id, object_row.id, created, False)
