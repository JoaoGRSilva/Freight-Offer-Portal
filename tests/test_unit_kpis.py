
import numpy as np
import pandas as pd
import pytest

from analytics import kpis


@pytest.fixture
def df_kpis():
    return pd.DataFrame({
        "freight_id": [1, 2, 2, 3],
        "savings_value": [-100.0, -200.0, 50.0, 0.0],
        "negotiated_value": [1000.0, 2000.0, 500.0, 1500.0],
        "lead_time_days": [2.0, 4.0, 6.0, 8.0],
        "sla_met": [1, 1, 0, 0],
        "year_month": ["2026-01", "2026-01", "2026-02", "2026-02"],
        "service_agent_description": ["Transportadora A", "Transportadora B", "Transportadora A", "Transportadora C"],
        "customer_region": ["SP", "RJ", "SP", "MG"],
        "customer_name": ["Cliente 1", "Cliente 2", "Cliente 1", "Cliente 3"],
    })


def mock_parquet(monkeypatch, df):
    monkeypatch.setattr(
        kpis.pd,
        "read_parquet",
        lambda *args, **kwargs: df.copy(),
    )


# ============================================================
# formatar_moeda
# ============================================================

@pytest.mark.parametrize(
    "valor, esperado",
    [
        (1000, "R$ 1.000,00"),
        (1234.56, "R$ 1.234,56"),
        (0, "R$ 0,00"),
        (-1234.56, "R$ -1.234,56"),
        (0.5, "R$ 0,50"),
        (None, "R$ 0,00"),
        (np.nan, "R$ 0,00"),
    ],
)
def test_formatar_moeda(valor, esperado):
    assert kpis.formatar_moeda(valor) == esperado


# ============================================================
# obter_kpis
# ============================================================

def test_obter_kpis_calcula_indicadores_corretamente(
    monkeypatch,
    df_kpis,
):
    mock_parquet(monkeypatch, df_kpis)

    resultado = kpis.obter_kpis()

    assert resultado == {
        "fretes": "3",
        "valor_negociado": "R$ 5.000,00",
        "savings": "R$ 250,00",
        "savings_positivo": False,
        "lead_time": "5.0 dias",
        "sla_medio": "50.00%",
    }


def test_obter_kpis_com_savings_positivo(
    monkeypatch,
    df_kpis,
):
    df = df_kpis.copy()
    df["savings_value"] = [100, 200, 300, 400]

    mock_parquet(monkeypatch, df)

    resultado = kpis.obter_kpis()

    assert resultado["savings"] == "R$ 1.000,00"
    assert bool(resultado["savings_positivo"]) is True


def test_obter_kpis_com_savings_zero(
    monkeypatch,
    df_kpis,
):
    df = df_kpis.copy()
    df["savings_value"] = [0, 0, 0, 0]

    mock_parquet(monkeypatch, df)

    resultado = kpis.obter_kpis()

    assert resultado["savings"] == "R$ 0,00"
    assert bool(resultado["savings_positivo"]) is False


def test_obter_kpis_chama_parquet_no_caminho_esperado(
    monkeypatch,
    df_kpis,
):
    chamadas = []

    def fake_read_parquet(caminho):
        chamadas.append(caminho)
        return df_kpis.copy()

    monkeypatch.setattr(kpis.pd, "read_parquet", fake_read_parquet)

    kpis.obter_kpis()

    assert chamadas == ["data/processed/baseEA.parquet"]


# ============================================================
# obter_evolucao_mensal
# ============================================================

def test_obter_evolucao_mensal_filtra_valores_invalidos(
    monkeypatch,
):
    df = pd.DataFrame({
        "year_month": [
            "2026-01",
            "2026-01",
            "2026-02",
            "2026-02",
            "2026-03",
        ],
        "negotiated_value": [
            100.0,
            200.0,
            0.0,
            -50.0,
            np.nan,
        ],
        "freight_id": [1, 2, 3, 4, 5],
    })

    mock_parquet(monkeypatch, df)

    resultado = kpis.obter_evolucao_mensal()

    assert resultado.to_dict("records") == [
        {
            "year_month": "2026-01",
            "negotiated_value": 300.0,
            "freight_count": 2,
        }
    ]


def test_obter_evolucao_mensal_conta_fretes_unicos(
    monkeypatch,
):
    df = pd.DataFrame({
        "year_month": ["2026-01", "2026-01", "2026-01"],
        "negotiated_value": [100.0, 200.0, 300.0],
        "freight_id": [1, 1, 2],
    })

    mock_parquet(monkeypatch, df)

    resultado = kpis.obter_evolucao_mensal()

    assert len(resultado) == 1
    assert resultado.iloc[0]["negotiated_value"] == 600.0
    assert resultado.iloc[0]["freight_count"] == 2


