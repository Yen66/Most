from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_versioned_values"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None

MIGRATION_VALID_FROM = "2026-09-20"

COST_ARTICLES = (
    ("MAT", "direct", "Материалы и конструкции"), ("MAT_DELIVERY", "direct", "Доставка материалов"),
    ("MAT_WASTE", "direct", "Потери и отходы материалов"), ("LAB", "direct", "ФОТ рабочих начисленный"),
    ("LAB_TAX", "direct", "Страховые взносы и НДФЛ"), ("LAB_SHIFT", "direct", "Вахта: проезд, проживание, питание"),
    ("MACH_OWN", "direct", "Собственная техника: машино-часы"), ("MACH_RENT", "direct", "Арендованная техника"),
    ("MACH_FUEL", "direct", "ГСМ"), ("MACH_MOVE", "direct", "Перебазировка техники"),
    ("MACH_IDLE", "direct", "Простой техники"), ("MACH_REPAIR", "direct", "Ремонт, ТО, амортизация"),
    ("SUB", "direct", "Субподряд"), ("LOG", "direct", "Логистика и транспорт"),
    ("OVR_SITE", "indirect", "Накладные расходы объекта"), ("OVR_COMPANY", "indirect", "Накладные расходы компании"),
    ("TEMP_FAC", "indirect", "Временные здания и сооружения"), ("TRAFFIC", "indirect", "Организация дорожного движения"),
    ("LAB_CONTROL", "indirect", "Лабораторный контроль и геодезия"), ("MOB", "indirect", "Мобилизация и демобилизация"),
    ("WINTER", "indirect", "Зимнее удорожание"), ("DRAIN", "indirect", "Водоотлив"), ("INSUR", "indirect", "Страхование"),
    ("BANK_GUAR", "financial", "Банковская гарантия"), ("TREASURY", "financial", "Казначейское сопровождение"),
    ("FINANCE", "financial", "Финансирование кассового разрыва"), ("WARRANTY_RET", "financial", "Гарантийное удержание"),
    ("PENALTY_OURS", "financial", "Неустойка наша"), ("OTHER", "other", "Прочие затраты"),
)

def _version_columns(batch, table: str) -> None:
    batch.add_column(sa.Column("valid_from", sa.Date(), nullable=False, server_default=MIGRATION_VALID_FROM))
    batch.add_column(sa.Column("valid_to", sa.Date()))
    batch.add_column(sa.Column("superseded_by", sa.Uuid()))
    batch.add_column(sa.Column("replace_reason", sa.Text()))
    batch.alter_column("valid_from", server_default=None)
    batch.create_foreign_key(f"fk_{table}_superseded_by", table, ["superseded_by"], ["id"])

def _upgrade_versioned_existing() -> None:
    bind = op.get_bind()
    naming = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
    with op.batch_alter_table("contracts", recreate="auto", naming_convention=naming) as batch:
        batch.add_column(sa.Column("signed_on", sa.Date()))
        batch.add_column(sa.Column("award_reduction_factor", sa.Numeric(9, 6)))
        _version_columns(batch, "contracts")
    with op.batch_alter_table("objects", recreate="always" if bind.dialect.name == "sqlite" else "auto", naming_convention=naming) as batch:
        if bind.dialect.name == "sqlite":
            batch.drop_constraint("uq_objects_company_id", type_="unique")
        else:
            batch.drop_constraint("objects_company_id_name_key", type_="unique")
        _version_columns(batch, "objects")
    with op.batch_alter_table("schedule_tasks", recreate="auto", naming_convention=naming) as batch:
        _version_columns(batch, "schedule_tasks")
    op.create_index("uq_contract_current", "contracts", ["company_id", "number"], unique=True, postgresql_where=sa.text("valid_to IS NULL"), sqlite_where=sa.text("valid_to IS NULL"))
    op.create_index("uq_object_current", "objects", ["company_id", "name"], unique=True, postgresql_where=sa.text("valid_to IS NULL"), sqlite_where=sa.text("valid_to IS NULL"))
    op.create_index("uq_schedule_task_current", "schedule_tasks", ["company_id", "object_id", "position_no", "front"], unique=True, postgresql_where=sa.text("valid_to IS NULL"), sqlite_where=sa.text("valid_to IS NULL"))

