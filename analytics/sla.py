
"""
Cálculo do SLA geral por transportadora.
"""

import pandas as pd

from analytics.history import obter_historico_consolidado


def calcular_sla_transportadoras(historico=None):
    """
    Calcula o SLA geral por transportadora.

    Cada frete consolidado é considerado uma viagem.
    Um frete é considerado dentro do SLA quando sla_frete=True.

    Retorna um DataFrame com:
    - service_agent_description
    - viagens_historicas
    - viagens_dentro_sla
    - sla_geral
    """

    if historico is None:
        historico = obter_historico_consolidado()

    if historico.empty:
        return pd.DataFrame(
            columns=[
                "service_agent_description",
                "viagens_historicas",
                "viagens_dentro_sla",
                "sla_geral",
            ]
        )

    df = historico.copy()

    df = df[
        df["service_agent_description"].notna()
        & df["service_agent_description"].astype(str).str.strip().ne("")
    ].copy()

    resultado = (
        df.groupby("service_agent_description")
        .agg(
            viagens_historicas=("freight_id", "nunique"),
            viagens_dentro_sla=("sla_frete", "sum"),
            sla_geral=("sla_frete", "mean"),
        )
        .reset_index()
    )

    resultado["sla_geral"] = (
        resultado["sla_geral"] * 100
    ).round(1)

    return resultado.sort_values(
        "sla_geral",
        ascending=False,
    )