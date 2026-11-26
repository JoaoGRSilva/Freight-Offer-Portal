
from types import SimpleNamespace
import sqlite3
from werkzeug.exceptions import Forbidden
import pytest

from routes import admin



@pytest.fixture
def admin_client(app_client, monkeypatch):
    app, client = app_client

    import app as app_module

    usuario = SimpleNamespace(
        id=1,
        is_authenticated=True,
        is_active=True,
        is_admin=True,
        role="internal",
        get_id=lambda: "1",
    )

    # Autenticação real do Flask-Login, usando o user_loader da aplicação.
    monkeypatch.setattr(
        app_module,
        "get_user",
        lambda user_id: usuario if str(user_id) == "1" else None,
    )

    # Isola o CSRF global e o CSRF específico das rotas administrativas.
    monkeypatch.setattr(app_module, "csrf_is_valid", lambda: True)
    monkeypatch.setattr(admin, "validate_csrf", lambda: None)

    # Cria uma sessão autenticada pelo Flask-Login.
    with client.session_transaction() as session:
        session["_user_id"] = "1"
        session["_fresh"] = True

    return app, client



@pytest.fixture
def render_capture(monkeypatch):
    calls = []

    def fake_render(template, **context):
        calls.append((template, context))
        return "TEMPLATE_RENDERIZADO"

    monkeypatch.setattr(admin, "render_template", fake_render)

    return calls



def test_protect_rejeita_usuario_nao_autenticado(monkeypatch):
    monkeypatch.setattr(
        admin,
        "current_user",
        SimpleNamespace(
            is_authenticated=False,
            is_admin=True,
        ),
    )

    with pytest.raises(Forbidden):
        admin.protect()


def test_protect_rejeita_usuario_sem_permissao_admin(monkeypatch):
    monkeypatch.setattr(
        admin,
        "current_user",
        SimpleNamespace(
            is_authenticated=True,
            is_admin=False,
        ),
    )

    with pytest.raises(Forbidden):
        admin.protect()



def test_protect_permite_administrador(admin_client):
    _, client = admin_client

    response = client.get("/admin/")

    assert response.status_code == 200
    assert b"TEMPLATE" in response.data or response.status_code == 200


def test_index_renderiza_template(admin_client, render_capture):
    _, client = admin_client

    response = client.get("/admin/")

    assert response.status_code == 200
    assert render_capture[-1][0] == "admin/index.html"


def test_users_get_renderiza_lista_sem_usuario_selecionado(
    admin_client,
    monkeypatch,
    render_capture,
):
    _, client = admin_client

    usuarios = [
        SimpleNamespace(id=1, name="Admin"),
        SimpleNamespace(id=2, name="Usuario"),
    ]

    plantas = [{"code": "1001", "name": "Planta A"}]

    monkeypatch.setattr(admin, "list_users", lambda: usuarios)
    monkeypatch.setattr(admin.plants_repo, "list_plants", lambda: plantas)

    response = client.get("/admin/users")

    assert response.status_code == 200

    template, context = render_capture[-1]

    assert template == "admin/users.html"
    assert context["users"] == usuarios
    assert context["selected"] is None
    assert context["plants"] == plantas


def test_users_get_seleciona_usuario_por_id(
    admin_client,
    monkeypatch,
    render_capture,
):
    _, client = admin_client

    usuarios = [
        SimpleNamespace(id=1, name="Admin"),
        SimpleNamespace(id=2, name="Usuario"),
    ]

    monkeypatch.setattr(admin, "list_users", lambda: usuarios)
    monkeypatch.setattr(admin.plants_repo, "list_plants", lambda: [])

    response = client.get("/admin/users?edit=2")

    assert response.status_code == 200

    context = render_capture[-1][1]

    assert context["selected"] == usuarios[1]


def test_users_get_nao_seleciona_id_inexistente(
    admin_client,
    monkeypatch,
    render_capture,
):
    _, client = admin_client

    monkeypatch.setattr(admin, "list_users", lambda: [])
    monkeypatch.setattr(admin.plants_repo, "list_plants", lambda: [])

    response = client.get("/admin/users?edit=999")

    assert response.status_code == 200
    assert render_capture[-1][1]["selected"] is None