def _create_cost_tables() -> None:
    op.create_table("cost_articles",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("code", sa.Text(), nullable=False, unique=True),
        sa.Column("category", sa.Text(), nullable=False), sa.Column("name", sa.Text(), nullable=False), sa.Column("unit", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("sort_order", sa.Integer()),
        sa.CheckConstraint("category IN ('direct','indirect','financial','other')", name="ck_cost_article_category"))
    article = sa.table("cost_articles", sa.column("id", sa.Uuid()), sa.column("code", sa.Text()), sa.column("category", sa.Text()), sa.column("name", sa.Text()), sa.column("sort_order", sa.Integer()))
    from uuid import uuid4
    op.bulk_insert(article, [{"id": uuid4(), "code": code, "category": category, "name": name, "sort_order": i} for i, (code, category, name) in enumerate(COST_ARTICLES, 1)])
    op.create_table("cost_entries",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("object_id", sa.Uuid(), sa.ForeignKey("objects.id"), nullable=False), sa.Column("contract_id", sa.Uuid(), sa.ForeignKey("contracts.id")),
        sa.Column("work_item_id", sa.Uuid(), sa.ForeignKey("work_items.id")), sa.Column("article_code", sa.Text(), sa.ForeignKey("cost_articles.code"), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4)), sa.Column("unit", sa.Text()), sa.Column("price", sa.Numeric(18, 4)),
        sa.Column("amount", sa.Numeric(18, 2)), sa.Column("amount_type", sa.Text(), nullable=False, server_default="fixed"),
        sa.Column("rate_value", sa.Numeric(9, 6)), sa.Column("vat_mode", sa.Text(), nullable=False, server_default="unknown"),
        sa.Column("vat_rate", sa.Numeric(9, 6)), sa.Column("source_id", sa.Uuid(), sa.ForeignKey("value_sources.id"), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False), sa.Column("valid_to", sa.Date()),
        sa.Column("superseded_by", sa.Uuid(), sa.ForeignKey("cost_entries.id")), sa.Column("replace_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("created_by", sa.Text(), nullable=False),
        sa.CheckConstraint("amount_type IN ('fixed','share_of_revenue')", name="ck_cost_entry_amount_type"),
        sa.CheckConstraint("vat_mode IN ('gross','net','unknown')", name="ck_cost_entry_vat_mode"),
        sa.CheckConstraint("(amount_type = 'fixed' AND amount IS NOT NULL AND rate_value IS NULL) OR (amount_type = 'share_of_revenue' AND amount IS NULL AND rate_value IS NOT NULL)", name="ck_cost_entry_amount_shape"))
    op.create_index("ix_cost_entries_company_id", "cost_entries", ["company_id"])

def _create_scenario_tables() -> None:
    op.create_table("scenarios",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False), sa.Column("object_id", sa.Uuid(), sa.ForeignKey("objects.id")),
        sa.Column("contract_id", sa.Uuid(), sa.ForeignKey("contracts.id")), sa.Column("base_date", sa.Date(), nullable=False),
        sa.Column("note", sa.Text()), sa.Column("source_id", sa.Uuid(), sa.ForeignKey("value_sources.id"), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False), sa.Column("valid_to", sa.Date()),
        sa.Column("superseded_by", sa.Uuid(), sa.ForeignKey("scenarios.id")), sa.Column("replace_reason", sa.Text()))
    op.create_index("ix_scenarios_company_id", "scenarios", ["company_id"])
    op.create_index("uq_scenario_current", "scenarios", ["company_id", "object_id", "name"], unique=True, postgresql_where=sa.text("valid_to IS NULL"), sqlite_where=sa.text("valid_to IS NULL"))
    op.create_table("scenario_params",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("scenario_id", sa.Uuid(), sa.ForeignKey("scenarios.id"), nullable=False), sa.Column("param_type", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False, server_default="all"), sa.Column("scope_value", sa.Text()),
        sa.Column("param_value", sa.Numeric(18, 6), nullable=False), sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("param_type IN ('cost_multiplier','price_reduction','schedule_shift_days','winter_surcharge_pct','financial_share_override')", name="ck_scenario_param_type"),
        sa.CheckConstraint("scope IN ('all','category','cost_item')", name="ck_scenario_param_scope"),
        sa.CheckConstraint("scope <> 'all' OR scope_value IS NULL", name="ck_scenario_scope_all"),
        sa.CheckConstraint("scope = 'all' OR scope_value IS NOT NULL", name="ck_scenario_scope_specific"),
        sa.CheckConstraint("param_value > 0", name="ck_scenario_param_positive"))
    op.create_index("ix_scenario_params_company_id", "scenario_params", ["company_id"])

def upgrade() -> None:
    _upgrade_versioned_existing()
    _create_cost_tables()
    _create_scenario_tables()
    if op.get_bind().dialect.name == "postgresql":
        for table in ("cost_entries", "scenarios", "scenario_params", "cost_articles"):
            op.execute(f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION construction_os_guard_immutable();")

def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in ("cost_entries", "scenarios", "scenario_params", "cost_articles"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.drop_table("scenario_params"); op.drop_table("scenarios"); op.drop_table("cost_entries"); op.drop_table("cost_articles")
    op.drop_index("uq_schedule_task_current", table_name="schedule_tasks"); op.drop_index("uq_object_current", table_name="objects"); op.drop_index("uq_contract_current", table_name="contracts")
    naming = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
    for table in ("schedule_tasks", "objects", "contracts"):
        with op.batch_alter_table(table, recreate="always" if bind.dialect.name == "sqlite" else "auto", naming_convention=naming) as batch:
            batch.drop_constraint(f"fk_{table}_superseded_by", type_="foreignkey")
            for column in ("replace_reason", "superseded_by", "valid_to", "valid_from"):
                batch.drop_column(column)
            if table == "contracts":
                batch.drop_column("award_reduction_factor"); batch.drop_column("signed_on")
            if table == "objects":
                batch.create_unique_constraint("uq_objects_company_id", ["company_id", "name"])
