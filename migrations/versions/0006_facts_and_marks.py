from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_facts_and_marks"
down_revision = "0005_cash_flows"
branch_labels = None
depends_on = None


def _version_columns(table):
    return [
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date()),
        sa.Column("superseded_by", sa.Uuid(), sa.ForeignKey(f"{table}.id")),
        sa.Column("replace_reason", sa.Text()),
    ]


def upgrade():
    with op.batch_alter_table("contracts", recreate="auto") as batch:
        batch.add_column(sa.Column("object_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key("fk_contracts_object_id", "objects", ["object_id"], ["id"])
    op.create_table(
        "fact_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("object_id", sa.Uuid(), sa.ForeignKey("objects.id"), nullable=False),
        sa.Column("work_item_id", sa.Uuid(), sa.ForeignKey("work_items.id"), nullable=False),
        sa.Column("fact_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("recorded_by", sa.Text()),
        sa.Column("note", sa.Text()),
        *_version_columns("fact_entries"),
        sa.CheckConstraint("quantity > 0", name="ck_fact_quantity_positive"),
    )
    for field in ("company_id", "object_id", "work_item_id"):
        op.create_index(f"ix_fact_entries_{field}", "fact_entries", [field])
    op.create_index(
        "uq_fact_entry_current",
        "fact_entries",
        ["company_id", "work_item_id", "fact_date"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
        sqlite_where=sa.text("valid_to IS NULL"),
    )
    op.create_table(
        "time_marks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("object_id", sa.Uuid(), sa.ForeignKey("objects.id"), nullable=False),
        sa.Column("trip_code", sa.Text(), nullable=False),
        sa.Column("mark_type", sa.Text(), nullable=False),
        sa.Column("marked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("vehicle", sa.Text()),
        sa.Column("idle_reason", sa.Text()),
        sa.Column("note", sa.Text()),
        *_version_columns("time_marks"),
        sa.CheckConstraint(
            "mark_type IN ('arrived','loading_start','loaded','arrived_site','unloaded','departed')",
            name="ck_marks_type_valid",
        ),
    )
    for field in ("company_id", "object_id"):
        op.create_index(f"ix_time_marks_{field}", "time_marks", [field])
    op.create_index(
        "uq_time_mark_current",
        "time_marks",
        ["company_id", "trip_code", "mark_type"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
        sqlite_where=sa.text("valid_to IS NULL"),
    )
    if op.get_bind().dialect.name == "postgresql":
        for table in ("fact_entries", "time_marks"):
            op.execute(
                f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION construction_os_guard_immutable();"
            )


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        for table in ("fact_entries", "time_marks"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.drop_table("time_marks")
    op.drop_table("fact_entries")
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("contracts", recreate="always") as batch:
            batch.drop_constraint("fk_contracts_object_id", type_="foreignkey")
            batch.drop_column("object_id")
    else:
        op.drop_constraint("fk_contracts_object_id", "contracts", type_="foreignkey")
        op.drop_column("contracts", "object_id")
