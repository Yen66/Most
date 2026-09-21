from __future__ import annotations

import os

from sqlalchemy import create_engine


def make_engine(url: str | None = None):
    database_url = url or os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    return create_engine(database_url, future=True)
