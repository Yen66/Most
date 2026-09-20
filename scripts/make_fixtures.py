from decimal import Decimal,ROUND_HALF_UP
from pathlib import Path
from openpyxl import Workbook
CENT=Decimal("0.01")
def m(x): return x.quantize(CENT,rounding=ROUND_HALF_UP)
def make(path,name,count,target):
    rows=[]; subtotal=Decimal("0")
    for i in range(1,count):
        q=Decimal((i%7)+1); p=m(Decimal(10000+i*137)); rows.append((f"Синтетическая работа {i}","ед.",q,p)); subtotal+=m(q*p)
    rows.append((f"Синтетическая работа {count}","ед.",Decimal("1"),m(target-subtotal)))
    assert sum((m(q*p) for _,_,q,p in rows),Decimal("0"))==target
    wb=Workbook();ws=wb.active;ws.title="Лист1";ws["A4"]="Ведомость объемов и стоимости работ (смета)"
    for c,v in enumerate(["№ п/п","Наименование","Ед. изм","Кол-во","Расценка","Стоимость"],1):ws.cell(6,c,v)
    for c,v in enumerate(["№ п/п","Наименование работ","Ед.","Количество","Единичная расценка с НДС","Всего с НДС"],1):ws.cell(9,c,v)
    for j,(n,u,q,p) in enumerate(rows,11):
        ws.cell(j,1,j-10);ws.cell(j,2,n);ws.cell(j,3,u);ws.cell(j,4,float(q));ws.cell(j,5,float(p));ws.cell(j,6,f"=ROUND(D{j}*E{j},2)")
    tr=11+len(rows);ws.cell(tr,1,"Итого с учётом НДС 22%");ws.cell(tr,6,f"=SUM(F11:F{tr-1})")
    ws.cell(tr+2,1,"* Столбцы 5 и 6 будут скорректированы по итогам конкурса пропорционально сниженной цене.")
    wb.save(path)
if __name__=="__main__":
    out=Path("tests/fixtures");out.mkdir(parents=True,exist_ok=True)
    make(out/"vor_object_b.xlsx","Западная",50,Decimal("115397900.00"))
    make(out/"vor_object_c.xlsx","Восточная",29,Decimal("47635990.22"))
