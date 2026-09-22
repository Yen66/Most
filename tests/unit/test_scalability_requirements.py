from __future__ import annotations

import ast
import os
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from construction_os.calc import calculate_revenue_for_date
from construction_os.importers import parse_vor
from construction_os.references import (
    ContractType,
    NoteType,
    RateNotFoundError,
    SourceType,
    Unit,
    get_rate,
)
from construction_os.storage.models import (
    Base,
    CompanyRow,
    ContractRow,
    CostArticleRow,
    CostEntryRow,
    DocumentRow,
    ObjectRow,
    ScenarioParamRow,
    ScenarioRow,
    ScheduleNoteRow,
    ScheduleTaskRow,
    ValueConfirmationRow,
    ValueRefRow,
    ValueSourceRow,
    WorkItemRow,
)
from construction_os.storage.repositories import (
    TENANT_REPOSITORIES,
    ImmutableRecordError,
    WorkItemRepository,
)

ROOT = Path(__file__).resolve().parents[2]
EXCLUDED_TABLES = {"companies", "reference_rates", "cost_articles"}
FORBIDDEN_RATES = {0.20, 0.22, 1.22, 0.25, 0.30, 0.14, 0.027, 1.25, 0.75, 0.03, 0.87}


def _seed_tenant_rows(session, company_name: str):
    company = CompanyRow(name=company_name)
    session.add(company)
    session.flush()
    document = DocumentRow(
        company_id=company.id,
        kind="vor",
        original_filename=f"{company_name}.xlsx",
        stored_path=f"/{company_name}.xlsx",
        sha256=(company_name.encode("utf-8").hex() + "0" * 64)[:64],
    )
    session.add(document)
    session.flush()
    source = ValueSourceRow(
        company_id=company.id,
        source_type="document",
        document_id=document.id,
        confidence="exact",
    )
    contract = ContractRow(company_id=company.id, contract_type="unknown", price_is_final=False)
    session.add_all([source, contract])
    session.flush()
    obj = ObjectRow(company_id=company.id, contract_id=contract.id, name=f"O-{company_name}")
    session.add(obj)
    session.flush()
    work = WorkItemRow(
        company_id=company.id,
        object_id=obj.id,
        contract_id=contract.id,
        position_no=1,
        name="Работа",
        unit="шт",
        quantity=Decimal("1"),
        price_gross=Decimal("1"),
        amount_gross=Decimal("1"),
        vat_rate=Decimal("0.22"),
        document_id=document.id,
        source_id=source.id,
        valid_from=date(2026, 1, 1),
    )
    session.add(work)
    session.flush()
    value_ref = ValueRefRow(
        company_id=company.id,
        entity_name="work_items",
        entity_id=work.id,
        field_name="quantity",
        source_id=source.id,
    )
    task = ScheduleTaskRow(
        company_id=company.id,
        object_id=obj.id,
        position_no=1,
        name="Работа",
        quantity=Decimal("1"),
        amount=Decimal("1"),
        source_id=source.id,
    )
    note = ScheduleNoteRow(
        company_id=company.id,
        object_id=obj.id,
        note_type="period",
        text="Период",
        source_id=source.id,
    )
    confirmation = ValueConfirmationRow(
        company_id=company.id,
        entity_name="work_items",
        entity_id=work.id,
        action="imported",
        actor="test",
    )
    session.add_all([value_ref, task, note, confirmation])
    session.flush()
    article = session.scalar(select(CostArticleRow).where(CostArticleRow.code == "MAT"))
    if article is None:
        article = CostArticleRow(code="MAT", category="direct", name="Материалы", is_active=True)
        session.add(article)
        session.flush()
    cost = CostEntryRow(
        company_id=company.id,
        object_id=obj.id,
        article_code="MAT",
        amount=Decimal("1"),
        amount_type="fixed",
        vat_mode="net",
        source_id=source.id,
        valid_from=date(2026, 1, 1),
        created_by="test",
    )
    scenario = ScenarioRow(
        company_id=company.id,
        name=f"S-{company_name}",
        object_id=obj.id,
        base_date=date(2026, 1, 1),
        source_id=source.id,
        created_by="test",
        valid_from=date(2026, 1, 1),
    )
    session.add_all([cost, scenario])
    session.flush()
    param = ScenarioParamRow(
        company_id=company.id,
        scenario_id=scenario.id,
        param_type="cost_multiplier",
        scope="all",
        param_value=Decimal("1"),
        created_by="test",
    )
    session.add(param)
    session.flush()
    rows = {
        row.__tablename__: row
        for row in (
            document,
            source,
            value_ref,
            contract,
            obj,
            work,
            task,
            note,
            confirmation,
            cost,
            scenario,
            param,
        )
    }
    return company, rows


