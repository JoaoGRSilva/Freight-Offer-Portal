
import pytest

from services import freight_cost


@pytest.fixture
def tabelas_custos(monkeypatch):
    monkeypatch.setattr(
        freight_cost,
        "antt",
        {
            4: {
                "ccd": 2.50,
                "cc": 150.00,
            },
            6: {
                "ccd": 3.20,
                "cc": 200.00,
            },
        },
    )

    monkeypatch.setattr(
        freight_cost,
        "preco_gasolina_max",
        {
            "SP": 6.00,
            "MG": 6.50,
        },
    )

    monkeypatch.setattr(
        freight_cost,
        "consumo_tabela",
        {
            ("graneleiro", 4, "asfalto"): 2.0,
            ("graneleiro", 4, "terra"): 1.0,
            ("graneleiro", 6, "asfalto"): 1.5,
            ("sider", 4, "asfalto"): 2.5,
        },
    )


def test_calcular_custos_com_um_trecho(tabelas_custos):
    resultado = freight_cost.calcular_custos(
        uf="SP",
        peso_kg=10000,
        eixos=4,
        categoria="graneleiro",
        trechos=[
            {
                "distancia_km": 100,
                "pavimento": "asfalto",
            }
        ],
    )

    assert resultado["distancia_total_km"] == 100
    assert resultado["litros_totais"] == 50
    assert resultado["custo_combustivel"] == 300
    assert resultado["antt"] == 400
    assert resultado["mercado"] == pytest.approx(300 / 0.415)


def test_calcular_custos_com_multiplos_trechos(tabelas_custos):
    resultado = freight_cost.calcular_custos(
        uf="SP",
        peso_kg=20000,
        eixos=4,
        categoria="graneleiro",
        trechos=[
            {
                "distancia_km": 100,
                "pavimento": "asfalto",
            },
            {
                "distancia_km": 50,
                "pavimento": "terra",
            },
        ],
    )

    # 100 / 2 + 50 / 1 = 100 litros
    assert resultado["distancia_total_km"] == 150
    assert resultado["litros_totais"] == 100
    assert resultado["custo_combustivel"] == 600
    assert resultado["antt"] == 525
    assert resultado["mercado"] == pytest.approx(600 / 0.415)


def test_calcular_custos_com_lista_de_trechos_vazia(
    tabelas_custos,
):
    resultado = freight_cost.calcular_custos(
        uf="SP",
        peso_kg=10000,
        eixos=4,
        categoria="graneleiro",
        trechos=[],
    )

    assert resultado == {
        "antt": 150,
        "mercado": 0,
        "distancia_total_km": 0,
        "litros_totais": 0,
        "custo_combustivel": 0,
    }


def test_calcular_custos_utiliza_tabela_antt_dos_eixos(
    tabelas_custos,
):
    resultado = freight_cost.calcular_custos(
        uf="MG",
        peso_kg=30000,
        eixos=6,
        categoria="graneleiro",
        trechos=[
            {
                "distancia_km": 150,
                "pavimento": "asfalto",
            }
        ],
    )

    assert resultado["antt"] == pytest.approx(680)
    assert resultado["litros_totais"] == 100
    assert resultado["custo_combustivel"] == 650
    assert resultado["mercado"] == pytest.approx(650 / 0.415)


def test_calcular_custos_utiliza_categoria_do_caminhao(
    tabelas_custos,
):
    resultado = freight_cost.calcular_custos(
        uf="SP",
        peso_kg=10000,
        eixos=4,
        categoria="sider",
        trechos=[
            {
                "distancia_km": 100,
                "pavimento": "asfalto",
            }
        ],
    )

    assert resultado["litros_totais"] == 40
    assert resultado["custo_combustivel"] == 240
    assert resultado["mercado"] == pytest.approx(240 / 0.415)


def test_calcular_custos_utiliza_preco_de_combustivel_da_uf(
    tabelas_custos,
):
    resultado = freight_cost.calcular_custos(
        uf="MG",
        peso_kg=10000,
        eixos=4,
        categoria="graneleiro",
        trechos=[
            {
                "distancia_km": 100,
                "pavimento": "asfalto",
            }
        ],
    )

    assert resultado["litros_totais"] == 50
    assert resultado["custo_combustivel"] == 325
    assert resultado["mercado"] == pytest.approx(325 / 0.415)


