from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from construction_os.importers import parse_schedule, parse_vor, persist_schedule, persist_vor
from construction_os.reports import format_money
from construction_os.storage import make_engine
from construction_os.storage.queries import object_revenues, portfolio_revenue, verify_object


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="construction-os")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("path")
    import_parser.add_argument("--kind", choices=["vor", "schedule"], required=True)
    import_parser.add_argument("--company", required=True)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--object", required=True)
    verify_parser.add_argument("--company", required=True)

    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("--date", type=date.fromisoformat, required=True)
    report_parser.add_argument("--company")

    debug_parser = subparsers.add_parser(
        "debug-format",
        help="форматтер чисел; не выполняет расчёт объекта",
    )
    debug_parser.add_argument("values", type=Decimal, nargs="*")
    return parser


def main(argv=None) -> int:
    arguments = _parser().parse_args(argv)
    engine = make_engine()
    if arguments.command == "debug-format":
        for value in arguments.values:
            print(format_money(value))
        return 0
    with Session(engine) as session:
        if arguments.command == "import":
            if arguments.kind == "vor":
                parsed = parse_vor(arguments.path)
                result = persist_vor(session, arguments.company, parsed, arguments.path)
            else:
                parsed = parse_schedule(arguments.path)
                result = persist_schedule(session, arguments.company, parsed, arguments.path)
            session.commit()
            status = "duplicate skipped" if result.skipped_duplicate else "created"
            print(f"Import: {status}; entities: {result.created_entities}; document: {result.document_id}")
            return 0
        if arguments.command == "verify":
            try:
                differences = verify_object(session, arguments.company, arguments.object)
            except LookupError as error:
                print(str(error))
                return 2
            print(f"Differences: {len(differences)}")
            for position, field in differences:
                print(f"{position}: {field}")
            return 0 if not differences else 1
        rows = object_revenues(session, arguments.date, arguments.company)
        if not rows:
            print("No imported objects")
            return 2
        for row in rows:
            print(
                f"{row.company_name} / {row.object_name}: "
                f"с НДС {format_money(row.revenue.gross)}; "
                f"без НДС {format_money(row.revenue.net)}; "
                f"НДС {format_money(row.revenue.vat)}"
            )
        portfolio = portfolio_revenue(rows, arguments.date)
        print(f"Портфель с НДС: {format_money(portfolio.gross)}")
        print(f"Портфель без НДС: {format_money(portfolio.net)}")
        print(f"Портфель НДС: {format_money(portfolio.vat)}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
