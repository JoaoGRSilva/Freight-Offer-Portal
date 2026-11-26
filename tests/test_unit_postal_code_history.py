
import numpy as np
import pandas as pd
import pytest

from services import postal_code_history as history


@pytest.fixture(autouse=True)
def reset_cache(monkeypatch):
    monkeypatch.setattr(history, "_MAPAS", None)


@pytest.fixture
def historico():
    return pd.DataFrame(
        [
            # Cliente A: empate; deve escolher o menor CEP.
            ("A", "São Paulo", "SP", "87654321"),
            ("A", "São Paulo", "SP", "12345678"),
            ("A", "São Paulo", "SP", "87654321"),
            ("A", "São Paulo", "SP", "12345678"),

            # Cliente B: CEP com sete dígitos.
            ("B", "Campinas", "SP", "1234567"),

            # Cidade com CEP mais frequente.
            ("C", "São Paulo", "SP", "11111111"),
            ("D", "São Paulo", "SP", "11111111"),
            ("E", "São Paulo", "SP", "22222222"),

            # Cliente sem região válida.
            ("F", "Curitiba", "Região inválida", "33333333"),

            # Linha com CEP inválido: deve ser descartada.
            ("G", "Rio de Janeiro", "RJ", "123"),

            # Linha sem cliente, mas com cidade e UF válidas.
            (None, "Campinas", "SP", "44444444"),
        ],
        columns=[
            "customer_id",
            "customer_city",
            "customer_region",
            "cep",
        ],
    )


# ============================================================
# NORMALIZAÇÃO DE TEXTO
# ============================================================

@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("São Paulo", "sao paulo"),
        ("  CAMPINAS  ", "campinas"),
        ("João D'Ávila", "joao d'avila"),
        ("ABC", "abc"),
        ("", ""),
        (None, ""),
        (np.nan, ""),
        (pd.NA, ""),
    ],
)
def test_norm_normaliza_texto(valor, esperado):
    assert history._norm(valor) == esperado


# ============================================================
# NORMALIZAÇÃO DE CEP
# ============================================================

@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("12345678", "12345678"),
        ("12.345-678", "12345678"),
        ("1234567", "01234567"),
        ("1234567.0", "01234567"),
        ("12345678.0", "12345678"),
        (" 12345-678 ", "12345678"),
        (12345678, "12345678"),
        (1234567.0, "01234567"),
        (None, None),
        (np.nan, None),
        (pd.NA, None),
        ("123456", None),
        ("123456789", None),
        ("abcdefgh", None),
        ("", None),
    ],
)
def test_cep8_normaliza_e_valida(valor, esperado):
    assert history._cep8(valor) == esperado


# ============================================================
# CARREGAMENTO DOS MAPAS
# ============================================================

def test_carregar_mapas_constroi_mapas_corretamente(
    monkeypatch,
    historico,
):
    monkeypatch.setattr(
        history.pd,
        "read_parquet",
        lambda *args, **kwargs: historico.copy(),
    )

    por_cliente, por_cidade = history._carregar_mapas()

    assert por_cliente["A"] == "12345678"
    assert por_cliente["B"] == "01234567"
    assert por_cliente["F"] == "33333333"

    assert ("sao paulo", "SP") in por_cidade
    assert por_cidade[("sao paulo", "SP")] == "11111111"

    assert por_cidade[("campinas", "SP")] == "01234567"

    # Cliente sem região válida não impede seu mapa individual.
    assert "F" in por_cliente

    # CEP inválido foi descartado.
    assert "G" not in por_cliente


def test_carregar_mapas_usa_cache(
    monkeypatch,
    historico,
):
    chamadas = []

    def fake_read_parquet(*args, **kwargs):
        chamadas.append(1)
        return historico.copy()

    monkeypatch.setattr(
        history.pd,
        "read_parquet",
        fake_read_parquet,
    )

    primeiro = history._carregar_mapas()
    segundo = history._carregar_mapas()

    assert primeiro is segundo
    assert len(chamadas) == 1


def test_carregar_mapas_com_historico_vazio(monkeypatch):
    vazio = pd.DataFrame(
        columns=[
            "customer_id",
            "customer_city",
            "customer_region",
            "cep",
        ]
    )

    monkeypatch.setattr(
        history.pd,
        "read_parquet",
        lambda *args, **kwargs: vazio.copy(),
    )

    por_cliente, por_cidade = history._carregar_mapas()

    assert por_cliente == {}
    assert por_cidade == {}



def test_carregar_mapas_sem_clientes_validos(monkeypatch):
    dados = pd.DataFrame(
        [
            (None, "São Paulo", "SP", "12345678"),
            (None, "Campinas", "SP", "87654321"),
        ],
        columns=[
            "customer_id",
            "customer_city",
            "customer_region",
            "cep",
        ],
    )

    monkeypatch.setattr(
        history.pd,
        "read_parquet",
        lambda *args, **kwargs: dados.copy(),
    )

    por_cliente, por_cidade = history._carregar_mapas()

    assert por_cliente == {}
    assert por_cidade == {
        ("campinas", "SP"): "87654321",
        ("sao paulo", "SP"): "12345678",
    }




