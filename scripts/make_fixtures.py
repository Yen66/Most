from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from openpyxl import Workbook, load_workbook

CENT = Decimal("0.01")
FIXED_TIME = (2020, 1, 1, 0, 0, 0)

DATA_PATH = Path("tests/fixtures/data/vor_object_a.json")


def load_vor_a() -> list[list]:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    rows = payload["items"]
    if len(rows) != 29:
        raise RuntimeError(f"vor_object_a.json: expected 29 positions, got {len(rows)}")
    return rows


VOR_A = load_vor_a()

TARGET_A = Decimal("35656922.00")
TARGET_B = Decimal("115397900.00")
TARGET_C = Decimal("47635990.22")


def money(value: Decimal | int | str) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def position_amount(quantity: Decimal | int | str, price: Decimal | int | str) -> Decimal:
    return (Decimal(str(quantity)) * money(price)).quantize(CENT, rounding=ROUND_HALF_UP)


def save_deterministic(workbook: Workbook, path: Path) -> None:
    workbook.properties.created = datetime(2020, 1, 1)
    workbook.properties.modified = datetime(2020, 1, 1)
    raw = BytesIO()
    workbook.save(raw)
    raw.seek(0)
    out = BytesIO()
    with ZipFile(raw, "r") as source, ZipFile(out, "w", ZIP_DEFLATED) as target:
        for name in sorted(source.namelist()):
            info = ZipInfo(name, FIXED_TIME)
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            payload = source.read(name)
            if name == "docProps/core.xml":
                text = payload.decode("utf-8")
                start = text.index("<dcterms:modified")
                value_start = text.index(">", start) + 1
                value_end = text.index("</dcterms:modified>", value_start)
                text = text[:value_start] + "2020-01-01T00:00:00Z" + text[value_end:]
                payload = text.encode("utf-8")
            target.writestr(info, payload)
    path.write_bytes(out.getvalue())


def build_vor(path: Path, rows: list[list], object_name: str, header_shift: int = 0) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Лист1"
    sheet.merge_cells("E1:F1")
    sheet.merge_cells("A4:F4")
    sheet.merge_cells("A8:F8")
    if len(rows) == 29:
        sheet.merge_cells("A40:E40")
        sheet.merge_cells("A41:F41")
    sheet["E1"] = "Приложение № 3\nк Государственному контракту №___"
    sheet["A4"] = "Ведомость объемов и стоимости работ (смета)"
    first_header = ["№ п/п", "Наименование видов и этапов работ", "Ед. изм", "Кол-во", "Ед. расценка, руб. ", "Стоимость, руб. "]
    second_header = ["№ п/п", "Наименование конструктивных решений (элементов), видов работ", "Ед. Изм.", "Количество (объём работ)", "Единичная расценка с НДС, руб.", "Всего с НДС, руб."]
    for column, value in enumerate(first_header, 1):
        sheet.cell(6, column, value)
    for column, value in enumerate(["1", "2", "3", "4", "5", "6"], 1):
        sheet.cell(7, column, value)
    sheet["A8"] = "Содержание искусственных сооружений на действующей сети автомобильных дорог общего пользования"
    for column, value in enumerate(second_header, 1):
        sheet.cell(9, column, value)
    for column, value in enumerate(["1", "2", "3", "4", "5*", "6*"], 1):
        sheet.cell(10, column, value)
    for row_number, row in enumerate(rows, 11):
        position, name, unit, quantity, price = row
        sheet.cell(row_number, 1, position if row_number == 11 else f"=A{row_number - 1}+1")
        sheet.cell(row_number, 2, name)
        sheet.cell(row_number, 3, unit)
        sheet.cell(row_number, 4, quantity)
        sheet.cell(row_number, 5, price)
        sheet.cell(row_number, 6, f"=ROUND(D{row_number}*E{row_number},2)")
    total_row = 11 + len(rows)
    if total_row != 40:
        sheet.merge_cells(start_row=total_row, start_column=1, end_row=total_row, end_column=5)
    sheet.cell(total_row, 1, "Итого с учётом НДС 22%")
    sheet.cell(total_row, 6, f"=SUM(F11:F{total_row - 1})")
    note_row = total_row + 2
    sheet.cell(note_row, 1, "* Столбцы 5 и 6 будут скорректированы  по итогам открытого конкурса в электронной форме, пропорционально сниженной цены.")
    sheet.cell(note_row + 2, 2, "Заказчик:")
    sheet.cell(note_row + 2, 4, "Подрядчик:")
    if header_shift:
        for merged in list(sheet.merged_cells.ranges):
            sheet.unmerge_cells(str(merged))
        sheet.move_range(f"A9:F{note_row + 2}", rows=header_shift, cols=0, translate=True)
        shifted_total = total_row + header_shift
        shifted_note = note_row + header_shift
        sheet.merge_cells(start_row=shifted_total, start_column=1, end_row=shifted_total, end_column=5)
        if len(rows) == 29:
            sheet.merge_cells(start_row=shifted_total + 1, start_column=1, end_row=shifted_total + 1, end_column=6)
        sheet.merge_cells("E1:F1")
        sheet.merge_cells("A4:F4")
        sheet.merge_cells("A8:F8")
    save_deterministic(workbook, path)


