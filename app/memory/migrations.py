import os
import sqlite3
from app.memory.database_schema import SCHEMA_SQL


def init_db(db_path: str) -> None:
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()