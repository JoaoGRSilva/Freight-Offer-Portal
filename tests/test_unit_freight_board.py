
import pytest
from werkzeug.security import generate_password_hash


def autenticar_operador(app_client):
    from services.db import connect

    app, client = app_client

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
                "freight_board_teste@teste.com",
                generate_password_hash("senha-teste"),
                "internal",
                1,
                0,
            ),
        )

        user_id = cursor.lastrowid

        conn.execute(
            """
            INSERT INTO user_plants (user_id, plant_code)
            VALUES (?, ?)
            """,
            (user_id, "SP01"),
        )

    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True
        sess["_csrf_token"] = "token-de-teste"

    return client


def liberar_acesso_ao_frete(monkeypatch):
    import services.access_control as access_control

    monkeypatch.setattr(
        access_control,
        "obter_frete",
        lambda freight_id: {
            "id": freight_id,
            "detalhes": {
                "planta": {
                    "codigo": "SP01"
                }
            },
        },
    )


# ==========================================
# CONTRAPROPOSTA DO OPERADOR
# ==========================================

def test_counterproposal_route_success(app_client, monkeypatch):
    import routes.freight_board as freight_board

    client = autenticar_operador(app_client)
    liberar_acesso_ao_frete(monkeypatch)

    chamadas = []

    def fake_contrapropor(**kwargs):
        chamadas.append(kwargs)

    monkeypatch.setattr(
        freight_board,
        "contrapropor",
        fake_contrapropor,
    )

    response = client.post(
        "/nova-carga/fretes/10/propostas/20/contrapropor",
        data={
            "valor": "1500",
            "prazo_dias": "15",
            "observacoes": "Entrega urgente",
        },
        headers={"X-CSRF-Token": "token-de-teste"},
    )

    assert response.status_code == 200
    assert response.get_json()["sucesso"] is True
    assert chamadas == [{
        "frete_id": 10,
        "proposta_id": 20,
        "valor": "1500",
        "prazo_dias": "15",
        "observacoes": "Entrega urgente",
    }]


def test_counterproposal_route_validation_error(app_client, monkeypatch):
    import routes.freight_board as freight_board

    client = autenticar_operador(app_client)
    liberar_acesso_ao_frete(monkeypatch)

    def fake_contrapropor(**kwargs):
        raise ValueError("Valor inválido.")

    monkeypatch.setattr(
        freight_board,
        "contrapropor",
        fake_contrapropor,
    )

    response = client.post(
        "/nova-carga/fretes/10/propostas/20/contrapropor",
        data={"valor": "abc"},
        headers={"X-CSRF-Token": "token-de-teste"},
    )

    assert response.status_code == 400
    assert response.get_json()["sucesso"] is False
    assert response.get_json()["mensagem"] == "Valor inválido."


def test_counterproposal_route_internal_error(app_client, monkeypatch):
    import routes.freight_board as freight_board

    client = autenticar_operador(app_client)
    liberar_acesso_ao_frete(monkeypatch)

    def fake_contrapropor(**kwargs):
        raise RuntimeError("Erro simulado.")

    monkeypatch.setattr(
        freight_board,
        "contrapropor",
        fake_contrapropor,
    )

    response = client.post(
        "/nova-carga/fretes/10/propostas/20/contrapropor",
        data={"valor": "1500"},
        headers={"X-CSRF-Token": "token-de-teste"},
    )

    assert response.status_code == 500
    assert response.get_json()["sucesso"] is False


# ==========================================
# INICIAR NEGOCIAÇÃO
# ==========================================

def test_start_negotiation_route_success(app_client, monkeypatch):
    import routes.freight_board as freight_board

    client = autenticar_operador(app_client)
    liberar_acesso_ao_frete(monkeypatch)

    chamadas = []

    def fake_iniciar_negociacao(frete_id, transportadora):
        chamadas.append((frete_id, transportadora))

    monkeypatch.setattr(
        freight_board,
        "iniciar_negociacao",
        fake_iniciar_negociacao,
    )

    response = client.post(
        "/api/nova-carga/fretes/10/negociacao",
        json={"transportadora": ["Transportadora Teste"]},
        headers={"X-CSRF-Token": "token-de-teste"},
    )

    assert response.status_code == 200
    assert response.get_json()["sucesso"] is True
    assert chamadas == [
        (10, ["Transportadora Teste"])
    ]