def synthetic_rows(count: int, target: Decimal, prefix: str) -> list[list]:
    names = [
        "Фрезерование асфальтобетонного покрытия",
        "Разборка деформационного шва",
        "Ремонт защитного слоя бетона",
        "Устройство гидроизоляции",
        "Монтаж барьерного ограждения",
        "Пескоструйная очистка поверхности",
        "Устройство выравнивающего слоя",
        "Восстановление дорожной одежды",
    ]
    rows: list[list] = []
    subtotal = Decimal("0")
    for position in range(1, count):
        quantity = Decimal((position % 9) + 1)
        price = money(Decimal("15000") + Decimal(position * 731))
        subtotal += position_amount(quantity, price)
        rows.append([position, f"{names[(position - 1) % len(names)]} — {prefix} {position}", "ед.", quantity, price])
    last_price = money(target - subtotal)
    rows.append([count, f"Завершающий комплекс работ — {prefix}", "ед.", Decimal("1"), last_price])
    actual = sum((position_amount(row[3], row[4]) for row in rows), Decimal("0"))
    if actual != target:
        raise RuntimeError(f"{prefix}: expected {target}, got {actual}")
    return rows


def split_half(value: Decimal) -> tuple[Decimal, Decimal]:
    first = (value / Decimal("2")).quantize(CENT, rounding=ROUND_HALF_UP)
    return first, value - first


