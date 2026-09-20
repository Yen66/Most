from __future__ import annotations
from datetime import date
from uuid import UUID
from sqlalchemy import select, text
from .models import ValueConfirmationRow, WorkItemRow

class ImmutableRecordError(RuntimeError): pass

class WorkItemRepository:
    def __init__(self,session): self.session=session
    def add(self,company_id:UUID,**values):
        if values["company_id"]!=company_id: raise PermissionError("company mismatch")
        row=WorkItemRow(**values); self.session.add(row); self.session.flush(); return row
    def list_current(self,company_id:UUID,object_id:UUID):
        q=select(WorkItemRow).where(WorkItemRow.company_id==company_id,WorkItemRow.object_id==object_id,WorkItemRow.valid_to.is_(None)).order_by(WorkItemRow.position_no)
        return list(self.session.scalars(q))
    def update(self,*a,**k): raise ImmutableRecordError("supersede instead")
    def delete(self,*a,**k): raise ImmutableRecordError("delete forbidden")
    def supersede(self,company_id:UUID,old_id:UUID,new_values:dict,reason:str,actor:str,effective_on:date):
        old=self.session.get(WorkItemRow,old_id)
        if old is None or old.company_id!=company_id: raise KeyError(old_id)
        if self.session.bind.dialect.name=="postgresql":
            self.session.execute(text("SET LOCAL construction_os.allow_supersede='on'"))
        old.valid_to=effective_on; old.replace_reason=reason; self.session.flush()
        data={c.name:getattr(old,c.name) for c in WorkItemRow.__table__.columns if c.name not in {"id","valid_to","superseded_by","replace_reason"}}
        data.update(new_values); data["valid_from"]=effective_on; data["company_id"]=company_id
        new=WorkItemRow(**data,replace_reason=reason); self.session.add(new); self.session.flush()
        old.superseded_by=new.id
        self.session.add(ValueConfirmationRow(company_id=company_id,entity_name="work_items",entity_id=old.id,action="replaced",old_value=str(old.price_gross),new_value=str(new.price_gross),reason=reason,actor=actor))
        self.session.flush(); return new