def test_start_negotiation_route_validation_error(app_client, monkeypatch):
    import routes.freight_board as freight_board

    client = autenticar_operador(app_client)
    liberar_acesso_ao_frete(monkeypatch)

    def fake_iniciar_negociacao(frete_id, transportadora):
        raise ValueError("Transportadora inválida.")

    monkeypatch.setattr(
        freight_board,
        "iniciar_negociacao",
        fake_iniciar_negociacao,
    )

    response = client.post(
        "/api/nova-carga/fretes/10/negociacao",
        json={"transportadora": []},
        headers={"X-CSRF-Token": "token-de-teste"},
    )

    assert response.status_code == 400
    assert response.get_json()["sucesso"] is False
    assert response.get_json()["mensagem"] == "Transportadora inválida."


def test_start_negotiation_route_internal_error(app_client, monkeypatch):
    import routes.freight_board as freight_board

    client = autenticar_operador(app_client)
    liberar_acesso_ao_frete(monkeypatch)

    def fake_iniciar_negociacao(frete_id, transportadora):
        raise RuntimeError("Erro simulado.")

    monkeypatch.setattr(
        freight_board,
        "iniciar_negociacao",
        fake_iniciar_negociacao,
    )

    response = client.post(
        "/api/nova-carga/fretes/10/negociacao",
        json={"transportadora": ["Transportadora Teste"]},
        headers={"X-CSRF-Token": "token-de-teste"},
    )

    assert response.status_code == 500
    assert response.get_json()["sucesso"] is False


# ==========================================
# ALTERAÇÃO DE STATUS
# ==========================================

def test_update_status_route_success(app_client, monkeypatch):
    import routes.freight_board as freight_board

    client = autenticar_operador(app_client)
    liberar_acesso_ao_frete(monkeypatch)

    chamadas = []

    def fake_atualizar_status(frete_id, novo_status):
        chamadas.append((frete_id, novo_status))
        return True

    monkeypatch.setattr(
        freight_board,
        "atualizar_status",
        fake_atualizar_status,
    )

    response = client.patch(
        "/api/fretes/10/status",
        json={"status": "em_preparacao"},
        headers={"X-CSRF-Token": "token-de-teste"},
    )

    assert response.status_code == 200
    assert response.get_json()["sucesso"] is True
    assert response.get_json()["frete_id"] == 10
    assert response.get_json()["status"] == "em_preparacao"
    assert chamadas == [(10, "em_preparacao")]


@pytest.mark.parametrize(
    "status",
    ["cotacao_aceita", "concluido"],
)
def test_update_status_route_rejects_protected_status(
    app_client, monkeypatch, status
):
    import routes.freight_board as freight_board

    client = autenticar_operador(app_client)
    liberar_acesso_ao_frete(monkeypatch)

    chamadas = []

    def fake_atualizar_status(frete_id, novo_status):
        chamadas.append((frete_id, novo_status))
        return True

    monkeypatch.setattr(
        freight_board,
        "atualizar_status",
        fake_atualizar_status,
    )

    response = client.patch(
        "/api/fretes/10/status",
        json={"status": status},
        headers={"X-CSRF-Token": "token-de-teste"},
    )

    assert response.status_code == 409
    assert response.get_json()["sucesso"] is False
    assert chamadas == []


def test_update_status_route_validation_error(app_client, monkeypatch):
    import routes.freight_board as freight_board

    client = autenticar_operador(app_client)
    liberar_acesso_ao_frete(monkeypatch)

    def fake_atualizar_status(frete_id, novo_status):
        raise ValueError("Status inválido.")

    monkeypatch.setattr(
        freight_board,
        "atualizar_status",
        fake_atualizar_status,
    )

    response = client.patch(
        "/api/fretes/10/status",
        json={"status": "invalido"},
        headers={"X-CSRF-Token": "token-de-teste"},
    )

    assert response.status_code == 400
    assert response.get_json()["erro"] == "Status inválido."


def test_update_status_route_freight_not_found(app_client, monkeypatch):
    import routes.freight_board as freight_board

    client = autenticar_operador(app_client)
    liberar_acesso_ao_frete(monkeypatch)

    monkeypatch.setattr(
        freight_board,
        "atualizar_status",
        lambda frete_id, novo_status: False,
    )

    response = client.patch(
        "/api/fretes/10/status",
        json={"status": "em_preparacao"},
        headers={"X-CSRF-Token": "token-de-teste"},
    )

    assert response.status_code == 404
    assert response.get_json()["erro"] == "Frete não encontrado"


# ==========================================
# DETALHES DO FRETE
# ==========================================

def test_freight_details_route_not_found(app_client, monkeypatch):
    import routes.freight_board as freight_board

    client = autenticar_operador(app_client)
    liberar_acesso_ao_frete(monkeypatch)

    monkeypatch.setattr(
        freight_board,
        "get_freight_view_data",
        lambda freight_id: None,
    )

    response = client.get("/fretes/10")

    assert response.status_code == 404