def build_schedule(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Календарный график"
    for cell_range in ["A1:W1", "A2:W2", "A4:W4", "A5:W5", "A8:W8", "A58:I58", "A60:W60"]:
        sheet.merge_cells(cell_range)
    sheet["A1"] = "КАЛЕНДАРНЫЙ ГРАФИК ПРОИЗВОДСТВА РАБОТ — СЕВЕРНАЯ"
    sheet["A2"] = "Мост через реку Северная, км 10+100 А-900. Период работ: 05.10.2026–15.11.2026."
    sheet["A4"] = "Ресурсный план: 05–09.10 до 10 чел.; далее Северная и Восточная делят мобильную бригаду 10 чел. По Северной в разные периоды 4–6 чел., на критических операциях ресурс перераспределяется."
    sheet["A5"] = "Реверс: сторона 1 06–24.10 → отдельный день переключения 25.10 → сторона 2 26.10–12.11 → завершение 13–15.11. Это не 10 дней: объект идет 42 календарных дня."
    headers = ["№ сметы", "Наименование работ", "Фронт/сторона", "Ед.", "Объем", "Начало", "Окончание", "Дни", "Звено, чел.", "Стоимость, руб.", "Комментарий"]
    periods = ["01–04.10", "05–09.10", "10–15.10", "16–20.10", "21–25.10", "26–31.10", "01–05.11", "06–10.11", "11–15.11", "16–20.11", "21–23.11", "24–30.11"]
    for column, value in enumerate(headers + periods, 1):
        sheet.cell(7, column, value)

    source = {int(row[0]): row for row in VOR_A}
    amounts = {position: position_amount(row[3], row[4]) for position, row in source.items()}
    entries: list[tuple[str, int | None, str | None]] = [("group", None, "ПОДГОТОВКА")]
    for position in range(1, 11):
        entries.append(("task", position, "ОДД / весь объект"))
    entries.append(("group", None, "СТОРОНА 1"))
    for position in range(11, 18):
        entries.append(("task", position, "Сторона 1"))
    entries.append(("group", None, "ПАРАЛЛЕЛЬНО"))
    for position in range(18, 25):
        entries.append(("task", position, "Сторона 1"))
    entries.append(("group", None, "ПЕРЕКЛЮЧЕНИЕ"))
    entries.append(("group", None, "СТОРОНА 2"))
    for position in range(11, 25):
        entries.append(("task", position, "Сторона 2"))
    entries.append(("group", None, "ЗАВЕРШЕНИЕ"))
    for position in range(25, 30):
        entries.append(("task", position, "весь объект"))
    if len(entries) != 49:
        raise RuntimeError(f"schedule layout must contain 49 rows, got {len(entries)}")

    task_seen: dict[int, int] = {}
    for row_number, (kind, position, front) in enumerate(entries, 8):
        if kind == "group":
            sheet.merge_cells(start_row=row_number, start_column=1, end_row=row_number, end_column=23)
            sheet.cell(row_number, 1, front)
            continue
        assert position is not None
        source_row = source[position]
        _, name, unit, quantity_raw, _ = source_row
        quantity = Decimal(str(quantity_raw))
        amount = amounts[position]
        if 11 <= position <= 24:
            first_quantity = quantity / Decimal("2")
            second_quantity = quantity - first_quantity
            first_amount, second_amount = split_half(amount)
            side_index = task_seen.get(position, 0)
            task_seen[position] = side_index + 1
            task_quantity = first_quantity if side_index == 0 else second_quantity
            task_amount = first_amount if side_index == 0 else second_amount
        else:
            task_quantity = quantity
            task_amount = amount
        if position <= 10:
            start_on, end_on, period_index = date(2026, 10, 5), date(2026, 10, 9), 1
        elif front == "Сторона 1":
            start_on, end_on, period_index = date(2026, 10, 6), date(2026, 10, 24), 2
        elif front == "Сторона 2":
            start_on, end_on, period_index = date(2026, 10, 26), date(2026, 11, 12), 6
        else:
            start_on, end_on, period_index = date(2026, 11, 13), date(2026, 11, 15), 8
        values = [position, name, front, unit, task_quantity, start_on, end_on, (end_on - start_on).days + 1, 4 + (position % 7), task_amount, ""]
        for column, value in enumerate(values, 1):
            sheet.cell(row_number, column, value)
        sheet.cell(row_number, 12 + period_index, task_quantity)

    sheet["A58"] = "ИТОГО ПО ВЕДОМОСТИ"
    sheet["J58"] = "=SUM(J8:J57)"
    sheet["A60"] = "Примечание: объемы по периодам — плановое календарное распределение, а не подтверждённая норма выработки."
    save_deterministic(workbook, path)


def verify_vor(path: Path, target: Decimal) -> None:
    workbook = load_workbook(path, data_only=False)
    sheet = workbook[workbook.sheetnames[0]]
    header_row = None
    total_row = None
    for row in range(1, sheet.max_row + 1):
        values = [str(sheet.cell(row, column).value or "") for column in range(1, 7)]
        joined = " | ".join(values).lower()
        if "единичная расценка с ндс" in joined and "количество" in joined:
            header_row = row
        if "итого с учётом ндс" in joined:
            total_row = row
            break
    if header_row is None or total_row is None:
        raise RuntimeError(f"{path.name}: structure not found")
    total = Decimal("0")
    for row in range(header_row + 2, total_row):
        name = sheet.cell(row, 2).value
        if not isinstance(name, str) or not name.strip():
            continue
        quantity = sheet.cell(row, 4).value
        price = sheet.cell(row, 5).value
        if quantity is None or price is None:
            raise RuntimeError(f"{path.name}: row {row} has incomplete item")
        total += position_amount(quantity, price)
    if total != target:
        raise RuntimeError(f"{path.name}: expected {target}, got {total}")


def verify_schedule(path: Path) -> None:
    workbook = load_workbook(path, data_only=False)
    sheet = workbook["Календарный график"]
    total = Decimal("0")
    for row in range(8, 58):
        value = sheet.cell(row, 10).value
        if value is not None and not isinstance(value, str):
            total += money(value)
    if total != TARGET_A:
        raise RuntimeError(f"{path.name}: expected {TARGET_A}, got {total}")
    for row in range(8, 58):
        quantity = sheet.cell(row, 5).value
        if quantity is None:
            continue
        period_total = sum(
            (Decimal(str(sheet.cell(row, column).value)) for column in range(12, 24) if sheet.cell(row, column).value is not None),
            Decimal("0"),
        )
        if period_total != Decimal(str(quantity)):
            raise RuntimeError(
                f"{path.name}: row {row} period volume {period_total} != quantity {quantity}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("tests/fixtures/generated"))
    parser.add_argument("--shift-header", type=int, default=0)
    args = parser.parse_args(argv)
    output = args.out
    output.mkdir(parents=True, exist_ok=True)
    rows_a = load_vor_a()
    build_vor(output / "vor_object_a.xlsx", rows_a, "Северная")
    build_vor(output / "vor_object_b.xlsx", synthetic_rows(50, TARGET_B, "Западная"), "Западная")
    build_vor(output / "vor_object_c.xlsx", synthetic_rows(29, TARGET_C, "Восточная"), "Восточная")
    build_schedule(output / "schedule_object_a.xlsx")
    if args.shift_header:
        build_vor(
            output / f"vor_object_a_shifted_{args.shift_header}.xlsx",
            rows_a,
            "Северная",
            header_shift=args.shift_header,
        )
    verify_vor(output / "vor_object_a.xlsx", TARGET_A)
    verify_vor(output / "vor_object_b.xlsx", TARGET_B)
    verify_vor(output / "vor_object_c.xlsx", TARGET_C)
    verify_schedule(output / "schedule_object_a.xlsx")
    if args.shift_header:
        verify_vor(output / f"vor_object_a_shifted_{args.shift_header}.xlsx", TARGET_A)
    print(f"fixtures generated and verified: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
