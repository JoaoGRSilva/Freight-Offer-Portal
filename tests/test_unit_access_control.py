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

def test_user_cannot_access_nonexistent_freight(app_client, monkeypatch):
    from services.db import connect
    from werkzeug.security import generate_password_hash
    import services.access_control as access_control

    app, client = app_client

    # Cria um usuário interno autenticado.
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
                "operador_frete@teste.com",
                generate_password_hash("senha-teste"),
                "internal",
                1,
                0,
            ),
        )

        user_id = cursor.lastrowid

    # Simula um frete que não existe.
    monkeypatch.setattr(
        access_control,
        "obter_frete",
        lambda freight_id: None,
    )

    # Simula a sessão autenticada.
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True
        sess["_csrf_token"] = "token-de-teste"

    # Tenta acessar o frete inexistente.
    response = client.patch(
        "/api/fretes/999/status",
        json={"status": "em_preparacao"},
        headers={"X-CSRF-Token": "token-de-teste"},
    )

    assert response.status_code == 404

def test_operator_cannot_access_freight_from_other_plant(app_client, monkeypatch):
    from services.db import connect
    from werkzeug.security import generate_password_hash
    import services.access_control as access_control

    app, client = app_client

    # Cria um operador sem vínculo com a planta SP01.
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
                "Operador sem acesso",
                "operador_sem_acesso@teste.com",
                generate_password_hash("senha-teste"),
                "internal",
                1,
                0,
            ),
        )

        user_id = cursor.lastrowid

    # Simula um frete existente da planta SP01.
    monkeypatch.setattr(
        access_control,
        "obter_frete",
        lambda freight_id: {
            "id": freight_id,
            "detalhes": {
                "planta": {
                    "codigo": "SP01"
                }
            }
        },
    )

    # Simula a sessão autenticada.
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True
        sess["_csrf_token"] = "token-de-teste"

    response = client.patch(
        "/api/fretes/999/status",
        json={"status": "em_preparacao"},
        headers={"X-CSRF-Token": "token-de-teste"},
    )

    assert response.status_code == 403


def test_operator_can_access_freight_from_assigned_plant(app_client, monkeypatch):
    from services.db import connect
    from werkzeug.security import generate_password_hash
    import services.access_control as access_control
    import routes.freight_board as freight_board

    app, client = app_client

    # Cria o operador.
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
                "Operador autorizado",
                "operador_autorizado@teste.com",
                generate_password_hash("senha-teste"),
                "internal",
                1,
                0,
            ),
        )

        user_id = cursor.lastrowid

        # Vincula o operador à planta SP01.
        conn.execute(
            """
            INSERT INTO user_plants (user_id, plant_code)
            VALUES (?, ?)
            """,
            (user_id, "SP01"),
        )

    # Simula um frete da planta autorizada.
    monkeypatch.setattr(
        access_control,
        "obter_frete",
        lambda freight_id: {
            "id": freight_id,
            "detalhes": {
                "planta": {
                    "codigo": "SP01"
                }
            }
        },
    )

    # Impede a execução das operações internas da tela.
    monkeypatch.setattr(
        freight_board,
        "get_freight_view_data",
        lambda freight_id: None,
    )

    # Simula a sessão autenticada.
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True
        sess["_csrf_token"] = "token-de-teste"

    response = client.get("/fretes/999")

    # A autorização foi permitida; a rota retornou seu próprio 404.
    assert response.status_code == 404

def test_operator_can_update_status_of_assigned_freight(app_client, monkeypatch):
    from services.db import connect
    from werkzeug.security import generate_password_hash
    import services.access_control as access_control
    import routes.freight_board as freight_board

    app, client = app_client

    # Cria um operador.
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
                "Operador autorizado",
                "operador_status@teste.com",
                generate_password_hash("senha-teste"),
                "internal",
                1,
                0,
            ),
        )

        user_id = cursor.lastrowid

        # Autoriza o operador na planta SP01.
        conn.execute(
            """
            INSERT INTO user_plants (user_id, plant_code)
            VALUES (?, ?)
            """,
            (user_id, "SP01"),
        )

    # Simula um frete pertencente à planta autorizada.
    monkeypatch.setattr(
        access_control,
        "obter_frete",
        lambda freight_id: {
            "id": freight_id,
            "detalhes": {
                "planta": {
                    "codigo": "SP01"
                }
            }
        },
    )

    # Registra se a função de atualização foi realmente chamada.
    chamadas = []

    def atualizar_status_fake(frete_id, novo_status):
        chamadas.append((frete_id, novo_status))
        return True

    monkeypatch.setattr(
        freight_board,
        "atualizar_status",
        atualizar_status_fake,
    )

    # Simula a sessão autenticada.
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True
        sess["_csrf_token"] = "token-de-teste"

    response = client.patch(
        "/api/fretes/999/status",
        json={"status": "em_preparacao"},
        headers={"X-CSRF-Token": "token-de-teste"},
    )

    assert response.status_code == 200
    assert chamadas == [(999, "em_preparacao")]