def test_carregar_mapas_sem_ufs_validas(monkeypatch):
    dados = pd.DataFrame(
        [
            ("A", "São Paulo", "X", "12345678"),
            ("B", "Campinas", None, "87654321"),
        ],
        columns=[
            "customer_id",
            "customer_city",
            "customer_region",
            "cep",
        ],
    )

    monkeypatch.setattr(
        history.pd,
        "read_parquet",
        lambda *args, **kwargs: dados.copy(),
    )

    por_cliente, por_cidade = history._carregar_mapas()

    assert por_cliente == {
        "A": "12345678",
        "B": "87654321",
    }
    assert por_cidade == {}


# ============================================================
# PREENCHIMENTO DE CEP
# ============================================================

def test_preencher_cep_preserva_cep_existente():
    frete = {
        "cep": "12.345-678",
        "cep_origem": "manual",
    }

    history.preencher_cep(frete)

    assert frete["cep"] == "12345678"
    assert frete["cep_origem"] == "manual"


def test_preencher_cep_existente_define_origem_padrao():
    frete = {"cep": "12345678"}

    history.preencher_cep(frete)

    assert frete["cep"] == "12345678"
    assert frete["cep_origem"] == "arquivo"


def test_preencher_cep_preserva_origem_existente():
    frete = {
        "cep": "12345678",
        "cep_origem": None,
    }

    history.preencher_cep(frete)

    assert frete["cep_origem"] is None


def test_preencher_cep_nao_consulta_historico_em_multiplas_paradas(
    monkeypatch,
):
    def erro_se_chamar():
        pytest.fail("O histórico não deveria ser carregado")

    monkeypatch.setattr(history, "_carregar_mapas", erro_se_chamar)

    frete = {
        "cep": "",
        "tipo": "Múltiplas paradas",
    }

    history.preencher_cep(frete)

    assert frete["cep"] == ""
    assert frete["cep_origem"] is None


def test_preencher_cep_prioriza_cliente(monkeypatch):
    monkeypatch.setattr(
        history,
        "_carregar_mapas",
        lambda: (
            {"123": "11111111"},
            {("sao paulo", "SP"): "22222222"},
        ),
    )

    frete = {
        "cep": "",
        "customer": "123",
        "destino": "São Paulo",
        "uf": "SP",
    }

    history.preencher_cep(frete)

    assert frete["cep"] == "11111111"
    assert frete["cep_origem"] == "cliente"


def test_preencher_cep_usa_cidade_quando_cliente_nao_tem_cep(
    monkeypatch,
):
    monkeypatch.setattr(
        history,
        "_carregar_mapas",
        lambda: (
            {},
            {("sao paulo", "SP"): "12345678"},
        ),
    )

    frete = {
        "cep": "",
        "customer": "999",
        "destino": "São Paulo",
        "uf": "sp",
    }

    history.preencher_cep(frete)

    assert frete["cep"] == "12345678"
    assert frete["cep_origem"] == "cidade_uf"


def test_preencher_cep_usa_cidade_quando_cliente_nao_encontrado(
    monkeypatch,
):
    monkeypatch.setattr(
        history,
        "_carregar_mapas",
        lambda: (
            {"123": "11111111"},
            {("campinas", "SP"): "22222222"},
        ),
    )

    frete = {
        "cep": "",
        "customer": "999",
        "destino": "Campinas",
        "uf": "SP",
    }

    history.preencher_cep(frete)

    assert frete["cep"] == "22222222"
    assert frete["cep_origem"] == "cidade_uf"


def test_preencher_cep_nao_encontrado(monkeypatch):
    monkeypatch.setattr(
        history,
        "_carregar_mapas",
        lambda: ({}, {}),
    )

    frete = {
        "cep": "inválido",
        "customer": "999",
        "destino": "Cidade desconhecida",
        "uf": "XX",
    }

    history.preencher_cep(frete)

    assert frete["cep"] == ""
    assert frete["cep_origem"] is None


def test_preencher_cep_sem_customer(monkeypatch):
    monkeypatch.setattr(
        history,
        "_carregar_mapas",
        lambda: (
            {},
            {("campinas", "SP"): "12345678"},
        ),
    )

    frete = {
        "cep": None,
        "customer": None,
        "destino": "Campinas",
        "uf": "SP",
    }

    history.preencher_cep(frete)

    assert frete["cep"] == "12345678"
    assert frete["cep_origem"] == "cidade_uf"


def test_preencher_cep_nao_encontra_cidade_com_uf_diferente(
    monkeypatch,
):
    monkeypatch.setattr(
        history,
        "_carregar_mapas",
        lambda: (
            {},
            {("campinas", "SP"): "12345678"},
        ),
    )

    frete = {
        "cep": "",
        "customer": "999",
        "destino": "Campinas",
        "uf": "RJ",
    }

    history.preencher_cep(frete)

    assert frete["cep"] == ""
    assert frete["cep_origem"] is None
