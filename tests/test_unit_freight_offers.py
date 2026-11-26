
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import request

from routes import freight_offers as offers


@pytest.fixture
def offers_app(app_client):
    app, client = app_client
    return app, client


def make_user(
    role="carrier",
    is_admin=False,
    plants=None,
    carrier_name="Transportadora Teste",
    is_authenticated=True,
):
    return SimpleNamespace(
        id=10,
        role=role,
        is_admin=is_admin,
        plants=plants or [],
        carrier_name=carrier_name,
        is_authenticated=is_authenticated,
        is_active=True,
        get_id=lambda: "10",
    )


def call_home(app, monkeypatch, user, shipments=None, weather_result=None):
    shipments = shipments if shipments is not None else []

    monkeypatch.setattr(offers, "current_user", user)
    monkeypatch.setattr(
        offers,
        "listar_fretes_em_oferta",
        Mock(return_value=shipments),
    )
    monkeypatch.setattr(
        offers.weather,
        "get_current_weather",
        Mock(return_value=weather_result),
    )

    rendered = {}

    def fake_render(template, **context):
        rendered["template"] = template
        rendered["context"] = context
        return "pagina-renderizada"

    monkeypatch.setattr(offers, "render_template", fake_render)

    with app.test_request_context("/"):
        result = offers.home()

    return result, rendered



def call_proposal(app, monkeypatch, user, payload):
    monkeypatch.setattr(offers, "current_user", user)

    with app.test_request_context(
        "/api/ofertas/123/propostas",
        method="POST",
        json=payload,
    ):
        return offers.enviar_proposta.__wrapped__(123)



def response_json(result):
    if isinstance(result, tuple):
        response, status = result
    else:
        response = result
        status = response.status_code

    return response.get_json(), status


# ============================================================
# HOME
# ============================================================

def test_home_renderiza_template_e_contexto_padrao(
    offers_app, monkeypatch
):
    app, _ = offers_app

    result, rendered = call_home(
        app,
        monkeypatch,
        make_user(),
    )

    assert result == "pagina-renderizada"
    assert rendered["template"] == "carrier-portal.html"
    assert rendered["context"]["cargas"] == []
    assert rendered["context"]["transportadoras_teste"] == []


def test_home_transportadora_lista_todos_os_fretes(
    offers_app, monkeypatch
):
    app, _ = offers_app
    listar = Mock(return_value=[])

    monkeypatch.setattr(offers, "current_user", make_user())
    monkeypatch.setattr(offers, "listar_fretes_em_oferta", listar)
    monkeypatch.setattr(
        offers.weather,
        "get_current_weather",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        offers,
        "render_template",
        Mock(return_value="ok"),
    )

    with app.test_request_context("/"):
        offers.home()

    listar.assert_called_once_with(None)


def test_home_admin_lista_todos_os_fretes(
    offers_app, monkeypatch
):
    app, _ = offers_app
    listar = Mock(return_value=[])

    user = make_user(role="internal", is_admin=True)

    monkeypatch.setattr(offers, "current_user", user)
    monkeypatch.setattr(offers, "listar_fretes_em_oferta", listar)
    monkeypatch.setattr(
        offers.weather,
        "get_current_weather",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        offers,
        "render_template",
        Mock(return_value="ok"),
    )

    with app.test_request_context("/"):
        offers.home()

    listar.assert_called_once_with(None)


def test_home_usuario_internal_filtra_pelas_plantas(
    offers_app, monkeypatch
):
    app, _ = offers_app
    plantas = ["BR01", "BR02"]
    listar = Mock(return_value=[])

    user = make_user(
        role="internal",
        is_admin=False,
        plants=plantas,
    )

    monkeypatch.setattr(offers, "current_user", user)
    monkeypatch.setattr(offers, "listar_fretes_em_oferta", listar)
    monkeypatch.setattr(
        offers.weather,
        "get_current_weather",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        offers,
        "render_template",
        Mock(return_value="ok"),
    )

    with app.test_request_context("/"):
        offers.home()

    listar.assert_called_once_with(plantas)


