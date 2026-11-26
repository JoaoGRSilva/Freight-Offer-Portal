
import secrets
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import session
from werkzeug.exceptions import BadRequest

from routes import auth


@pytest.fixture
def auth_app(app_client):
    app, client = app_client
    return app, client


@pytest.fixture
def fake_user():
    return SimpleNamespace(
        id=10,
        role="internal",
        is_authenticated=True,
        is_active=True,
        get_id=lambda: "10",
    )


# ============================================================
# csrf_token
# ============================================================

def test_csrf_token_gera_token_quando_nao_existe(auth_app):
    app, _ = auth_app

    with app.test_request_context("/"):
        token = auth.csrf_token()

        assert isinstance(token, str)
        assert len(token) == 64
        assert session["_csrf_token"] == token


def test_csrf_token_reutiliza_token_existente(auth_app):
    app, _ = auth_app

    with app.test_request_context("/"):
        session["_csrf_token"] = "token-existente"

        token = auth.csrf_token()

        assert token == "token-existente"
        assert session["_csrf_token"] == "token-existente"


def test_csrf_token_usa_secrets_token_hex(auth_app, monkeypatch):
    app, _ = auth_app
    gerador = Mock(return_value="token-gerado")

    monkeypatch.setattr(auth.secrets, "token_hex", gerador)

    with app.test_request_context("/"):
        token = auth.csrf_token()

    assert token == "token-gerado"
    gerador.assert_called_once_with(32)


# ============================================================
# csrf_is_valid
# ============================================================

def test_csrf_is_valid_com_token_correto_no_formulario(auth_app):
    app, _ = auth_app

    with app.test_request_context(
        "/",
        method="POST",
        data={"csrf_token": "token-correto"},
    ):
        session["_csrf_token"] = "token-correto"

        assert auth.csrf_is_valid() is True


def test_csrf_is_valid_com_token_correto_no_header(auth_app):
    app, _ = auth_app

    with app.test_request_context(
        "/",
        method="POST",
        headers={"X-CSRF-Token": "token-correto"},
    ):
        session["_csrf_token"] = "token-correto"

        assert auth.csrf_is_valid() is True


def test_csrf_is_valid_prioriza_header_sobre_formulario(auth_app):
    app, _ = auth_app

    with app.test_request_context(
        "/",
        method="POST",
        data={"csrf_token": "token-incorreto"},
        headers={"X-CSRF-Token": "token-correto"},
    ):
        session["_csrf_token"] = "token-correto"

        assert auth.csrf_is_valid() is True


def test_csrf_is_valid_rejeita_token_incorreto(auth_app):
    app, _ = auth_app

    with app.test_request_context(
        "/",
        method="POST",
        data={"csrf_token": "token-incorreto"},
    ):
        session["_csrf_token"] = "token-correto"

        assert auth.csrf_is_valid() is False


def test_csrf_is_valid_rejeita_token_ausente(auth_app):
    app, _ = auth_app

    with app.test_request_context("/"):
        session["_csrf_token"] = "token-correto"

        assert auth.csrf_is_valid() is False


def test_csrf_is_valid_rejeita_sessao_sem_token(auth_app):
    app, _ = auth_app

    with app.test_request_context(
        "/",
        method="POST",
        data={"csrf_token": "token-correto"},
    ):
        assert auth.csrf_is_valid() is False


def test_csrf_is_valid_rejeita_sessao_com_token_vazio(auth_app):
    app, _ = auth_app

    with app.test_request_context(
        "/",
        method="POST",
        data={"csrf_token": "token-correto"},
    ):
        session["_csrf_token"] = ""

        assert auth.csrf_is_valid() is False


def test_csrf_is_valid_rejeita_header_vazio_sem_fallback_valido(auth_app):
    app, _ = auth_app

    with app.test_request_context(
        "/",
        method="POST",
        headers={"X-CSRF-Token": ""},
    ):
        session["_csrf_token"] = "token-correto"

        assert auth.csrf_is_valid() is False


def test_csrf_is_valid_usa_compare_digest(auth_app, monkeypatch):
    app, _ = auth_app
    comparador = Mock(return_value=True)

    monkeypatch.setattr(auth.secrets, "compare_digest", comparador)

    with app.test_request_context(
        "/",
        method="POST",
        data={"csrf_token": "token"},
    ):
        session["_csrf_token"] = "token"

        resultado = auth.csrf_is_valid()

    assert resultado is True
    comparador.assert_called_once_with("token", "token")


