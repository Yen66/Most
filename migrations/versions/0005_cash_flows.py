from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_cash_flows"
down_revision = "0004_acts_and_payments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cash_flows",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("contract_id", sa.Uuid(), sa.ForeignKey("contracts.id")),
        sa.Column("object_id", sa.Uuid(), sa.ForeignKey("objects.id")),
        sa.Column("flow_date", sa.Date(), nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("plan_or_fact", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.Text()),
        sa.Column("source_id", sa.Uuid()),
        sa.Column("note", sa.Text()),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date()),
        sa.Column("superseded_by", sa.Uuid(), sa.ForeignKey("cash_flows.id")),
        sa.Column("replace_reason", sa.Text()),
        sa.CheckConstraint("direction IN ('inflow','outflow')", name="ck_cash_flow_direction"),
        sa.CheckConstraint("amount > 0", name="ck_cash_flow_amount_positive"),
        sa.CheckConstraint("plan_or_fact IN ('plan','fact')", name="ck_cash_flow_plan_fact"),
        sa.CheckConstraint(
            "(source_kind IS NULL AND source_id IS NULL) OR "
            "(source_kind IS NOT NULL AND source_id IS NOT NULL)",
            name="ck_cash_flow_source_pair",
        ),
    )
    op.create_index("ix_cash_flows_company_id", "cash_flows", ["company_id"])
    op.create_index(
        "uq_cash_flow_source_current",
        "cash_flows",
        ["company_id", "source_kind", "source_id"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL AND source_kind IS NOT NULL"),
        sqlite_where=sa.text("valid_to IS NULL AND source_kind IS NOT NULL"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE TRIGGER trg_cash_flows_immutable BEFORE UPDATE OR DELETE "
            "ON cash_flows FOR EACH ROW "
            "EXECUTE FUNCTION construction_os_guard_immutable();"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_cash_flows_immutable ON cash_flows")
    op.drop_table("cash_flows")
