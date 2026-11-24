def test_database_connection_commits_and_closes(isolated_databases):
    from services.db import connect

    with connect("fretes") as conn:
        conn.execute(
            "CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO sample (value) VALUES (?)", ("persistido",))

    with connect("fretes") as conn:
        row = conn.execute("SELECT value FROM sample WHERE id = 1").fetchone()

    assert row["value"] == "persistido"


def test_database_connection_rolls_back_on_error(isolated_databases):
    from services.db import connect

    with connect("fretes") as conn:
        conn.execute(
            "CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )

    try:
        with connect("fretes") as conn:
            conn.execute("INSERT INTO sample (value) VALUES (?)", ("nao salvar",))
            raise RuntimeError("forçar rollback")
    except RuntimeError:
        pass

    with connect("fretes") as conn:
        count = conn.execute("SELECT COUNT(*) AS total FROM sample").fetchone()["total"]

    assert count == 0


def test_unknown_database_name_is_rejected(isolated_databases):
    from services.db import connect

    try:
        with connect("nao_existe"):
            pass
    except ValueError as exc:
        assert "Banco de dados inválido" in str(exc)
    else:
        raise AssertionError("Era esperado ValueError para banco desconhecido")