def test_home_destino_dict_com_cidade_e_uf(
    offers_app, monkeypatch
):
    app, _ = offers_app
    shipments = [{"destino": {"cidade": "Campinas", "uf": "SP"}}]
    consultar = Mock(return_value={"temperatura": 25})

    monkeypatch.setattr(offers, "current_user", make_user())
    monkeypatch.setattr(
        offers,
        "listar_fretes_em_oferta",
        Mock(return_value=shipments),
    )
    monkeypatch.setattr(
        offers.weather,
        "get_current_weather",
        consultar,
    )
    monkeypatch.setattr(
        offers,
        "render_template",
        Mock(return_value="ok"),
    )

    with app.test_request_context("/"):
        offers.home()

    consultar.assert_called_once_with("Campinas, SP, Brazil")
    assert shipments[0]["clima"] == {"temperatura": 25}


def test_home_destino_dict_sem_uf_consulta_apenas_cidade(
    offers_app, monkeypatch
):
    app, _ = offers_app
    shipments = [{"destino": {"cidade": "Campinas"}}]
    consultar = Mock(return_value={"temperatura": 25})

    monkeypatch.setattr(offers, "current_user", make_user())
    monkeypatch.setattr(
        offers,
        "listar_fretes_em_oferta",
        Mock(return_value=shipments),
    )
    monkeypatch.setattr(
        offers.weather,
        "get_current_weather",
        consultar,
    )
    monkeypatch.setattr(
        offers,
        "render_template",
        Mock(return_value="ok"),
    )

    with app.test_request_context("/"):
        offers.home()

    consultar.assert_called_once_with("Campinas")


def test_home_destino_dict_sem_cidade_nao_consulta_clima(
    offers_app, monkeypatch
):
    app, _ = offers_app
    shipments = [{"destino": {"uf": "SP"}}]
    consultar = Mock()

    monkeypatch.setattr(offers, "current_user", make_user())
    monkeypatch.setattr(
        offers,
        "listar_fretes_em_oferta",
        Mock(return_value=shipments),
    )
    monkeypatch.setattr(
        offers.weather,
        "get_current_weather",
        consultar,
    )
    monkeypatch.setattr(
        offers,
        "render_template",
        Mock(return_value="ok"),
    )

    with app.test_request_context("/"):
        offers.home()

    consultar.assert_not_called()
    assert shipments[0]["clima"] is None


def test_home_destino_texto_remove_espacos(
    offers_app, monkeypatch
):
    app, _ = offers_app
    shipments = [{"destino": "  Campinas, SP  "}]
    consultar = Mock(return_value={"condicao": "Sol"})

    monkeypatch.setattr(offers, "current_user", make_user())
    monkeypatch.setattr(
        offers,
        "listar_fretes_em_oferta",
        Mock(return_value=shipments),
    )
    monkeypatch.setattr(
        offers.weather,
        "get_current_weather",
        consultar,
    )
    monkeypatch.setattr(
        offers,
        "render_template",
        Mock(return_value="ok"),
    )

    with app.test_request_context("/"):
        offers.home()

    consultar.assert_called_once_with("Campinas, SP")
    assert shipments[0]["clima"] == {"condicao": "Sol"}


@pytest.mark.parametrize(
    "destino",
    [
        None,
        "",
        "   ",
        123,
        12.5,
        [],
        ["Campinas"],
        True,
    ],
)
def test_home_destinos_sem_localizacao_nao_consultam_clima(
    offers_app, monkeypatch, destino
):
    app, _ = offers_app
    shipments = [{"destino": destino}]
    consultar = Mock()

    monkeypatch.setattr(offers, "current_user", make_user())
    monkeypatch.setattr(
        offers,
        "listar_fretes_em_oferta",
        Mock(return_value=shipments),
    )
    monkeypatch.setattr(
        offers.weather,
        "get_current_weather",
        consultar,
    )
    monkeypatch.setattr(
        offers,
        "render_template",
        Mock(return_value="ok"),
    )

    with app.test_request_context("/"):
        offers.home()

    consultar.assert_not_called()
    assert shipments[0]["clima"] is None


def test_home_destino_dict_vazio_nao_consulta_clima(
    offers_app, monkeypatch
):
    app, _ = offers_app
    shipments = [{"destino": {}}]
    consultar = Mock()

    monkeypatch.setattr(offers, "current_user", make_user())
    monkeypatch.setattr(
        offers,
        "listar_fretes_em_oferta",
        Mock(return_value=shipments),
    )
    monkeypatch.setattr(
        offers.weather,
        "get_current_weather",
        consultar,
    )
    monkeypatch.setattr(
        offers,
        "render_template",
        Mock(return_value="ok"),
    )

    with app.test_request_context("/"):
        offers.home()

    consultar.assert_not_called()
    assert shipments[0]["clima"] is None