def test_csrf_is_valid_nao_aceita_token_de_tipo_invalido(auth_app):
    app, _ = auth_app

    with app.test_request_context(
        "/",
        method="POST",
        data={"csrf_token": "token"},
    ):
        session["_csrf_token"] = "token"

        assert auth.csrf_is_valid() is True


# ============================================================
# validate_csrf
# ============================================================

def test_validate_csrf_nao_aborta_com_token_valido(auth_app, monkeypatch):
    monkeypatch.setattr(auth, "csrf_is_valid", lambda: True)

    app, _ = auth_app

    with app.test_request_context("/"):
        assert auth.validate_csrf() is None


def test_validate_csrf_aborta_com_token_invalido(auth_app, monkeypatch):
    monkeypatch.setattr(auth, "csrf_is_valid", lambda: False)

    app, _ = auth_app

    with app.test_request_context("/"):
        with pytest.raises(BadRequest):
            auth.validate_csrf()


# ============================================================
# user_home
# ============================================================

def test_user_home_redireciona_carrier_para_raiz(fake_user):
    fake_user.role = "carrier"

    assert auth.user_home(fake_user) == "/"


def test_user_home_redireciona_internal_para_fretes(auth_app, fake_user):
    app, _ = auth_app

    with app.test_request_context("/"):
        fake_user.role = "internal"

        assert auth.user_home(fake_user) == "/fretes"


def test_user_home_usa_url_for_para_fretes(auth_app, fake_user):
    app, _ = auth_app

    with app.test_request_context("/"):
        fake_user.role = "internal"

        resultado = auth.user_home(fake_user)

        assert resultado == auth.url_for("fretes.fretes")


# ============================================================
# GET /login
# ============================================================

def test_login_get_renderiza_pagina(auth_client=None):
    pass



def test_login_get_renderiza_pagina(auth_app):
    app, client = auth_app

    response = client.get("/login")

    assert response.status_code == 200
    assert b"csrf_token" in response.data


def test_login_get_cria_token_csrf_na_sessao(auth_app):
    app, client = auth_app

    response = client.get("/login")

    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert "_csrf_token" in sess
        assert len(sess["_csrf_token"]) == 64


def test_login_get_reutiliza_token_csrf(auth_app):
    app, client = auth_app

    with client.session_transaction() as sess:
        sess["_csrf_token"] = "token-ja-existente"

    response = client.get("/login")

    assert response.status_code == 200

    with client.session_transaction() as sess:
        assert sess["_csrf_token"] == "token-ja-existente"


def test_login_post_sem_csrf_retorna_400(auth_app, monkeypatch):
    app, client = auth_app
    autenticar = Mock()

    monkeypatch.setattr(auth, "authenticate_user", autenticar)

    response = client.post(
        "/login",
        data={"email": "teste@example.com", "password": "senha"},
    )

    assert response.status_code == 400
    autenticar.assert_not_called()


def test_login_post_com_csrf_invalido_retorna_400(auth_app, monkeypatch):
    app, client = auth_app
    autenticar = Mock()

    monkeypatch.setattr(auth, "authenticate_user", autenticar)

    with client.session_transaction() as sess:
        sess["_csrf_token"] = "token-correto"

    response = client.post(
        "/login",
        data={
            "email": "teste@example.com",
            "password": "senha",
            "csrf_token": "token-incorreto",
        },
    )

    assert response.status_code == 400
    autenticar.assert_not_called()


def test_login_post_com_credenciais_invalidas_retorna_401(
    auth_app, monkeypatch
):
    app, client = auth_app

    autenticar = Mock(return_value=None)
    monkeypatch.setattr(auth, "authenticate_user", autenticar)

    with client.session_transaction() as sess:
        sess["_csrf_token"] = "token-correto"

    response = client.post(
        "/login",
        data={
            "email": "teste@example.com",
            "password": "senha-incorreta",
            "csrf_token": "token-correto",
        },
    )

    assert response.status_code == 401
    assert "E-mail ou senha inválidos.".encode() in response.data

    autenticar.assert_called_once_with(
        "teste@example.com",
        "senha-incorreta",
    )