def test_obter_evolucao_mensal_retorna_vazio_sem_valores_positivos(
    monkeypatch,
):
    df = pd.DataFrame({
        "year_month": ["2026-01", "2026-02"],
        "negotiated_value": [0.0, -100.0],
        "freight_id": [1, 2],
    })

    mock_parquet(monkeypatch, df)

    resultado = kpis.obter_evolucao_mensal()

    assert resultado.empty
    assert list(resultado.columns) == [
        "year_month",
        "negotiated_value",
        "freight_count",
    ]


# ============================================================
# obter_top_transportadoras
# ============================================================

def test_obter_top_transportadoras_agrupa_e_ordena(
    monkeypatch,
    df_kpis,
):
    mock_parquet(monkeypatch, df_kpis)

    resultado = kpis.obter_top_transportadoras()

    assert list(resultado.index) == [
        "Transportadora B",
        "Transportadora A",
        "Transportadora C",
    ]

    assert resultado.loc["Transportadora A", "negotiated_value"] == 1500.0
    assert resultado.loc["Transportadora A", "freight_count"] == 2
    assert resultado.loc["Transportadora A", "sla"] == 0.5


def test_obter_top_transportadoras_limita_dez_resultados(
    monkeypatch,
):
    df = pd.DataFrame({
        "service_agent_description": [
            f"Transportadora {i}" for i in range(15)
        ],
        "negotiated_value": [
            float(i * 100) for i in range(15)
        ],
        "freight_id": list(range(15)),
        "sla_met": [1] * 15,
    })

    mock_parquet(monkeypatch, df)

    resultado = kpis.obter_top_transportadoras()

    assert len(resultado) == 10
    assert resultado.iloc[0]["negotiated_value"] == 1400.0
    assert resultado.iloc[-1]["negotiated_value"] == 500.0


def test_obter_top_transportadoras_retorna_vazio_sem_registros(
    monkeypatch,
):
    df = pd.DataFrame({
        "service_agent_description": pd.Series(dtype="object"),
        "negotiated_value": pd.Series(dtype="float"),
        "freight_id": pd.Series(dtype="int"),
        "sla_met": pd.Series(dtype="float"),
    })

    mock_parquet(monkeypatch, df)

    resultado = kpis.obter_top_transportadoras()

    assert resultado.empty


# ============================================================
# obter_performance_estado
# ============================================================

def test_obter_performance_estado_agrupa_por_estado(
    monkeypatch,
    df_kpis,
):
    mock_parquet(monkeypatch, df_kpis)

    resultado = kpis.obter_performance_estado()

    assert list(resultado.columns) == [
        "customer_region",
        "negotiated_value",
        "freight_count",
        "clientes",
        "sla",
    ]

    sp = resultado[resultado["customer_region"] == "SP"].iloc[0]

    assert sp["negotiated_value"] == 1500.0
    assert sp["freight_count"] == 2
    assert sp["clientes"] == 1
    assert sp["sla"] == 0.5


def test_obter_performance_estado_conta_clientes_unicos(
    monkeypatch,
):
    df = pd.DataFrame({
        "customer_region": ["SP", "SP", "SP", "RJ"],
        "negotiated_value": [100, 200, 300, 400],
        "freight_id": [1, 2, 3, 4],
        "customer_name": [
            "Cliente A",
            "Cliente A",
            "Cliente B",
            "Cliente C",
        ],
        "sla_met": [1, 0, 1, 1],
    })

    mock_parquet(monkeypatch, df)

    resultado = kpis.obter_performance_estado()

    sp = resultado[resultado["customer_region"] == "SP"].iloc[0]

    assert sp["clientes"] == 2
    assert sp["freight_count"] == 3
    assert sp["negotiated_value"] == 600
    assert pytest.approx(sp["sla"]) == 2 / 3


def test_obter_performance_estado_retorna_vazio_sem_registros(
    monkeypatch,
):
    df = pd.DataFrame({
        "customer_region": pd.Series(dtype="object"),
        "negotiated_value": pd.Series(dtype="float"),
        "freight_id": pd.Series(dtype="int"),
        "customer_name": pd.Series(dtype="object"),
        "sla_met": pd.Series(dtype="float"),
    })

    mock_parquet(monkeypatch, df)

    resultado = kpis.obter_performance_estado()

    assert resultado.empty
    assert "customer_region" in resultado.columns
