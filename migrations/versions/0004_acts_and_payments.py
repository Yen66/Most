from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_acts_and_payments"
down_revision = "0003_work_calendar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("contracts") as batch:
        batch.add_column(sa.Column("penalty_cap_pct", sa.Numeric(9, 6)))
    op.create_table(
        "acceptance_acts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("contract_id", sa.Uuid(), sa.ForeignKey("contracts.id"), nullable=False),
        sa.Column("object_id", sa.Uuid(), sa.ForeignKey("objects.id")),
        sa.Column("act_number", sa.Text(), nullable=False),
        sa.Column("period_from", sa.Date()),
        sa.Column("period_to", sa.Date()),
        sa.Column("amount_gross", sa.Numeric(18, 2), nullable=False),
        sa.Column("vat_rate_id", sa.Uuid(), sa.ForeignKey("reference_rates.id")),
        sa.Column("via_eis", sa.Boolean()),
        sa.Column("placed_on", sa.Date()),
        sa.Column("signed_on", sa.Date()),
        sa.Column("refusal_on", sa.Date()),
        sa.Column("refusal_reason", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date()),
        sa.Column("superseded_by", sa.Uuid(), sa.ForeignKey("acceptance_acts.id")),
        sa.Column("replace_reason", sa.Text()),
        sa.CheckConstraint("amount_gross > 0", name="ck_acts_amount_positive"),
        sa.CheckConstraint(
            "status IN ('placed','signed','refused')", name="ck_acts_status"
        ),
        sa.CheckConstraint(
            "status <> 'placed' OR placed_on IS NOT NULL",
            name="ck_acts_status_requires_placed_on",
        ),
        sa.CheckConstraint(
            "status <> 'signed' OR (signed_on IS NOT NULL AND placed_on IS NOT NULL)",
            name="ck_acts_status_requires_signed_on",
        ),
        sa.CheckConstraint(
            "status <> 'refused' OR (refusal_on IS NOT NULL AND refusal_reason IS NOT NULL)",
            name="ck_acts_status_requires_refusal",
        ),
        sa.CheckConstraint(
            "NOT (signed_on IS NOT NULL AND refusal_on IS NOT NULL)",
            name="ck_acts_not_signed_and_refused",
        ),
        sa.CheckConstraint(
            "signed_on IS NULL OR placed_on IS NULL OR signed_on >= placed_on",
            name="ck_acts_signed_after_placed",
        ),
        sa.CheckConstraint(
            "refusal_on IS NULL OR placed_on IS NULL OR refusal_on >= placed_on",
            name="ck_acts_refusal_after_placed",
        ),
    )
    op.create_index("ix_acceptance_acts_company_id", "acceptance_acts", ["company_id"])
    op.create_index("ix_acceptance_acts_contract_id", "acceptance_acts", ["contract_id"])
    op.create_index(
        "uq_acceptance_act_current",
        "acceptance_acts",
        ["company_id", "contract_id", "act_number"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
        sqlite_where=sa.text("valid_to IS NULL"),
    )
    op.create_table(
        "payment_obligations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Uuid(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("act_id", sa.Uuid(), sa.ForeignKey("acceptance_acts.id"), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("term_workdays", sa.Integer(), nullable=False),
        sa.Column("term_basis", sa.Text(), nullable=False),
        sa.Column("paid_on", sa.Date()),
        sa.Column("paid_amount", sa.Numeric(18, 2)),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date()),
        sa.Column("superseded_by", sa.Uuid(), sa.ForeignKey("payment_obligations.id")),
        sa.Column("replace_reason", sa.Text()),
        sa.CheckConstraint("amount > 0", name="ck_pay_obl_amount_positive"),
        sa.CheckConstraint("term_workdays > 0", name="ck_pay_obl_term_positive"),
        sa.CheckConstraint(
            "term_basis IN ('law_eis_7','law_treasury_10','law_non_eis_10','contract')",
            name="ck_pay_obl_term_basis",
        ),
        sa.CheckConstraint(
            "(paid_on IS NULL AND paid_amount IS NULL) OR "
            "(paid_on IS NOT NULL AND paid_amount IS NOT NULL)",
            name="ck_pay_obl_paid_pair",
        ),
        sa.CheckConstraint(
            "paid_amount IS NULL OR (paid_amount > 0 AND paid_amount <= amount)",
            name="ck_pay_obl_paid_range",
        ),
    )
    op.create_index("ix_payment_obligations_company_id", "payment_obligations", ["company_id"])
    op.create_index("ix_payment_obligations_act_id", "payment_obligations", ["act_id"])
    op.create_index(
        "uq_payment_obligation_current",
        "payment_obligations",
        ["company_id", "act_id"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
        sqlite_where=sa.text("valid_to IS NULL"),
    )
    if op.get_bind().dialect.name == "postgresql":
        for table in ("acceptance_acts", "payment_obligations"):
            op.execute(
                f"CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON "
                f"{table} FOR EACH ROW EXECUTE FUNCTION construction_os_guard_immutable();"
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in ("payment_obligations", "acceptance_acts"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    op.drop_table("payment_obligations")
    op.drop_table("acceptance_acts")
    with op.batch_alter_table("contracts") as batch:
        batch.drop_column("penalty_cap_pct")
