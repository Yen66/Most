from decimal import Decimal
from openpyxl import Workbook
from construction_os.importers import parse_vor

def make_real_shape(path):
    wb=Workbook();ws=wb.active;ws.title="Лист1"
    for c,v in enumerate(["№ п/п","Наименование работ","Ед.","Количество","Единичная расценка с НДС","Всего с НДС"],1):ws.cell(9,c,v)
    ws.cell(11,1,1);ws.cell(11,2,"Установка щитов");ws.cell(11,3,"шт");ws.cell(11,4,2);ws.cell(11,5,42860.189999999995);ws.cell(11,6,"=ROUND(D11*E11,2)")
    ws.cell(12,1,"Итого с учётом НДС 22%");ws.cell(12,6,"=SUM(F11:F11)")
    wb.save(path)

def test_structure_header_and_float(tmp_path):
    p=tmp_path/"v.xlsx";make_real_shape(p);v=parse_vor(p)
    assert v.header_row==9 and len(v.items)==1
    assert v.items[0].price_gross==Decimal("42860.19")
    assert v.items[0].amount_gross==Decimal("85720.38")
    assert v.vat_rate==Decimal("0.22")