def test_home_reutiliza_clima_para_destinos_iguais(
    offers_app, monkeypatch
):
    app, _ = offers_app
    shipments = [
        {"destino": "Campinas, SP"},
        {"destino": "Campinas, SP"},
        {"destino": " São Paulo, SP "},
    ]
    consultar = Mock(return_value={"temperatura": 20})

    monkeypatch.setattr(offers, "current_user", make_user())
    monkeypatch.setattr(
        offers,
        "listar_fretes_em_oferta",
        Mock(return_value=shipments),
    )
    monkeypatch.setattr(
        offers.weather,
        "get_current_weather",
        consultar,
    )
    monkeypatch.setattr(
        offers,
        "render_template",
        Mock(return_value="ok"),
    )

    with app.test_request_context("/"):
        offers.home()

    assert consultar.call_count == 2
    consultar.assert_any_call("Campinas, SP")
    consultar.assert_any_call("São Paulo, SP")

    assert all(
        shipment["clima"] == {"temperatura": 20}
        for shipment in shipments
    )


def test_home_consulta_clima_separadamente_para_destinos_diferentes(
    offers_app, monkeypatch
):
    app, _ = offers_app
    shipments = [
        {"destino": "Campinas"},
        {"destino": "Santos"},
    ]
    consultar = Mock(side_effect=["clima-campinas", "clima-santos"])

    monkeypatch.setattr(offers, "current_user", make_user())
    monkeypatch.setattr(
        offers,
        "listar_fretes_em_oferta",
        Mock(return_value=shipments),
    )
    monkeypatch.setattr(
        offers.weather,
        "get_current_weather",
        consultar,
    )
    monkeypatch.setattr(
        offers,
        "render_template",
        Mock(return_value="ok"),
    )

    with app.test_request_context("/"):
        offers.home()

    assert consultar.call_count == 2
    assert shipments[0]["clima"] == "clima-campinas"
    assert shipments[1]["clima"] == "clima-santos"


def test_home_clima_none_quando_servico_retorna_none(
    offers_app, monkeypatch
):
    app, _ = offers_app
    shipments = [{"destino": "Campinas"}]

    monkeypatch.setattr(offers, "current_user", make_user())
    monkeypatch.setattr(
        offers,
        "listar_fretes_em_oferta",
        Mock(return_value=shipments),
    )
    monkeypatch.setattr(
        offers.weather,
        "get_current_weather",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        offers,
        "render_template",
        Mock(return_value="ok"),
    )

    with app.test_request_context("/"):
        offers.home()

    assert shipments[0]["clima"] is None


def test_home_lista_vazia_nao_consulta_clima(
    offers_app, monkeypatch
):
    app, _ = offers_app
    consultar = Mock()

    monkeypatch.setattr(offers, "current_user", make_user())
    monkeypatch.setattr(
        offers,
        "listar_fretes_em_oferta",
        Mock(return_value=[]),
    )
    monkeypatch.setattr(
        offers.weather,
        "get_current_weather",
        consultar,
    )
    monkeypatch.setattr(
        offers,
        "render_template",
        Mock(return_value="ok"),
    )

    with app.test_request_context("/"):
        offers.home()

    consultar.assert_not_called()


def test_home_destino_ausente_define_clima_none(
    offers_app, monkeypatch
):
    app, _ = offers_app
    shipments = [{}]

    monkeypatch.setattr(offers, "current_user", make_user())
    monkeypatch.setattr(
        offers,
        "listar_fretes_em_oferta",
        Mock(return_value=shipments),
    )
    monkeypatch.setattr(
        offers.weather,
        "get_current_weather",
        Mock(return_value="não deveria consultar"),
    )
    monkeypatch.setattr(
        offers,
        "render_template",
        Mock(return_value="ok"),
    )

    with app.test_request_context("/"):
        offers.home()

    assert shipments[0]["clima"] is None


def test_home_propaga_erro_do_servico_de_clima(
    offers_app, monkeypatch
):
    app, _ = offers_app

    monkeypatch.setattr(offers, "current_user", make_user())
    monkeypatch.setattr(
        offers,
        "listar_fretes_em_oferta",
        Mock(return_value=[{"destino": "Campinas"}]),
    )
    monkeypatch.setattr(
        offers.weather,
        "get_current_weather",
        Mock(side_effect=RuntimeError("falha no clima")),
    )
    monkeypatch.setattr(
        offers,
        "render_template",
        Mock(return_value="ok"),
    )

    with app.test_request_context("/"):
        with pytest.raises(RuntimeError, match="falha no clima"):
            offers.home()


