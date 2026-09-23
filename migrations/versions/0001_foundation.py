from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def _tenant_id():
    return sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("inn", sa.Text()),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "reference_rates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("rate_type", sa.Text(), nullable=False),
        sa.Column("value", sa.Numeric(12, 6), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date()),
        sa.Column("document_number", sa.Text()),
        sa.Column("document_date", sa.Date()),
        sa.UniqueConstraint("rate_type", "valid_from"),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _tenant_id(),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("stored_path", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.UniqueConstraint("company_id", "sha256"),
    )
    op.create_index("ix_documents_company_id", "documents", ["company_id"])
    op.create_table(
        "value_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _tenant_id(),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id")),
        sa.Column("sheet", sa.Text()),
        sa.Column("cell_or_range", sa.Text()),
        sa.Column("row_no", sa.Integer()),
        sa.Column("confidence", sa.Text(), nullable=False),
        sa.Column("note", sa.Text()),
    )
    op.create_index("ix_value_sources_company_id", "value_sources", ["company_id"])
    op.create_table(
        "value_refs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _tenant_id(),
        sa.Column("entity_name", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("field_name", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("value_sources.id"), nullable=False),
    )
    op.create_index("ix_value_refs_company_id", "value_refs", ["company_id"])
    op.create_index(
        "ix_value_refs_entity", "value_refs", ["entity_name", "entity_id", "field_name"]
    )
    op.create_table(
        "contracts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _tenant_id(),
        sa.Column("contract_type", sa.Text(), nullable=False),
        sa.Column("number", sa.Text()),
        sa.Column("price_is_final", sa.Boolean(), nullable=False),
        sa.Column("advance_pct", sa.Numeric(9, 4)),
        sa.Column("payment_delay_days", sa.Integer()),
        sa.Column("security_amount", sa.Numeric(18, 2)),
        sa.Column("warranty_retention_pct", sa.Numeric(9, 4)),
        sa.Column("treasury_account", sa.Boolean()),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("vat_rate_id", sa.Uuid(), sa.ForeignKey("reference_rates.id")),
    )
    op.create_index("ix_contracts_company_id", "contracts", ["company_id"])
    op.create_table(
        "objects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _tenant_id(),
        sa.Column("contract_id", sa.Uuid(), sa.ForeignKey("contracts.id")),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("object_type", sa.Text()),
        sa.Column("location_text", sa.Text()),
        sa.UniqueConstraint("company_id", "name"),
    )
    op.create_index("ix_objects_company_id", "objects", ["company_id"])
    op.create_table(
        "work_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _tenant_id(),
        sa.Column("object_id", sa.Uuid(), sa.ForeignKey("objects.id"), nullable=False),
        sa.Column("contract_id", sa.Uuid(), sa.ForeignKey("contracts.id")),
        sa.Column("position_no", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("price_gross", sa.Numeric(18, 4), nullable=False),
        sa.Column("amount_gross", sa.Numeric(18, 2), nullable=False),
        sa.Column("vat_rate", sa.Numeric(9, 6), nullable=False),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id")),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("value_sources.id"), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date()),
        sa.Column("superseded_by", sa.Uuid(), sa.ForeignKey("work_items.id")),
        sa.Column("replace_reason", sa.Text()),
    )
    op.create_index("ix_work_items_company_id", "work_items", ["company_id"])
    op.create_index(
        "uq_work_item_current",
        "work_items",
        ["company_id", "object_id", "position_no"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
        sqlite_where=sa.text("valid_to IS NULL"),
    )
    op.create_table(
        "schedule_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _tenant_id(),
        sa.Column("object_id", sa.Uuid(), sa.ForeignKey("objects.id"), nullable=False),
        sa.Column("position_no", sa.Integer()),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("front", sa.Text()),
        sa.Column("unit", sa.Text()),
        sa.Column("quantity", sa.Numeric(18, 4)),
        sa.Column("start_on", sa.Date()),
        sa.Column("end_on", sa.Date()),
        sa.Column("days", sa.Integer()),
        sa.Column("crew_size", sa.Numeric(9, 2)),
        sa.Column("amount", sa.Numeric(18, 2)),
        sa.Column("period_volumes", sa.JSON(), nullable=False),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("value_sources.id"), nullable=False),
    )
    op.create_index("ix_schedule_tasks_company_id", "schedule_tasks", ["company_id"])
    op.create_table(
        "schedule_notes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _tenant_id(),
        sa.Column("object_id", sa.Uuid(), sa.ForeignKey("objects.id"), nullable=False),
        sa.Column("note_type", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("parsed", sa.JSON(), nullable=False),
        sa.Column("cell", sa.Text()),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("value_sources.id"), nullable=False),
    )
    op.create_index("ix_schedule_notes_company_id", "schedule_notes", ["company_id"])
    op.create_table(
        "value_confirmations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _tenant_id(),
        sa.Column("entity_name", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("field_name", sa.Text()),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("old_value", sa.Text()),
        sa.Column("new_value", sa.Text()),
        sa.Column("reason", sa.Text()),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_value_confirmations_company_id", "value_confirmations", ["company_id"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION construction_os_guard_immutable() RETURNS trigger AS $$
            BEGIN
                IF current_setting('construction_os.allow_supersede', true) IS DISTINCT FROM 'on' THEN
                    RAISE EXCEPTION '% immutable', TG_TABLE_NAME;
                END IF;
                IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        for table in ("contracts", "reference_rates", "objects", "work_items", "schedule_tasks"):
            op.execute(
                f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION construction_os_guard_immutable();"
            )
        op.execute(
            """
            CREATE OR REPLACE FUNCTION construction_os_guard_append_only() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION '% append-only', TG_TABLE_NAME;
            END;
            $$ LANGUAGE plpgsql;
            CREATE TRIGGER trg_value_confirmations_append_only
            BEFORE UPDATE OR DELETE ON value_confirmations
            FOR EACH ROW EXECUTE FUNCTION construction_os_guard_append_only();
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS construction_os_guard_append_only() CASCADE")
        op.execute("DROP FUNCTION IF EXISTS construction_os_guard_immutable() CASCADE")
    for table in (
        "value_confirmations",
        "schedule_notes",
        "schedule_tasks",
        "work_items",
        "objects",
        "contracts",
        "value_refs",
        "value_sources",
        "documents",
        "reference_rates",
        "companies",
    ):
        op.drop_table(table)