def test_calcular_custos_com_distancia_fracionada(
    tabelas_custos,
):
    resultado = freight_cost.calcular_custos(
        uf="SP",
        peso_kg=10000,
        eixos=4,
        categoria="graneleiro",
        trechos=[
            {
                "distancia_km": 12.5,
                "pavimento": "asfalto",
            }
        ],
    )

    assert resultado["distancia_total_km"] == 12.5
    assert resultado["litros_totais"] == 6.25
    assert resultado["custo_combustivel"] == 37.5


def test_calcular_custos_com_distancia_zero(
    tabelas_custos,
):
    resultado = freight_cost.calcular_custos(
        uf="SP",
        peso_kg=10000,
        eixos=4,
        categoria="graneleiro",
        trechos=[
            {
                "distancia_km": 0,
                "pavimento": "asfalto",
            }
        ],
    )

    assert resultado["distancia_total_km"] == 0
    assert resultado["litros_totais"] == 0
    assert resultado["custo_combustivel"] == 0
    assert resultado["antt"] == 150
    assert resultado["mercado"] == 0


def test_calcular_custos_retorna_todas_as_chaves(
    tabelas_custos,
):
    resultado = freight_cost.calcular_custos(
        uf="SP",
        peso_kg=10000,
        eixos=4,
        categoria="graneleiro",
        trechos=[],
    )

    assert set(resultado.keys()) == {
        "antt",
        "mercado",
        "distancia_total_km",
        "litros_totais",
        "custo_combustivel",
    }


def test_calcular_custos_com_trecho_sem_distancia(
    tabelas_custos,
):
    with pytest.raises(KeyError, match="distancia_km"):
        freight_cost.calcular_custos(
            uf="SP",
            peso_kg=10000,
            eixos=4,
            categoria="graneleiro",
            trechos=[
                {
                    "pavimento": "asfalto",
                }
            ],
        )


def test_calcular_custos_com_trecho_sem_pavimento(
    tabelas_custos,
):
    with pytest.raises(KeyError, match="pavimento"):
        freight_cost.calcular_custos(
            uf="SP",
            peso_kg=10000,
            eixos=4,
            categoria="graneleiro",
            trechos=[
                {
                    "distancia_km": 100,
                }
            ],
        )


def test_calcular_custos_com_uf_nao_cadastrada(
    tabelas_custos,
):
    with pytest.raises(KeyError, match="XX"):
        freight_cost.calcular_custos(
            uf="XX",
            peso_kg=10000,
            eixos=4,
            categoria="graneleiro",
            trechos=[],
        )


def test_calcular_custos_com_quantidade_de_eixos_nao_cadastrada(
    tabelas_custos,
):
    with pytest.raises(KeyError):
        freight_cost.calcular_custos(
            uf="SP",
            peso_kg=10000,
            eixos=8,
            categoria="graneleiro",
            trechos=[],
        )


def test_calcular_custos_com_combinacao_inexistente(
    tabelas_custos,
):
    with pytest.raises(KeyError):
        freight_cost.calcular_custos(
            uf="SP",
            peso_kg=10000,
            eixos=4,
            categoria="basculante",
            trechos=[
                {
                    "distancia_km": 100,
                    "pavimento": "asfalto",
                }
            ],
        )


def test_calcular_custos_com_consumo_zero(
    tabelas_custos,
    monkeypatch,
):
    monkeypatch.setitem(
        freight_cost.consumo_tabela,
        ("graneleiro", 4, "asfalto"),
        0,
    )

    with pytest.raises(ZeroDivisionError):
        freight_cost.calcular_custos(
            uf="SP",
            peso_kg=10000,
            eixos=4,
            categoria="graneleiro",
            trechos=[
                {
                    "distancia_km": 100,
                    "pavimento": "asfalto",
                }
            ],
        )


def test_calcular_custos_com_trecho_invalido(
    tabelas_custos,
):
    with pytest.raises(TypeError):
        freight_cost.calcular_custos(
            uf="SP",
            peso_kg=10000,
            eixos=4,
            categoria="graneleiro",
            trechos=[None],
        )
