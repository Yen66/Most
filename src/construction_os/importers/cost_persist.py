from __future__ import annotations
from datetime import date
from pathlib import Path
from sqlalchemy import select
from construction_os.references import SourceType
from construction_os.storage.models import CompanyRow,CostArticleRow,CostEntryRow,ObjectRow,ValueRefRow,ValueSourceRow,WorkItemRow
from .costs import CostImportError,ParsedCosts
from .persist import PersistResult,_create_document,_existing_document

def persist_costs(session,company_name:str,parsed:ParsedCosts,source_path:str|Path,imported_on:date|None=None,actor:str="cost-importer")->PersistResult:
    company=session.scalar(select(CompanyRow).where(CompanyRow.name==company_name))
    if company is None: raise CostImportError(f"компания не найдена: {company_name}")
    existing=_existing_document(session,company.id,parsed.sha256)
    if existing is not None: return PersistResult(existing.id,company.id,None,0,True)
    objects={r.name:r for r in session.scalars(select(ObjectRow).where(ObjectRow.company_id==company.id,ObjectRow.valid_to.is_(None)))}
    for row in parsed.rows:
        if row.object_name not in objects: raise CostImportError(f"строка {row.row_no}: объект не найден: {row.object_name}")
    path=Path(source_path); document=_create_document(session,company.id,path,"costs",parsed.sha256); created=1; first=None; effective=imported_on or date.today()
    for row in parsed.rows:
        obj=objects[row.object_name]; first=first or obj.id; work_id=None
        if row.work_position_no is not None:
            work=session.scalar(select(WorkItemRow).where(WorkItemRow.company_id==company.id,WorkItemRow.object_id==obj.id,WorkItemRow.position_no==row.work_position_no,WorkItemRow.valid_to.is_(None)))
            if work is None: raise CostImportError(f"строка {row.row_no}: позиция работ не найдена: {row.work_position_no}")
            work_id=work.id
        source=ValueSourceRow(company_id=company.id,source_type=SourceType.DOCUMENT.value,document_id=document.id,sheet=parsed.sheet_name,row_no=row.row_no,confidence="exact",note=row.note)
        session.add(source); session.flush()
        entry=CostEntryRow(company_id=company.id,object_id=obj.id,contract_id=obj.contract_id,work_item_id=work_id,article_code=row.article_code,quantity=row.quantity,unit=row.unit,price=row.price,amount=row.amount,amount_type=row.amount_type,rate_value=row.rate_value,vat_mode=row.vat_mode,vat_rate=None,source_id=source.id,valid_from=effective,created_by=actor)
        session.add(entry); session.flush()
        field="rate_value" if row.amount_type=="share_of_revenue" else "amount"; column="I" if field=="rate_value" else "G"
        cell_source=ValueSourceRow(company_id=company.id,source_type=SourceType.DOCUMENT.value,document_id=document.id,sheet=parsed.sheet_name,cell_or_range=f"{column}{row.row_no}",row_no=row.row_no,confidence="exact")
        session.add(cell_source); session.flush(); session.add(ValueRefRow(company_id=company.id,entity_name="cost_entries",entity_id=entry.id,field_name=field,source_id=cell_source.id)); created+=4
    session.flush(); return PersistResult(document.id,company.id,first,created,False)

def article_codes(session)->set[str]:
    return set(session.scalars(select(CostArticleRow.code)))
