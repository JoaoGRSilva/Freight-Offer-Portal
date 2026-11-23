import sqlite3
from analytics.config import DATABASES
from contextlib import contextmanager
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


@contextmanager
def connect(db_name):
    """Abre a conexão, faz commit/rollback e SEMPRE fecha ao final."""

    if db_name not in DATABASES:
        raise ValueError(f"Banco de dados inválido: {db_name}")

    DATABASES[db_name].parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DATABASES[db_name])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