# ============================================================
# ENVIAR PROPOSTA - AUTORIZAÇÃO E JSON
# ============================================================

def test_proposta_rejeita_usuario_que_nao_e_transportadora(
    offers_app, monkeypatch
):
    app, _ = offers_app
    user = make_user(role="internal")

    registrar = Mock()
    monkeypatch.setattr(offers, "registrar_proposta", registrar)

    result = call_proposal(
        app,
        monkeypatch,
        user,
        {"valor": 1000, "prazo_dias": 10},
    )

    data, status = response_json(result)

    assert status == 403
    assert data == {
        "ok": False,
        "erro": "Apenas transportadoras podem enviar propostas.",
    }
    registrar.assert_not_called()


def test_proposta_rejeita_json_ausente(
    offers_app, monkeypatch
):
    app, _ = offers_app
    user = make_user()

    monkeypatch.setattr(offers, "current_user", user)

    with app.test_request_context(
        "/api/ofertas/123/propostas",
        method="POST",
        data="",
        content_type="application/json",
    ):
        result = offers.enviar_proposta.__wrapped__(123)

    data, status = response_json(result)

    assert status == 400
    assert data["erro"] == "Dados da proposta inválidos."


@pytest.mark.parametrize(
    "payload",
    [
        [],
        "texto",
        123,
        12.5,
        True,
    ],
)
def test_proposta_rejeita_json_que_nao_e_dicionario(
    offers_app, monkeypatch, payload
):
    app, _ = offers_app
    user = make_user()

    monkeypatch.setattr(offers, "current_user", user)

    with app.test_request_context(
        "/api/ofertas/123/propostas",
        method="POST",
        data=__import__("json").dumps(payload),
        content_type="application/json",
    ):
        result = offers.enviar_proposta.__wrapped__(123)

    data, status = response_json(result)

    assert status == 400
    assert data["erro"] == "Dados da proposta inválidos."


def test_proposta_rejeita_transportadora_vazia(
    offers_app, monkeypatch
):
    app, _ = offers_app
    user = make_user(carrier_name="   ")
    registrar = Mock()

    monkeypatch.setattr(offers, "registrar_proposta", registrar)

    result = call_proposal(
        app,
        monkeypatch,
        user,
        {"valor": 1000, "prazo_dias": 10},
    )

    data, status = response_json(result)

    assert status == 400
    assert data["erro"] == "Transportadora não identificada na conta."
    registrar.assert_not_called()


def test_proposta_rejeita_transportadora_none(
    offers_app, monkeypatch
):
    app, _ = offers_app
    user = make_user(carrier_name=None)

    result = call_proposal(
        app,
        monkeypatch,
        user,
        {"valor": 1000, "prazo_dias": 10},
    )

    data, status = response_json(result)

    assert status == 400
    assert data["erro"] == "Transportadora não identificada na conta."


# ============================================================
# VALOR
# ============================================================

@pytest.mark.parametrize(
    "valor",
    [
        None,
        "",
        "abc",
        " ",
        0,
        -1,
        -100.50,
        float("nan"),
        float("inf"),
        float("-inf"),
        "NaN",
        "Infinity",
        "-Infinity",
    ],
)
def test_proposta_rejeita_valor_invalido(
    offers_app, monkeypatch, valor
):
    app, _ = offers_app
    registrar = Mock()
    monkeypatch.setattr(offers, "registrar_proposta", registrar)

    result = call_proposal(
        app,
        monkeypatch,
        make_user(),
        {"valor": valor, "prazo_dias": 10},
    )

    data, status = response_json(result)

    assert status == 400
    assert data["erro"] == "Informe um valor proposto maior que zero."
    registrar.assert_not_called()


@pytest.mark.parametrize(
    ("valor_original", "valor_esperado"),
    [
        (1, 1.0),
        ("1000.50", 1000.50),
        (2500, 2500.0),
        ("0.01", 0.01),
    ],
)
def test_proposta_converte_valor_para_float(
    offers_app,
    monkeypatch,
    valor_original,
    valor_esperado,
):
    app, _ = offers_app
    registrar = Mock(return_value=77)
    monkeypatch.setattr(offers, "registrar_proposta", registrar)

    result = call_proposal(
        app,
        monkeypatch,
        make_user(),
        {"valor": valor_original, "prazo_dias": 10},
    )

    data, status = response_json(result)

    assert status == 201
    assert data["proposta_id"] == 77
    assert registrar.call_args.kwargs["valor"] == valor_esperado


