from datetime import date
from decimal import Decimal

from sqlalchemy import select

from construction_os.importers import parse_schedule, parse_vor, persist_schedule, persist_vor
from construction_os.storage.models import CompanyRow, DocumentRow, WorkItemRow
from construction_os.storage.queries import object_revenues, portfolio_revenue, verify_object


def _load_pipeline(session, fixtures_dir, company="Подрядчик"):
    for suffix in ("a", "b", "c"):
        path = fixtures_dir / f"vor_object_{suffix}.xlsx"
        persist_vor(session, company, parse_vor(path), path, imported_on=date(2026, 9, 20))
    schedule_path = fixtures_dir / "schedule_object_a.xlsx"
    persist_schedule(session, company, parse_schedule(schedule_path), schedule_path)
    session.flush()


def test_pipeline_db_seven_reference_values(db_session, fixtures_dir):
    _load_pipeline(db_session, fixtures_dir)
    company = db_session.scalar(select(CompanyRow).where(CompanyRow.name == "Подрядчик"))
    items_a = list(
        db_session.scalars(select(WorkItemRow).where(WorkItemRow.company_id == company.id))
    )
    assert len(items_a) == 108
    assert verify_object(db_session, "Подрядчик", "vor_object_a") == []
    rows = object_revenues(db_session, date(2026, 9, 20), "Подрядчик")
    by_name = {row.object_name: row.revenue for row in rows}
    assert by_name["vor_object_a"].gross == Decimal("35656922.00")
    assert by_name["vor_object_a"].net == Decimal("29226985.25")
    assert by_name["vor_object_a"].vat == Decimal("6429936.75")
    portfolio = portfolio_revenue(rows, date(2026, 9, 20))
    assert portfolio.gross == Decimal("198690812.22")
    assert portfolio.net == Decimal("162861321.49")


def test_reimport_same_sha_is_idempotent(sqlite_session, fixtures_dir):
    path = fixtures_dir / "vor_object_a.xlsx"
    parsed = parse_vor(path)
    first = persist_vor(sqlite_session, "A", parsed, path)
    sqlite_session.commit()
    second = persist_vor(sqlite_session, "A", parsed, path)
    assert first.skipped_duplicate is False
    assert second.skipped_duplicate is True
    assert len(sqlite_session.scalars(select(DocumentRow)).all()) == 1


def test_company_isolation_in_report(sqlite_session, fixtures_dir):
    path_a = fixtures_dir / "vor_object_a.xlsx"
    path_c = fixtures_dir / "vor_object_c.xlsx"
    persist_vor(sqlite_session, "Первая", parse_vor(path_a), path_a)
    persist_vor(sqlite_session, "Вторая", parse_vor(path_c), path_c)
    sqlite_session.commit()
    rows = object_revenues(sqlite_session, date(2026, 9, 20), "Первая")
    assert len(rows) == 1
    assert rows[0].revenue.gross == Decimal("35656922.00")
