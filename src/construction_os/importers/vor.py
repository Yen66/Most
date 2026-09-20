from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import re
from openpyxl import load_workbook
from construction_os.money.core import as_decimal, money, round_position, sum_positions

class VorImportError(ValueError): pass

@dataclass(frozen=True,slots=True)
class Item:
    position_no:int; name:str; unit:str; quantity:Decimal; price_gross:Decimal; amount_gross:Decimal
    row_no:int; quantity_cell:str; price_cell:str; amount_cell:str; raw_price:str; amount_formula:str|None

@dataclass(frozen=True,slots=True)
class ParsedVor:
    items:tuple[Item,...]; total_gross:Decimal; vat_rate:Decimal; price_is_final:bool
    discrepancies:tuple[str,...]; sha256:str; header_row:int

def _header(ws):
    for r in range(1,ws.max_row+1):
        s=" | ".join(str(ws.cell(r,c).value or "").lower() for c in range(1,min(ws.max_column,8)+1))
        if "наименование" in s and "количество" in s and "расцен" in s and "ндс" in s: return r
    raise VorImportError("header not found")

def _vat_and_total_row(ws):
    rx=re.compile(r"ндс\s*(\d+(?:[.,]\d+)?)\s*%",re.I)
    for r in range(1,ws.max_row+1):
        for c in range(1,min(ws.max_column,8)+1):
            v=ws.cell(r,c).value
            if isinstance(v,str) and (m:=rx.search(v)): return Decimal(m.group(1).replace(",","."))/Decimal("100"),r
    raise VorImportError("VAT not stated")

def parse_vor(path:str|Path)->ParsedVor:
    p=Path(path); wf=load_workbook(p,data_only=False); wv=load_workbook(p,data_only=True)
    sf=wf[wf.sheetnames[0]]; sv=wv[sf.title]; h=_header(sf); rate,total_row=_vat_and_total_row(sf)
    items=[]; errors=[]; prev=None
    for r in range(h+1,total_row):
        a=sv.cell(r,1).value; af=sf.cell(r,1).value
        pos=int(a) if isinstance(a,(int,float)) else None
        if pos is None and isinstance(af,str) and af.startswith("=") and prev is not None: pos=prev+1
        name=sv.cell(r,2).value
        if pos is None or not isinstance(name,str) or not name.strip(): continue
        q=as_decimal(sv.cell(r,4).value); raw=sv.cell(r,5).value; price=money(raw)
        expected=round_position(q,price); observed=money(sv.cell(r,6).value) if sv.cell(r,6).value is not None else expected
        if observed!=expected: errors.append(f"row {r}: {observed} != {expected}")
        items.append(Item(pos,name.strip(),str(sv.cell(r,3).value or "").strip(),q,price,observed,r,f"D{r}",f"E{r}",f"F{r}",str(raw),sf.cell(r,6).value))
        prev=pos
    total=sum_positions(i.amount_gross for i in items)
    cached=sv.cell(total_row,6).value
    if cached is not None and money(cached)!=total: raise VorImportError(f"total {cached} != {total}")
    note=" ".join(str(sf.cell(r,c).value or "") for r in range(1,sf.max_row+1) for c in range(1,min(sf.max_column,7)+1)).lower()
    digest=sha256(p.read_bytes()).hexdigest()
    return ParsedVor(tuple(items),total,rate,"скоррект" not in note,tuple(errors),digest,h)
