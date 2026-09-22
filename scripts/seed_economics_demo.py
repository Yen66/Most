from __future__ import annotations

import os
import sys
from datetime import date
from decimal import Decimal

from openpyxl import load_workbook
from sqlalchemy.orm import Session

from construction_os.storage import make_engine
from construction_os.storage.models import CompanyRow, ObjectRow, ValueSourceRow, WorkItemRow


def main(path):
    engine = make_engine(os.environ["DATABASE_URL"])
    with Session(engine) as s:
        c = CompanyRow(name="Demo Co")
        s.add(c)
        s.flush()
        src = ValueSourceRow(company_id=c.id, source_type="user_input", confidence="confirmed")
        s.add(src)
        s.flush()
        o = ObjectRow(company_id=c.id, name="Demo Object", valid_from=date(2026, 9, 20))
        s.add(o)
        s.flush()
        w = WorkItemRow(
            company_id=c.id,
            object_id=o.id,
            position_no=1,
            name="Demo",
            unit="шт",
            quantity=Decimal("1"),
            price_gross=Decimal("1220000"),
            amount_gross=Decimal("1220000"),
            vat_rate=Decimal("0.22"),
            source_id=src.id,
            valid_from=date(2026, 9, 20),
        )
        s.add(w)
        s.commit()
    wb = load_workbook(path)
    ws = wb["Затраты"]
    for code, amount in (
        ("MAT", 500000),
        ("LAB", 250000),
        ("MACH_OWN", 70000),
        ("OVR_SITE", 50000),
        ("BANK_GUAR", 27000),
    ):
        ws.append(
            [
                "Demo Object",
                None,
                code,
                None,
                None,
                None,
                amount,
                "fixed",
                None,
                "net",
                "demo",
                date(2026, 9, 20),
                None,
            ]
        )
    wb.save(path)


if __name__ == "__main__":
    main(sys.argv[1])
