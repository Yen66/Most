from alembic import op
from construction_os.storage.models import Base
revision="0001_foundation"; down_revision=None; branch_labels=None; depends_on=None
def upgrade():
    bind=op.get_bind(); Base.metadata.create_all(bind)
    if bind.dialect.name=="postgresql":
        op.execute("""CREATE OR REPLACE FUNCTION guard_work_items() RETURNS trigger AS $$ BEGIN
        IF TG_OP='DELETE' THEN RAISE EXCEPTION 'work_items immutable'; END IF;
        IF current_setting('construction_os.allow_supersede',true) IS DISTINCT FROM 'on' THEN RAISE EXCEPTION 'work_items immutable'; END IF;
        RETURN NEW; END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_work_items_immutable BEFORE UPDATE OR DELETE ON work_items FOR EACH ROW EXECUTE FUNCTION guard_work_items();
        CREATE OR REPLACE FUNCTION guard_confirmations() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'confirmations append-only'; END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_confirmations_append_only BEFORE UPDATE OR DELETE ON value_confirmations FOR EACH ROW EXECUTE FUNCTION guard_confirmations();""")
def downgrade():
    Base.metadata.drop_all(op.get_bind())
