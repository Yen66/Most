import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from construction_os.storage import Base, make_engine


@pytest.fixture
def sqlite_session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    output = Path(__file__).parent / "fixtures" / "generated"
    subprocess.run(
        [sys.executable, "scripts/make_fixtures.py", "--out", str(output)],
        check=True,
    )
    return output


@pytest.fixture
def db_session():
    url = os.environ.get("DATABASE_URL")
    if not url:
        engine = make_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            yield session
        return
    engine = make_engine(url)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        engine.dispose()