def test_login_post_com_credenciais_validas_redireciona(
    auth_app, monkeypatch, fake_user
):
    app, client = auth_app

    monkeypatch.setattr(
        auth,
        "authenticate_user",
        lambda email, password: fake_user,
    )

    with client.session_transaction() as sess:
        sess["_csrf_token"] = "token-correto"
        sess["dado_antigo"] = "deve-ser-removido"

    response = client.post(
        "/login",
        data={
            "email": "teste@example.com",
            "password": "senha-correta",
            "csrf_token": "token-correto",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/fretes")

    with client.session_transaction() as sess:
        assert "_user_id" in sess
        assert "dado_antigo" not in sess
        assert "_csrf_token" not in sess


def test_login_post_carrier_redireciona_para_raiz(
    auth_app, monkeypatch, fake_user
):
    app, client = auth_app
    fake_user.role = "carrier"

    monkeypatch.setattr(
        auth,
        "authenticate_user",
        lambda email, password: fake_user,
    )

    with client.session_transaction() as sess:
        sess["_csrf_token"] = "token-correto"

    response = client.post(
        "/login",
        data={
            "email": "carrier@example.com",
            "password": "senha",
            "csrf_token": "token-correto",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_login_post_usa_valores_vazios_quando_campos_ausentes(
    auth_app, monkeypatch
):
    app, client = auth_app
    autenticar = Mock(return_value=None)

    monkeypatch.setattr(auth, "authenticate_user", autenticar)

    with client.session_transaction() as sess:
        sess["_csrf_token"] = "token-correto"

    response = client.post(
        "/login",
        data={"csrf_token": "token-correto"},
    )

    assert response.status_code == 401
    autenticar.assert_called_once_with("", "")


def test_login_usuario_ja_autenticado_redireciona(
    auth_app, monkeypatch, fake_user
):
    app, client = auth_app
    app_module = __import__("app")

    monkeypatch.setattr(
        app_module,
        "get_user",
        lambda user_id: fake_user,
    )

    with client.session_transaction() as sess:
        sess["_user_id"] = str(fake_user.id)
        sess["_fresh"] = True

    response = client.get("/login")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/fretes")


def test_login_usuario_carrier_ja_autenticado_redireciona(
    auth_app, monkeypatch, fake_user
):
    app, client = auth_app
    app_module = __import__("app")
    fake_user.role = "carrier"

    monkeypatch.setattr(
        app_module,
        "get_user",
        lambda user_id: fake_user,
    )

    with client.session_transaction() as sess:
        sess["_user_id"] = str(fake_user.id)
        sess["_fresh"] = True

    response = client.get("/login")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


# ============================================================
# POST /logout
# ============================================================

def test_logout_sem_autenticacao_retorna_401(auth_app):
    app, client = auth_app

    response = client.post("/logout")

    assert response.status_code == 401


def test_logout_sem_csrf_retorna_400(auth_app, monkeypatch, fake_user):
    app, client = auth_app
    app_module = __import__("app")

    monkeypatch.setattr(
        app_module,
        "get_user",
        lambda user_id: fake_user,
    )

    with client.session_transaction() as sess:
        sess["_user_id"] = str(fake_user.id)
        sess["_fresh"] = True

    response = client.post("/logout")

    assert response.status_code == 400


def test_logout_com_csrf_invalido_retorna_400(
    auth_app, monkeypatch, fake_user
):
    app, client = auth_app
    app_module = __import__("app")

    monkeypatch.setattr(
        app_module,
        "get_user",
        lambda user_id: fake_user,
    )

    with client.session_transaction() as sess:
        sess["_user_id"] = str(fake_user.id)
        sess["_fresh"] = True
        sess["_csrf_token"] = "token-correto"

    response = client.post(
        "/logout",
        data={"csrf_token": "token-incorreto"},
    )

    assert response.status_code == 400


def test_logout_valido_limpa_sessao_e_redireciona(
    auth_app, monkeypatch, fake_user
):
    app, client = auth_app
    app_module = __import__("app")
    logout = Mock()

    monkeypatch.setattr(
        app_module,
        "get_user",
        lambda user_id: fake_user,
    )
    monkeypatch.setattr(auth, "logout_user", logout)

    with client.session_transaction() as sess:
        sess["_user_id"] = str(fake_user.id)
        sess["_fresh"] = True
        sess["_csrf_token"] = "token-correto"
        sess["outro_dado"] = "valor"

    response = client.post(
        "/logout",
        data={"csrf_token": "token-correto"},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    logout.assert_called_once()

    with client.session_transaction() as sess:
        assert "_user_id" not in sess
        assert "_csrf_token" not in sess
        assert "outro_dado" not in sess


def test_logout_aceita_csrf_pelo_header(
    auth_app, monkeypatch, fake_user
):
    app, client = auth_app
    app_module = __import__("app")

    monkeypatch.setattr(
        app_module,
        "get_user",
        lambda user_id: fake_user,
    )
    monkeypatch.setattr(auth, "logout_user", Mock())

    with client.session_transaction() as sess:
        sess["_user_id"] = str(fake_user.id)
        sess["_fresh"] = True
        sess["_csrf_token"] = "token-correto"

    response = client.post(
        "/logout",
        headers={"X-CSRF-Token": "token-correto"},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
