from __future__ import annotations

from pathlib import Path

from construction_os.importers.intake import intake_batch, receipt_json


def configure_intake(sub) -> None:
    parser = sub.add_parser("intake", help="приём нескольких файлов и квитанция")
    parser.add_argument("--company", required=True, help="укажите --company")
    parser.add_argument("--report")
    parser.add_argument("files", nargs="+")


def run_intake(args, session) -> int:
    receipt = intake_batch(session, args.company, args.files)
    session.commit()
    print("Файл | Тип | Действие | Позиций | С НДС")
    for item in receipt["files"]:
        print(
            f'{item["file"]} | {item["type"]} | {item["action"]} | '
            f'{item["positions"]} | {item["total_gross"] or "—"}'
        )
        for warning in item["warnings"]:
            print(f"  ПРЕДУПРЕЖДЕНИЕ: {warning}")
        for error in item["errors"]:
            print(f"  ОШИБКА: {error}")
    summary = receipt["summary"]
    print(
        f'ИТОГО: imported: {summary["imported"]}, skipped: {summary["skipped"]}, '
        f'rejected: {summary["rejected"]}; портфель с НДС: '
        f'{summary["portfolio_gross"]}; без НДС: {summary["portfolio_net"]}'
    )
    if args.report:
        Path(args.report).write_text(receipt_json(receipt) + "\n", encoding="utf-8")
    return 0 if summary["imported"] or summary["skipped"] else 2