def test_M01_company_id_everywhere():
    for name, table in Base.metadata.tables.items():
        if name in EXCLUDED_TABLES:
            continue
        column = table.c.company_id
        assert column.nullable is False
        assert column.index is True or any(
            column.name in [c.name for c in index.columns] for index in table.indexes
        )


def test_M02_tenant_isolation_repository_catalog_complete():
    names = {repository.model.__tablename__ for repository in TENANT_REPOSITORIES}
    assert names == set(Base.metadata.tables) - EXCLUDED_TABLES


def test_M02_tenant_isolation_all_repositories(sqlite_session):
    company_a, rows_a = _seed_tenant_rows(sqlite_session, "A")
    company_b, rows_b = _seed_tenant_rows(sqlite_session, "B")
    for repository_type in TENANT_REPOSITORIES:
        table_name = repository_type.model.__tablename__
        repository = repository_type(sqlite_session)
        row_a = rows_a[table_name]
        row_b = rows_b[table_name]
        assert repository.get(company_a.id, row_a.id).id == row_a.id
        assert repository.get(company_a.id, row_b.id) is None
        assert repository.get(company_b.id, row_a.id) is None
        ids_a = {row.id for row in repository.list_current(company_a.id)}
        ids_b = {row.id for row in repository.list_current(company_b.id)}
        assert row_a.id in ids_a and row_b.id not in ids_a
        assert row_b.id in ids_b and row_a.id not in ids_b


def test_M03_values_are_superseded_not_updated(sqlite_session):
    company = CompanyRow(name="A")
    sqlite_session.add(company)
    sqlite_session.flush()
    source = ValueSourceRow(company_id=company.id, source_type="document", confidence="exact")
    sqlite_session.add(source)
    sqlite_session.flush()
    obj = ObjectRow(company_id=company.id, name="O")
    sqlite_session.add(obj)
    sqlite_session.flush()
    repo = WorkItemRepository(sqlite_session)
    old = repo.add(
        company.id,
        object_id=obj.id,
        position_no=1,
        name="Работа",
        unit="шт",
        quantity=Decimal("1"),
        price_gross=Decimal("10"),
        amount_gross=Decimal("10"),
        vat_rate=Decimal("0.22"),
        source_id=source.id,
        valid_from=date(2026, 1, 1),
    )
    new = repo.supersede(
        company.id, old.id, {"price_gross": Decimal("11")}, "correction", "test", date(2026, 2, 1)
    )
    assert new.id != old.id
    historical = repo.get_on_date(company.id, old.id, date(2026, 1, 15))
    assert historical.price_gross == Decimal("10")
    assert historical.source_id == source.id
    assert new.source_id == source.id
    with pytest.raises(ImmutableRecordError):
        repo.update(old.id)
    with pytest.raises(ImmutableRecordError):
        repo.delete(old.id)
    for table_name in (
        "contracts",
        "objects",
        "work_items",
        "schedule_tasks",
        "cost_entries",
        "scenarios",
    ):
        assert {"valid_from", "valid_to", "superseded_by", "replace_reason"} <= set(Base.metadata.tables[table_name].c.keys())


def test_M04_no_rate_literals_outside_references():
    violations = []
    for path in (ROOT / "src").rglob("*.py"):
        if "references" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, float)
                and node.value in FORBIDDEN_RATES
            ):
                violations.append((path, node.lineno, node.value))
    assert violations == []


def test_M05_reference_catalog_is_mandatory():
    assert str(get_rate("VAT_RATE", date(2025, 9, 1)).value) == "0.20"
    assert str(get_rate("VAT_RATE", date(2026, 9, 1)).value) == "0.22"
    assert str(get_rate("VAT_RATE", date(2025, 12, 31)).value) == "0.20"
    assert str(get_rate("VAT_RATE", date(2026, 1, 1)).value) == "0.22"
    with pytest.raises(RateNotFoundError):
        get_rate("VAT_RATE", date(2010, 1, 1))


