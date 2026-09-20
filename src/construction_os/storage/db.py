from __future__ import annotations
import os
from sqlalchemy import create_engine

def make_engine(url: str|None=None):
    return create_engine(url or os.environ.get("DATABASE_URL","sqlite+pysqlite:///:memory:"),future=True)
