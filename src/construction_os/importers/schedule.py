from __future__ import annotations
from dataclasses import dataclass
from datetime import date,datetime,timedelta
from decimal import Decimal
from pathlib import Path
import re
from openpyxl import load_workbook
from construction_os.money.core import as_decimal,money,sum_positions
from .vor import ParsedVor

@dataclass(frozen=True,slots=True)
class Task:
    position_no:int|None; name:str; front:str|None; unit:str|None; quantity:Decimal|None
    start_on:date|None; end_on:date|None; days:int|None; crew_size:Decimal|None; amount:Decimal|None
    period_volumes:tuple[Decimal|None,...]; row_no:int

@dataclass(frozen=True,slots=True)
class ParsedSchedule:
    tasks:tuple[Task,...]; notes:tuple[dict,...]; total_amount:Decimal; period_mismatches:tuple[str,...]

def d(v):
    if v is None:return None
    if isinstance(v,datetime):return v.date()
    if isinstance(v,date):return v
    return datetime.strptime(str(v),"%d.%m.%Y").date()
def dec(v): return None if v is None else as_decimal(v)

def parse_schedule(path:str|Path)->ParsedSchedule:
    wb=load_workbook(path,data_only=True);ws=wb[wb.sheetnames[0]];header=None
    for r in range(1,ws.max_row+1):
        s=" | ".join(str(ws.cell(r,c).value or "").lower() for c in range(1,min(ws.max_column,12)+1))
        if "наименование работ" in s and "начало" in s and "окончание" in s and "звено" in s:header=r;break
    if header is None:raise ValueError("schedule header not found")
    notes=[];year=None
    for r in range(1,ws.max_row+1):
        t=ws.cell(r,1).value
        if not isinstance(t,str):continue
        low=t.lower()
        if "период работ:" in low:
            m=re.search(r"(\d{2}\.\d{2}\.\d{4})[–-](\d{2}\.\d{2}\.\d{4})",t)
            if m:year=int(m.group(2)[-4:]);notes.append({"type":"period","cell":f"A{r}","start":m.group(1),"end":m.group(2)})
        elif low.startswith("ресурсный план:"):
            n={"type":"resource_plan","cell":f"A{r}","text":t}
            m=re.search(r"\d{2}[–-](\d{2}\.\d{2}).*?далее\s+(.+?)\s+и\s+(.+?)\s+делят\s+мобильную\s+бригаду\s+(\d+)\s+чел",low)
            if m and year:
                day,month=map(int,m.group(1).split("."));n["shared_resource"]={"resource":"мобильная бригада","objects":[m.group(2).title(),m.group(3).title()],"from":(date(year,month,day)+timedelta(days=1)).isoformat(),"crew":m.group(4)}
            notes.append(n)
        elif low.startswith("реверс:"):notes.append({"type":"reverse_scheme","cell":f"A{r}","text":t})
        elif low.startswith("примечание:") and "режим:" in low:notes.append({"type":"work_regime","cell":f"A{r}","text":t})
    tasks=[];bad=[]
    for r in range(header+1,ws.max_row+1):
        name=ws.cell(r,2).value
        if not isinstance(name,str) or not name.strip():continue
        p=ws.cell(r,1).value;pos=int(p) if isinstance(p,(int,float)) else None;q=dec(ws.cell(r,5).value)
        periods=tuple(dec(ws.cell(r,c).value) for c in range(12,24))
        if q is not None and sum((x for x in periods if x is not None),Decimal("0"))!=q:bad.append(f"row {r}")
        tasks.append(Task(pos,name.strip(),ws.cell(r,3).value,ws.cell(r,4).value,q,d(ws.cell(r,6).value),d(ws.cell(r,7).value),ws.cell(r,8).value,dec(ws.cell(r,9).value),money(ws.cell(r,10).value) if ws.cell(r,10).value is not None else None,periods,r))
    return ParsedSchedule(tuple(tasks),tuple(notes),sum_positions(t.amount for t in tasks if t.amount is not None),tuple(bad))

def reconcile(vor:ParsedVor,schedule:ParsedSchedule):
    q={};a={}
    for t in schedule.tasks:
        if t.position_no is None:continue
        q[t.position_no]=q.get(t.position_no,Decimal("0"))+(t.quantity or Decimal("0"))
        a[t.position_no]=a.get(t.position_no,Decimal("0"))+(t.amount or Decimal("0"))
    out=[]
    for i in vor.items:
        if q.get(i.position_no,Decimal("0"))!=i.quantity:out.append((i.position_no,"quantity"))
        if money(a.get(i.position_no,Decimal("0")))!=i.amount_gross:out.append((i.position_no,"amount"))
    return out
