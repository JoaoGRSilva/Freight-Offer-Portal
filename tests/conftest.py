import pytest


@pytest.fixture
def isolated_databases(tmp_path, monkeypatch):
    """Redireciona os bancos do projeto para arquivos temporários do teste."""
    from services import db

    monkeypatch.setitem(db.DATABASES, "fretes", tmp_path / "fretes_test.db")
    monkeypatch.setitem(db.DATABASES, "users", tmp_path / "users_test.db")
    monkeypatch.setitem(db.DATABASES, "settings", tmp_path / "settings_test.db")

    return db.DATABASES


@pytest.fixture
def app_client(isolated_databases, monkeypatch):
    """Cria um cliente Flask usando bancos temporários."""

    monkeypatch.setenv("FLASK_SECRET_KEY", "chave-segura-para-testes")

    import app as app_module

    # Garante que as tabelas existam nos bancos temporários
    # de cada teste, mesmo que o módulo app já esteja carregado.
    app_module.inicializar_banco()
    app_module.initialize_users()
    app_module.seed_plants_from_config()

    test_app = app_module.app
    test_app.config.update(TESTING=True)

    return test_app, test_app.test_client()