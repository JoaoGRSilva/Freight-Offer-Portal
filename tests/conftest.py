import pytest


@pytest.fixture
def isolated_databases(tmp_path, monkeypatch):
    """Redireciona os bancos do projeto para arquivos temporários do teste."""
    from services import db

    monkeypatch.setitem(db.DATABASES, "fretes", tmp_path / "fretes_test.db")
    monkeypatch.setitem(db.DATABASES, "users", tmp_path / "users_test.db")
    monkeypatch.setitem(db.DATABASES, "settings", tmp_path / "settings_test.db")

    return db.DATABASES