# ============================================================
# PRAZO
# ============================================================

@pytest.mark.parametrize(
    "prazo",
    [
        None,
        "",
        "abc",
        " ",
        0,
        -1,
        366,
        1000,
        1.5,
        float("inf"),
        float("-inf"),
        True,
        False,
    ],
)

def test_proposta_rejeita_prazo_invalido(
    offers_app, monkeypatch, prazo
):
    app, _ = offers_app
    registrar = Mock()
    monkeypatch.setattr(offers, "registrar_proposta", registrar)

    result = call_proposal(
        app,
        monkeypatch,
        make_user(),
        {"valor": 1000, "prazo_dias": prazo},
    )

    data, status = response_json(result)

    assert status == 400
    assert data["erro"] == "Informe um prazo válido entre 1 e 365 dias."
    registrar.assert_not_called()


@pytest.mark.parametrize("prazo", [1, 2, 30, 180, 365, "1", "365"])
def test_proposta_aceita_prazo_dentro_do_intervalo(
    offers_app, monkeypatch, prazo
):
    app, _ = offers_app
    registrar = Mock(return_value=10)
    monkeypatch.setattr(offers, "registrar_proposta", registrar)

    result = call_proposal(
        app,
        monkeypatch,
        make_user(),
        {"valor": 1000, "prazo_dias": prazo},
    )

    data, status = response_json(result)

    assert status == 201
    assert registrar.call_args.kwargs["prazo_dias"] == int(prazo)


# ============================================================
# OBSERVAÇÕES
# ============================================================

def test_proposta_aceita_observacoes_ausentes(
    offers_app, monkeypatch
):
    app, _ = offers_app
    registrar = Mock(return_value=15)
    monkeypatch.setattr(offers, "registrar_proposta", registrar)

    result = call_proposal(
        app,
        monkeypatch,
        make_user(),
        {"valor": 1000, "prazo_dias": 10},
    )

    data, status = response_json(result)

    assert status == 201
    assert registrar.call_args.kwargs["observacoes"] == ""


def test_proposta_converte_observacoes_none_para_vazio(
    offers_app, monkeypatch
):
    app, _ = offers_app
    registrar = Mock(return_value=15)
    monkeypatch.setattr(offers, "registrar_proposta", registrar)

    result = call_proposal(
        app,
        monkeypatch,
        make_user(),
        {
            "valor": 1000,
            "prazo_dias": 10,
            "observacoes": None,
        },
    )

    data, status = response_json(result)

    assert status == 201
    assert registrar.call_args.kwargs["observacoes"] == ""


def test_proposta_remove_espacos_das_observacoes(
    offers_app, monkeypatch
):
    app, _ = offers_app
    registrar = Mock(return_value=15)
    monkeypatch.setattr(offers, "registrar_proposta", registrar)

    result = call_proposal(
        app,
        monkeypatch,
        make_user(),
        {
            "valor": 1000,
            "prazo_dias": 10,
            "observacoes": "  Entrega urgente  ",
        },
    )

    data, status = response_json(result)

    assert status == 201
    assert registrar.call_args.kwargs["observacoes"] == "Entrega urgente"


def test_proposta_aceita_observacoes_com_2000_caracteres(
    offers_app, monkeypatch
):
    app, _ = offers_app
    registrar = Mock(return_value=15)
    observacoes = "A" * 2000

    monkeypatch.setattr(offers, "registrar_proposta", registrar)

    result = call_proposal(
        app,
        monkeypatch,
        make_user(),
        {
            "valor": 1000,
            "prazo_dias": 10,
            "observacoes": observacoes,
        },
    )

    data, status = response_json(result)

    assert status == 201
    assert registrar.call_args.kwargs["observacoes"] == observacoes


def test_proposta_rejeita_observacoes_com_mais_de_2000_caracteres(
    offers_app, monkeypatch
):
    app, _ = offers_app
    registrar = Mock()
    monkeypatch.setattr(offers, "registrar_proposta", registrar)

    result = call_proposal(
        app,
        monkeypatch,
        make_user(),
        {
            "valor": 1000,
            "prazo_dias": 10,
            "observacoes": "A" * 2001,
        },
    )

    data, status = response_json(result)

    assert status == 400
    assert data["erro"] == "Observações excedem 2000 caracteres."
    registrar.assert_not_called()