def test_M06_domain_does_not_import_sqlalchemy():
    violations = []
    for path in (ROOT / "src" / "construction_os" / "domain").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                violations.extend(
                    alias.name for alias in node.names if alias.name.startswith("sqlalchemy")
                )
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("sqlalchemy"):
                violations.append(node.module)
    assert violations == []


def test_M07_calc_is_pure_from_storage_and_io():
    result = calculate_revenue_for_date(Decimal("122.00"), date(2026, 9, 20))
    assert result.net == Decimal("100.00")
    assert result.vat == Decimal("22.00")
    for path in (ROOT / "src" / "construction_os" / "calc").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
            elif isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
        assert not any(name.startswith("construction_os.storage") for name in imports)
        assert "openpyxl" not in imports


def test_M08_environment_settings_only():
    assert not (ROOT / ".env").exists()
    content = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert content.strip() == "DATABASE_URL="


def test_M09_migrations_from_zero(tmp_path):
    database = tmp_path / "migration.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+pysqlite:///{database}"
    env["PYTHONPATH"] = str(ROOT / "src")
    for command in (["upgrade", "head"], ["downgrade", "base"], ["upgrade", "head"]):
        completed = subprocess.run(
            [sys.executable, "-m", "alembic", *command],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr


def test_M10_no_single_tenant_data_tables():
    data_tables = set(Base.metadata.tables) - EXCLUDED_TABLES
    assert data_tables
    assert all("company_id" in Base.metadata.tables[name].c for name in data_tables)


def test_M11_reference_types_are_extensible():
    assert Unit.PIECE.value == "шт"
    assert ContractType.UNKNOWN.value == "unknown"
    assert SourceType.DOCUMENT.value == "document"
    assert NoteType.RESOURCE_PLAN.value == "resource_plan"


def test_M11_calc_and_importers_do_not_branch_on_unit_values():
    files = list((ROOT / "src" / "construction_os" / "calc").rglob("*.py")) + list(
        (ROOT / "src" / "construction_os" / "importers").rglob("*.py")
    )
    text = "\n".join(path.read_text(encoding="utf-8") for path in files)
    assert "Unit.PIECE" not in text
    assert "Unit.CUBIC_METER" not in text


def test_M12_importer_finds_shifted_header(fixtures_dir, tmp_path):
    subprocess.run(
        [
            sys.executable,
            "scripts/make_fixtures.py",
            "--out",
            str(tmp_path),
            "--shift-header",
            "2",
        ],
        cwd=ROOT,
        check=True,
    )
    original = parse_vor(fixtures_dir / "vor_object_a.xlsx")
    parsed = parse_vor(tmp_path / "vor_object_a_shifted_2.xlsx")
    assert parsed.header_row == 11
    assert len(parsed.items) == 29
    assert parsed.total_gross == Decimal("35656922.00")
    assert parsed.sha256 == original.sha256


def test_M03_postgres_trigger_rejects_direct_update(db_session):
    if db_session.bind.dialect.name != "postgresql":
        pytest.skip("PostgreSQL trigger test")
    company = CompanyRow(name="Trigger Co")
    db_session.add(company)
    db_session.flush()
    source = ValueSourceRow(company_id=company.id, source_type="document", confidence="exact")
    db_session.add(source)
    db_session.flush()
    obj = ObjectRow(company_id=company.id, name="Trigger Object")
    db_session.add(obj)
    db_session.flush()
    item = WorkItemRepository(db_session).add(
        company.id,
        object_id=obj.id,
        position_no=1,
        name="Работа",
        unit="шт",
        quantity=Decimal("1"),
        price_gross=Decimal("10"),
        amount_gross=Decimal("10"),
        vat_rate=Decimal("0.22"),
        source_id=source.id,
        valid_from=date(2026, 1, 1),
    )
    from sqlalchemy import text

    with pytest.raises(Exception, match="immutable"), db_session.begin_nested():
        db_session.execute(
            text("UPDATE work_items SET price_gross = 11 WHERE id = :id"), {"id": item.id}
        )
    with pytest.raises(Exception, match="immutable"), db_session.begin_nested():
        db_session.execute(text("DELETE FROM work_items WHERE id = :id"), {"id": item.id})