def test_users_post_salva_usuario_com_sucesso(
    admin_client,
    monkeypatch,
):
    _, client = admin_client

    chamadas = []

    def fake_save_user(*args):
        chamadas.append(args)

    monkeypatch.setattr(admin, "save_user", fake_save_user)

    response = client.post(
        "/admin/users",
        data={
            "name": "Novo Usuario",
            "email": "novo@example.com",
            "password": "senha123",
            "profile": "user",
            "carrier": "Transportadora",
            "plants": ["1001", "1002"],
            "active": "1",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/users")
    assert len(chamadas) == 1

    args = chamadas[0]

    assert args[0] == "Novo Usuario"
    assert args[1] == "novo@example.com"
    assert args[2] == "senha123"
    assert args[3] == "user"
    assert args[4] == "Transportadora"
    assert args[5] == ["1001", "1002"]
    assert args[6] is True
    assert args[7] is None


def test_users_post_converte_user_id_para_inteiro(
    admin_client,
    monkeypatch,
):
    _, client = admin_client

    chamadas = []

    monkeypatch.setattr(
        admin,
        "save_user",
        lambda *args: chamadas.append(args),
    )

    response = client.post(
        "/admin/users",
        data={
            "user_id": "25",
            "name": "Usuario",
            "email": "u@example.com",
            "profile": "user",
        },
    )

    assert response.status_code == 302
    assert chamadas[0][7] == 25


@pytest.mark.parametrize(
    "dados",
    [
        {
            "user_id": "1",
            "profile": "user",
            "active": "1",
        },
        {
            "user_id": "1",
            "profile": "admin",
            "active": "",
        },
    ],
)
def test_users_post_impede_admin_remover_proprio_acesso(
    admin_client,
    monkeypatch,
    dados,
):
    _, client = admin_client

    chamadas = []

    monkeypatch.setattr(
        admin,
        "save_user",
        lambda *args: chamadas.append(args),
    )

    response = client.post("/admin/users", data=dados)

    assert response.status_code == 302
    assert chamadas == []


def test_users_post_trata_user_id_invalido(
    admin_client,
    monkeypatch,
):
    _, client = admin_client

    chamadas = []

    monkeypatch.setattr(
        admin,
        "save_user",
        lambda *args: chamadas.append(args),
    )

    response = client.post(
        "/admin/users",
        data={"user_id": "abc"},
    )

    assert response.status_code == 302
    assert chamadas == []


def test_users_post_trata_value_error(
    admin_client,
    monkeypatch,
):
    _, client = admin_client

    def fake_save_user(*args):
        raise ValueError("Dados inválidos")

    monkeypatch.setattr(admin, "save_user", fake_save_user)

    response = client.post(
        "/admin/users",
        data={
            "name": "Usuario",
            "email": "invalido",
            "profile": "user",
        },
    )

    assert response.status_code == 302


def test_users_post_trata_email_duplicado(
    admin_client,
    monkeypatch,
):
    _, client = admin_client

    def fake_save_user(*args):
        raise sqlite3.IntegrityError("UNIQUE constraint failed")

    monkeypatch.setattr(admin, "save_user", fake_save_user)

    response = client.post(
        "/admin/users",
        data={
            "name": "Usuario",
            "email": "duplicado@example.com",
            "profile": "user",
        },
    )

    assert response.status_code == 302


def test_plants_page_calcula_resumo(
    admin_client,
    monkeypatch,
    render_capture,
):
    _, client = admin_client

    dados = [
        {
            "validation_status": admin.plants_repo.STATUS_VALIDATED,
            "active": 1,
        },
        {
            "validation_status": admin.plants_repo.STATUS_PENDING,
            "active": 1,
        },
        {
            "validation_status": admin.plants_repo.STATUS_VALIDATED,
            "active": 0,
        },
    ]

    monkeypatch.setattr(
        admin.plants_repo,
        "list_plants",
        lambda: dados,
    )

    response = client.get("/admin/plants")

    assert response.status_code == 200

    template, context = render_capture[-1]

    assert template == "admin/plants.html"
    assert context["summary"] == {
        "total": 3,
        "validated": 2,
        "pending": 1,
        "inactive": 1,
    }
    assert context["plants"] == dados
    assert context["selected"] is None
    assert context["editing"] is False
    assert context["error"] is None
    assert context["ufs"] == admin.plants_repo.UFS
    assert context["statuses"] == admin.plants_repo.VALID_STATUSES


def test_plants_page_com_lista_vazia(
    admin_client,
    monkeypatch,
    render_capture,
):
    _, client = admin_client

    monkeypatch.setattr(admin.plants_repo, "list_plants", lambda: [])

    response = client.get("/admin/plants")

    assert response.status_code == 200

    assert render_capture[-1][1]["summary"] == {
        "total": 0,
        "validated": 0,
        "pending": 0,
        "inactive": 0,
    }


def test_plants_get_edita_planta_existente(
    admin_client,
    monkeypatch,
    render_capture,
):
    _, client = admin_client

    planta = {
        "code": "1001",
        "name": "Planta A",
        "zip_code": "18130-000",
        "city": "Sao Roque",
        "state": "SP",
        "active": 1,
        "validation_status": admin.plants_repo.STATUS_VALIDATED,
        "notes": "",
    }

    monkeypatch.setattr(
        admin.plants_repo,
        "get_plant",
        lambda code: planta if code == "1001" else None,
    )
    monkeypatch.setattr(admin.plants_repo, "list_plants", lambda: [planta])

    response = client.get("/admin/plants?edit=1001")

    assert response.status_code == 200

    context = render_capture[-1][1]

    assert context["selected"] == planta
    assert context["editing"] is True


def test_plants_get_aborta_para_planta_inexistente(
    admin_client,
    monkeypatch,
):
    _, client = admin_client

    monkeypatch.setattr(
        admin.plants_repo,
        "get_plant",
        lambda code: None,
    )

    response = client.get("/admin/plants?edit=9999")

    assert response.status_code == 404


def test_plants_get_novo_cadastro(
    admin_client,
    monkeypatch,
    render_capture,
):
    _, client = admin_client

    monkeypatch.setattr(admin.plants_repo, "list_plants", lambda: [])

    response = client.get("/admin/plants?new=1")

    assert response.status_code == 200

    context = render_capture[-1][1]

    assert context["selected"] == {
        "active": 1,
        "validation_status": admin.plants_repo.STATUS_PENDING,
    }
    assert context["editing"] is False


def test_plants_post_salva_planta(
    admin_client,
    monkeypatch,
):
    _, client = admin_client

    chamadas = []

    def fake_save(*args, **kwargs):
        chamadas.append((args, kwargs))

    monkeypatch.setattr(admin.plants_repo, "save_plant", fake_save)

    response = client.post(
        "/admin/plants",
        data={
            "code": "1001",
            "name": "Planta A",
            "zip_code": "13000-000",
            "city": "Campinas",
            "state": "SP",
            "active": "1",
            "validation_status": admin.plants_repo.STATUS_VALIDATED,
            "notes": "Observação",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/plants")

    args, kwargs = chamadas[0]

    assert args == (
        "1001",
        "Planta A",
        "13000-000",
        "Campinas",
        "SP",
    )
    assert kwargs == {
        "active": True,
        "validation_status": admin.plants_repo.STATUS_VALIDATED,
        "notes": "Observação",
        "allow_update": False,
    }


def test_plants_post_permite_atualizacao(
    admin_client,
    monkeypatch,
):
    _, client = admin_client

    chamadas = []

    monkeypatch.setattr(
        admin.plants_repo,
        "save_plant",
        lambda *args, **kwargs: chamadas.append(kwargs),
    )

    response = client.post(
        "/admin/plants",
        data={
            "editing": "1",
            "code": "1001",
            "name": "Planta Atualizada",
        },
    )

    assert response.status_code == 302
    assert chamadas[0]["allow_update"] is True


def test_plants_post_trata_value_error(
    admin_client,
    monkeypatch,
    render_capture,
):
    _, client = admin_client

    def fake_save(*args, **kwargs):
        raise ValueError("CEP inválido")

    monkeypatch.setattr(admin.plants_repo, "save_plant", fake_save)

    response = client.post(
        "/admin/plants",
        data={
            "editing": "1",
            "code": "1001",
            "name": "Planta A",
            "zip_code": "invalido",
        },
    )

    assert response.status_code == 400
    assert b"TEMPLATE" in response.data

    template, context = render_capture[-1]

    assert template == "admin/plants.html"
    assert context["selected"]["code"] == "1001"
    assert context["selected"]["zip_code"] == "invalido"
    assert context["editing"] is True
    assert context["error"] == "CEP inválido"


def test_plants_post_com_formulario_sem_editing(
    admin_client,
    monkeypatch,
    render_capture,
):
    _, client = admin_client

    monkeypatch.setattr(
        admin.plants_repo,
        "save_plant",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ValueError("Erro")
        ),
    )

    response = client.post(
        "/admin/plants",
        data={"code": "1001"},
    )

    assert response.status_code == 400
    assert render_capture[-1][1]["editing"] is False


@pytest.mark.parametrize(
    ("active", "mensagem_esperada"),
    [
        ("1", "Planta ativada."),
        ("0", "Planta inativada."),
    ],
)
def test_toggle_plant_com_sucesso(
    admin_client,
    monkeypatch,
    active,
    mensagem_esperada,
):
    _, client = admin_client

    chamadas = []

    def fake_toggle(code, status):
        chamadas.append((code, status))
        return True

    monkeypatch.setattr(
        admin.plants_repo,
        "toggle_plant",
        fake_toggle,
    )

    response = client.post(
        "/admin/plants/1001/toggle",
        data={"active": active},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/plants")
    assert chamadas == [("1001", active == "1")]


def test_toggle_plant_nao_encontrada(admin_client, monkeypatch):
    _, client = admin_client

    monkeypatch.setattr(
        admin.plants_repo,
        "toggle_plant",
        lambda code, active: False,
    )

    response = client.post(
        "/admin/plants/9999/toggle",
        data={"active": "1"},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/plants")


def test_toggle_plant_considera_qualquer_valor_diferente_de_1_inativo(
    admin_client,
    monkeypatch,
):
    _, client = admin_client

    chamadas = []

    monkeypatch.setattr(
        admin.plants_repo,
        "toggle_plant",
        lambda code, active: chamadas.append(active) or True,
    )

    response = client.post(
        "/admin/plants/1001/toggle",
        data={"active": "true"},
    )

    assert response.status_code == 302
    assert chamadas == [False]


def test_costs_identifica_rota_ainda_nao_implementada():
    resultado = admin.costs()

    assert resultado is None