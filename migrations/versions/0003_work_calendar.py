from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from construction_os.references.calendar_seed import iter_calendar_days

revision = "0003_work_calendar"
down_revision = "0002_versioned_values"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "work_calendar",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("cal_date", sa.Date(), nullable=False, unique=True),
        sa.Column("is_working", sa.Boolean(), nullable=False),
        sa.Column("day_type", sa.Text(), nullable=False),
        sa.Column("is_shortened", sa.Boolean(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "day_type IN ('working','weekend','holiday','transferred_day_off','transferred_working')",
            name="ck_work_calendar_day_type",
        ),
        sa.CheckConstraint(
            "NOT is_shortened OR is_working", name="ck_work_calendar_shortened_working"
        ),
    )
    rows = [*iter_calendar_days(2026), *iter_calendar_days(2027)]
    table = sa.table(
        "work_calendar",
        sa.column("id", sa.Uuid()),
        sa.column("cal_date", sa.Date()),
        sa.column("is_working", sa.Boolean()),
        sa.column("day_type", sa.Text()),
        sa.column("is_shortened", sa.Boolean()),
        sa.column("source", sa.Text()),
    )
    op.bulk_insert(table, rows)
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE TRIGGER trg_work_calendar_immutable BEFORE UPDATE OR DELETE "
            "ON work_calendar FOR EACH ROW EXECUTE FUNCTION construction_os_guard_append_only();"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_work_calendar_immutable ON work_calendar")
    op.drop_table("work_calendar")
