from __future__ import annotations

from alembic import op

revision = "0003_versioned_immutability"
down_revision = "0002_versioned_values"
branch_labels = None
depends_on = None

TABLES = ("contracts", "objects", "schedule_tasks")


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in TABLES:
            op.execute(
                f"CREATE TRIGGER trg_{table}_immutable "
                f"BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW "
                "EXECUTE FUNCTION construction_os_guard_immutable();"
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
