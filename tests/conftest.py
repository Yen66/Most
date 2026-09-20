import pytest
from sqlalchemy.orm import Session
from construction_os.storage import Base, make_engine
@pytest.fixture
def sqlite_session():
    engine=make_engine("sqlite+pysqlite:///:memory:"); Base.metadata.create_all(engine)
    with Session(engine) as session: yield session