def test_operator_cannot_update_status_of_other_plant(
    app_client, monkeypatch
):
    from services.db import connect
    from werkzeug.security import generate_password_hash
    import services.access_control as access_control
    import routes.freight_board as freight_board

    app, client = app_client

    # Cria um operador sem vínculo com a planta SP01.
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
                "Operador sem acesso",
                "operador_sem_acesso@teste.com",
                generate_password_hash("senha-teste"),
                "internal",
                1,
                0,
            ),
        )

        user_id = cursor.lastrowid

    # Simula um frete da planta SP01.
    monkeypatch.setattr(
        access_control,
        "obter_frete",
        lambda freight_id: {
            "id": freight_id,
            "detalhes": {
                "planta": {
                    "codigo": "SP01"
                }
            }
        },
    )

    # Identifica se a atualização chegou a ser executada.
    chamadas = []

    def atualizar_status_fake(frete_id, novo_status):
        chamadas.append((frete_id, novo_status))
        return True

    monkeypatch.setattr(
        freight_board,
        "atualizar_status",
        atualizar_status_fake,
    )

    # Simula a sessão autenticada.
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True
        sess["_csrf_token"] = "token-de-teste"

    response = client.patch(
        "/api/fretes/999/status",
        json={"status": "em_preparacao"},
        headers={"X-CSRF-Token": "token-de-teste"},
    )

    assert response.status_code == 403
    assert chamadas == []



def test_operator_cannot_start_negotiation_from_other_plant(
    app_client, monkeypatch
):
    from services.db import connect
    from werkzeug.security import generate_password_hash
    import services.access_control as access_control
    import routes.freight_board as freight_board

    app, client = app_client

    # Cria um operador sem acesso à planta SP01.
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
                "Operador sem acesso",
                "operador_negociacao@teste.com",
                generate_password_hash("senha-teste"),
                "internal",
                1,
                0,
            ),
        )

        user_id = cursor.lastrowid

    # Simula um frete pertencente à planta SP01.
    monkeypatch.setattr(
        access_control,
        "obter_frete",
        lambda freight_id: {
            "id": freight_id,
            "detalhes": {
                "planta": {
                    "codigo": "SP01"
                }
            }
        },
    )

    # Identifica se a negociação chegou a ser executada.
    chamadas = []

    def iniciar_negociacao_fake(frete_id, transportadora):
        chamadas.append((frete_id, transportadora))

    monkeypatch.setattr(
        freight_board,
        "iniciar_negociacao",
        iniciar_negociacao_fake,
    )

    # Simula a sessão autenticada.
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True
        sess["_csrf_token"] = "token-de-teste"

    response = client.post(
        "/api/nova-carga/fretes/999/negociacao",
        json={"transportadora": "Transportadora Teste"},
        headers={"X-CSRF-Token": "token-de-teste"},
    )

    assert response.status_code == 403
    assert chamadas == []



def test_operator_can_start_negotiation_from_assigned_plant(
    app_client, monkeypatch
):
    from services.db import connect
    from werkzeug.security import generate_password_hash
    import services.access_control as access_control
    import routes.freight_board as freight_board

    app, client = app_client

    # Cria um operador.
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
                "Operador autorizado",
                "operador_negociacao_ok@teste.com",
                generate_password_hash("senha-teste"),
                "internal",
                1,
                0,
            ),
        )

        user_id = cursor.lastrowid

        # Autoriza o operador na planta SP01.
        conn.execute(
            """
            INSERT INTO user_plants (user_id, plant_code)
            VALUES (?, ?)
            """,
            (user_id, "SP01"),
        )

    # Simula um frete da planta autorizada.
    monkeypatch.setattr(
        access_control,
        "obter_frete",
        lambda freight_id: {
            "id": freight_id,
            "detalhes": {
                "planta": {
                    "codigo": "SP01"
                }
            }
        },
    )

    # Registra a chamada à função de negociação.
    chamadas = []

    def iniciar_negociacao_fake(frete_id, transportadora):
        chamadas.append((frete_id, transportadora))

    monkeypatch.setattr(
        freight_board,
        "iniciar_negociacao",
        iniciar_negociacao_fake,
    )

    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True
        sess["_csrf_token"] = "token-de-teste"

    response = client.post(
        "/api/nova-carga/fretes/999/negociacao",
        json={"transportadora": "Transportadora Teste"},
        headers={"X-CSRF-Token": "token-de-teste"},
    )

    assert response.status_code == 200
    assert response.get_json()["sucesso"] is True
    assert chamadas == [(999, "Transportadora Teste")]
