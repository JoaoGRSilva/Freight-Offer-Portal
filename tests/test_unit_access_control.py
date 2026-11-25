def test_non_admin_cannot_clear_freights(app_client, monkeypatch):
    from services.db import connect
    from werkzeug.security import generate_password_hash
    import routes.new_shipment as new_shipment

    app, client = app_client

    # Cria um usuário interno que não é administrador.
    with connect("users") as conn:
        cursor = conn.execute(
            """
            INSERT INTO users (
                name,
                email,
                password_hash,
                role,
                active,
                is_admin
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "Operador de teste",
                "operador_teste@teste.com",
                generate_password_hash("senha-teste"),
                "internal",
                1,
                0,
            ),
        )

        user_id = cursor.lastrowid

    # Simula a função de limpeza sem apagar dados.
    limpeza_executada = False

    def fake_delete_base():
        nonlocal limpeza_executada
        limpeza_executada = True

    monkeypatch.setattr(
        new_shipment,
        "delete_base",
        fake_delete_base,
    )

    # Simula a sessão de um usuário autenticado.
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True
        sess["_csrf_token"] = "token-de-teste"

    # Tenta executar a limpeza.
    response = client.post(
        "/nova-carga/limpar",
        headers={"X-CSRF-Token": "token-de-teste"},
    )

    # Verifica se o acesso foi bloqueado.
    assert response.status_code == 403

    # Verifica se a limpeza não foi executada.
    assert limpeza_executada is False

def test_admin_can_clear_freights(app_client, monkeypatch):
    from services.db import connect
    from werkzeug.security import generate_password_hash
    import routes.new_shipment as new_shipment

    app, client = app_client

    # Cria um usuário interno administrador.
    with connect("users") as conn:
        cursor = conn.execute(
            """
            INSERT INTO users (
                name,
                email,
                password_hash,
                role,
                active,
                is_admin
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "Administrador de teste",
                "admin_teste@teste.com",
                generate_password_hash("senha-teste"),
                "internal",
                1,
                1,
            ),
        )

        user_id = cursor.lastrowid

    # Simula a limpeza sem apagar dados reais.
    limpeza_executada = False

    def fake_delete_base():
        nonlocal limpeza_executada
        limpeza_executada = True

    monkeypatch.setattr(
        new_shipment,
        "delete_base",
        fake_delete_base,
    )

    # Simula a sessão autenticada do administrador.
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True
        sess["_csrf_token"] = "token-de-teste"

    response = client.post(
        "/nova-carga/limpar",
        headers={"X-CSRF-Token": "token-de-teste"},
    )

    # O administrador deve conseguir executar a operação.
    assert response.status_code == 302
    assert limpeza_executada is True

from services.user_repository import User


def test_admin_can_access_any_plant():
    user = User({
        "id": 1,
        "name": "Administrador",
        "email": "admin@test.com",
        "role": "internal",
        "carrier_name": None,
        "active": 1,
        "is_admin": 1,
    })

    assert user.can_access_plant("SP01") is True
    assert user.can_access_plant("RJ01") is True


def test_operator_can_access_assigned_plant():
    user = User({
        "id": 2,
        "name": "Operador",
        "email": "operator@test.com",
        "role": "internal",
        "carrier_name": None,
        "active": 1,
        "is_admin": 0,
    }, plants=["SP01"])

    assert user.can_access_plant("SP01") is True
    assert user.can_access_plant("RJ01") is False


def test_carrier_cannot_access_plant():
    user = User({
        "id": 3,
        "name": "Transportadora",
        "email": "carrier@test.com",
        "role": "carrier",
        "carrier_name": "Transportadora X",
        "active": 1,
        "is_admin": 0,
    }, plants=["SP01"])

    assert user.can_access_plant("SP01") is False