def test_proposta_converte_observacoes_numericas_para_string(
    offers_app, monkeypatch
):
    app, _ = offers_app
    registrar = Mock(return_value=15)
    monkeypatch.setattr(offers, "registrar_proposta", registrar)

    result = call_proposal(
        app,
        monkeypatch,
        make_user(),
        {
            "valor": 1000,
            "prazo_dias": 10,
            "observacoes": 123,
        },
    )

    data, status = response_json(result)

    assert status == 201
    assert registrar.call_args.kwargs["observacoes"] == "123"


# ============================================================
# REGISTRO DA PROPOSTA
# ============================================================

def test_proposta_registra_dados_corretos(
    offers_app, monkeypatch
):
    app, _ = offers_app
    registrar = Mock(return_value=456)
    user = make_user(carrier_name="  Transportadora ABC  ")

    monkeypatch.setattr(offers, "registrar_proposta", registrar)

    result = call_proposal(
        app,
        monkeypatch,
        user,
        {
            "valor": "2500.75",
            "prazo_dias": "30",
            "observacoes": "  Carga refrigerada  ",
        },
    )

    data, status = response_json(result)

    assert status == 201
    assert data == {
        "ok": True,
        "mensagem": "Proposta enviada com sucesso!",
        "proposta_id": 456,
    }

    registrar.assert_called_once_with(
        frete_id=123,
        transportadora="Transportadora ABC",
        valor=2500.75,
        prazo_dias=30,
        observacoes="Carga refrigerada",
    )


def test_proposta_usa_transportadora_da_sessao_e_ignora_json(
    offers_app, monkeypatch
):
    app, _ = offers_app
    registrar = Mock(return_value=456)

    monkeypatch.setattr(offers, "registrar_proposta", registrar)

    result = call_proposal(
        app,
        monkeypatch,
        make_user(carrier_name="Transportadora da Conta"),
        {
            "valor": 1000,
            "prazo_dias": 10,
            "transportadora": "Transportadora Falsa",
        },
    )

    data, status = response_json(result)

    assert status == 201
    assert registrar.call_args.kwargs["transportadora"] == "Transportadora da Conta"


def test_proposta_trata_value_error_do_repositorio(
    offers_app, monkeypatch
):
    app, _ = offers_app

    monkeypatch.setattr(
        offers,
        "registrar_proposta",
        Mock(side_effect=ValueError("Frete não disponível.")),
    )

    result = call_proposal(
        app,
        monkeypatch,
        make_user(),
        {"valor": 1000, "prazo_dias": 10},
    )

    data, status = response_json(result)

    assert status == 400
    assert data == {
        "ok": False,
        "erro": "Frete não disponível.",
    }


def test_proposta_trata_excecao_inesperada_do_repositorio(
    offers_app, monkeypatch
):
    app, _ = offers_app
    registrar = Mock(side_effect=RuntimeError("erro interno"))
    log_exception = Mock()

    monkeypatch.setattr(offers, "registrar_proposta", registrar)
    monkeypatch.setattr(offers.log, "exception", log_exception)

    result = call_proposal(
        app,
        monkeypatch,
        make_user(),
        {"valor": 1000, "prazo_dias": 10},
    )

    data, status = response_json(result)

    assert status == 500
    assert data == {
        "ok": False,
        "erro": "Erro interno ao registrar a proposta.",
    }

    log_exception.assert_called_once_with(
        "Erro ao registrar proposta do frete %s pela transportadora %s",
        123,
        "Transportadora Teste",
    )


@pytest.mark.parametrize(
    "exception",
    [
        RuntimeError("erro"),
        TypeError("tipo inválido"),
        OverflowError("overflow"),
    ],
)
def test_proposta_trata_diferentes_excecoes_inesperadas(
    offers_app, monkeypatch, exception
):
    app, _ = offers_app

    monkeypatch.setattr(
        offers,
        "registrar_proposta",
        Mock(side_effect=exception),
    )
    monkeypatch.setattr(offers.log, "exception", Mock())

    result = call_proposal(
        app,
        monkeypatch,
        make_user(),
        {"valor": 1000, "prazo_dias": 10},
    )

    data, status = response_json(result)

    assert status == 500
    assert data["erro"] == "Erro interno ao registrar a proposta."


