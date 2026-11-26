"""
Consolidação do histórico de fretes.

A base original possui várias linhas para o mesmo freight_id.

Este módulo mantém duas granularidades:

1. HISTÓRICO CONSOLIDADO
   Uma linha por freight_id.

   Utilizado para:
   - SLA;
   - quantidade de viagens;
   - similaridade;
   - recência;
   - peso;
   - análise de rotas.

2. HISTÓRICO DETALHADO
   Uma linha por registro original do parquet.

   Utilizado para:
   - valores negociados;
   - referência econômica;
   - média de valor por pedido/registro.

Isso evita misturar granularidades diferentes.

Uso:

    from analytics.history import (
        obter_historico_consolidado,
        obter_historico_detalhado,
    )
"""

import os

import pandas as pd

from analytics import config as C


# ============================================================
# COLUNAS NECESSÁRIAS DO PARQUET
# ============================================================

COLUNAS = [
    "freight_id",
    "pd_header",
    "issuing_plant_code",
    "service_agent_description",
    "sla_met",
    "negotiated_value",
    "quantity",
    "service_agent_group",
    "customer_city",
    "cep",
    "created_on",
    "due_date",
    "finish_date",
    "billing_date",
]


# ============================================================
# AUXILIAR
# ============================================================

def _lista_unica_texto(series):
    """
    Transforma uma série em texto com valores únicos.

    Exemplo:

        ["Campinas", "Campinas", "Jundiaí"]

    vira:

        "Campinas | Jundiaí"
    """

    valores = (
        series
        .dropna()
        .astype(str)
        .str.strip()
    )

    valores = [
        valor
        for valor in valores
        if valor
        and valor.lower()
        not in {"nan", "none"}
    ]

    valores = sorted(set(valores))

    return " | ".join(valores)


# ============================================================
# CARREGAMENTO
# ============================================================

def carregar_historico():
    df = pd.read_parquet(
        C.PARQUET_PATH,
        columns=COLUNAS,
    )

    # --------------------------------------------------------
    # IDs
    # --------------------------------------------------------

    df["freight_id"] = (
        df["freight_id"]
        .astype(str)
        .str.strip()
    )

    df["pd_header"] = (
        df["pd_header"]
        .astype(str)
        .str.strip()
    )

    # --------------------------------------------------------
    # Planta
    # --------------------------------------------------------

    df["issuing_plant_code"] = (
        df["issuing_plant_code"]
        .astype(str)
        .str.strip()
    )

    # --------------------------------------------------------
    # Transportadora
    # --------------------------------------------------------

    df["service_agent_description"] = (
        df["service_agent_description"]
        .astype("string")
        .str.strip()
    )

    df = df[
        df["service_agent_description"]
        .notna()
    ].copy()

    df = df[
        df["service_agent_description"]
        .str.strip()
        .ne("")
    ].copy()

    # --------------------------------------------------------
    # Valores numéricos
    # --------------------------------------------------------

    df["negotiated_value"] = pd.to_numeric(
        df["negotiated_value"],
        errors="coerce",
    ).fillna(0)

    df["quantity"] = pd.to_numeric(
        df["quantity"],
        errors="coerce",
    ).fillna(0)

    # --------------------------------------------------------
    # SLA
    # --------------------------------------------------------

    df["sla_met"] = (
        df["sla_met"]
        .astype("boolean")
    )

    # --------------------------------------------------------
    # Datas
    # --------------------------------------------------------

    df["created_on"] = pd.to_datetime(
        df["created_on"],
        errors="coerce",
    )

    df["due_date"] = pd.to_datetime(
        df["due_date"],
        errors="coerce",
    )

    df["finish_date"] = pd.to_datetime(
        df["finish_date"],
        errors="coerce",
    )

    df["billing_date"] = pd.to_datetime(
        df["billing_date"],
        errors="coerce",
    )

    # --------------------------------------------------------
    # CEP
    # --------------------------------------------------------

    df["cep"] = (
        df["cep"]
        .fillna("")
        .astype(str)
        .str.replace(
            r"\D",
            "",
            regex=True,
        )
        .str.zfill(8)
    )

    # Corrige valores artificiais
    # gerados por NaN.

    df.loc[
        df["cep"].isin(
            [
                "00000000",
                "nan0000",
            ]
        ),
        "cep",
    ] = ""

    return df


# ============================================================
# JUNÇÃO DE TEXTOS
# ============================================================

def _juntar_textos(
    df,
    chaves,
    col,
):
    """
    Lista única 'a | b | c' por viagem.
    """

    t = (
        df[
            chaves + [col]
        ]
        .dropna(
            subset=[col]
        )
        .assign(
            **{
                col: lambda x:
                    x[col]
                    .astype(str)
                    .str.strip()
            }
        )
    )

    t = t[
        ~t[col]
        .str.lower()
        .isin(
            [
                "",
                "nan",
                "none",
            ]
        )
    ]

    t = (
        t
        .drop_duplicates()
        .sort_values(col)
    )

    return (
        t
        .groupby(chaves)[col]
        .agg(" | ".join)
        .rename(col)
    )


# ============================================================
# HISTÓRICO DETALHADO
# ============================================================

def preparar_historico_detalhado(df):
    """
    Mantém a granularidade original da base.

    Cada linha representa um registro original do parquet.

    Esta função NÃO consolida por freight_id.

    É a base utilizada para referência econômica.
    """

    if df.empty:
        return pd.DataFrame()

    detalhado = df.copy()

    # --------------------------------------------------------
    # Campos padronizados para o recomendacao.py
    # --------------------------------------------------------

    detalhado["valor_pago"] = pd.to_numeric(
        detalhado["negotiated_value"],
        errors="coerce",
    ).fillna(0)

    detalhado["peso_kg"] = pd.to_numeric(
        detalhado["quantity"],
        errors="coerce",
    )

    detalhado["sla_frete"] = (
        detalhado["sla_met"]
        .astype("boolean")
    )

    detalhado["data_fim"] = (
        detalhado["finish_date"]
    )

    detalhado["cep_destino"] = (
        detalhado["cep"]
    )

    detalhado["uf_destino"] = (
        pd.NA
    )

    # --------------------------------------------------------
    # Flags
    # --------------------------------------------------------

    detalhado["tem_valor"] = (
        detalhado["valor_pago"] > 0
    )

    detalhado["tem_finish_date"] = (
        detalhado["data_fim"].notna()
    )

    return detalhado


# ============================================================
# CONSOLIDAÇÃO
# ============================================================

def consolidar_fretes(df):

    if df.empty:
        return pd.DataFrame()

    chaves = [
        "freight_id",
        "issuing_plant_code",
        "service_agent_description",
    ]

    df = df.copy()

    # --------------------------------------------------------
    # CEP vazio vira NA
    # para o nunique nativo ignorar.
    # --------------------------------------------------------

    df["cep"] = (
        df["cep"]
        .replace("", pd.NA)
    )

    historico = (
        df
        .groupby(
            chaves,
            dropna=False,
        )
        .agg(
            quantidade=(
                "quantity",
                "sum",
            ),

            # Valor TOTAL da viagem.
            #
            # Continua sendo importante para análises
            # financeiras por freight_id.
            valor_pago=(
                "negotiated_value",
                "sum",
            ),

            linhas=(
                "freight_id",
                "size",
            ),

            qtd_pedidos=(
                "pd_header",
                "nunique",
            ),

            sla_linhas=(
                "sla_met",
                "count",
            ),

            sla_true=(
                "sla_met",
                "sum",
            ),

            data_criacao=(
                "created_on",
                "min",
            ),

            data_vencimento=(
                "due_date",
                "max",
            ),

            data_fim=(
                "finish_date",
                "max",
            ),

            data_faturamento=(
                "billing_date",
                "max",
            ),

            qtd_destinos=(
                "customer_city",
                "nunique",
            ),

            qtd_ceps=(
                "cep",
                "nunique",
            ),

            cidade_destino=(
                "customer_city",
                "first",
            ),

            cep_destino=(
                "cep",
                "first",
            ),
            service_agent_group=(     
                "service_agent_group",
                "first",
            ),
        )
        .reset_index()
    )

    # --------------------------------------------------------
    # Colunas de texto
    # --------------------------------------------------------

    for col, nome in [
        ("pd_header", "pedidos"),
        ("customer_city", "cidades_destino"),
        ("cep", "ceps_destino"),
    ]:

        textos = (
            _juntar_textos(
                df,
                chaves,
                col,
            )
            .rename(nome)
        )

        historico = historico.merge(
            textos,
            on=chaves,
            how="left",
        )

    historico["cep_destino"] = (
        historico["cep_destino"]
        .fillna("")
    )

    historico["ceps_destino"] = (
        historico["ceps_destino"]
        .fillna("")
    )

    historico["pedidos"] = (
        historico["pedidos"]
        .fillna("")
    )

    historico["cidades_destino"] = (
        historico["cidades_destino"]
        .fillna("")
    )

    # ========================================================
    # SLA
    # ========================================================

    historico["sla_percentual"] = (
        historico["sla_true"]
        / historico["sla_linhas"]
    )

    historico["sla_percentual"] = (
        historico["sla_percentual"]
        .where(
            historico["sla_linhas"] > 0
        )
    )

    # --------------------------------------------------------
    # SLA por frete
    #
    # True:
    #   todas as linhas conhecidas estão OK.
    #
    # False:
    #   existe pelo menos uma fora do prazo.
    #
    # NA:
    #   nenhum SLA conhecido.
    # --------------------------------------------------------

    historico["sla_frete"] = pd.Series(
        pd.NA,
        index=historico.index,
        dtype="boolean",
    )

    mascara_sla = (
        historico["sla_percentual"]
        .notna()
    )

    historico.loc[
        mascara_sla,
        "sla_frete",
    ] = (
        historico.loc[
            mascara_sla,
            "sla_percentual",
        ]
        >= 1.0
    )

    # ========================================================
    # FLAGS
    # ========================================================

    historico["tem_valor"] = (
        historico["valor_pago"] > 0
    )

    historico["tem_finish_date"] = (
        historico["data_fim"]
        .notna()
    )

    historico["tem_billing_date"] = (
        historico["data_faturamento"]
        .notna()
    )

    # --------------------------------------------------------
    # Conclusão
    # --------------------------------------------------------

    historico["concluido"] = (
        historico["data_fim"]
        .notna()
    )

    # --------------------------------------------------------
    # Múltiplos destinos
    # --------------------------------------------------------

    historico["rota_multipla"] = (
        (
            historico["qtd_destinos"]
            > 1
        )
        |
        (
            historico["qtd_ceps"]
            > 1
        )
    )

    # ========================================================
    # SEGURANÇA PARA ROTAS
    # ========================================================

    mascara_multipla = (
        historico["rota_multipla"]
    )

    historico.loc[
        mascara_multipla,
        "cidade_destino",
    ] = pd.NA

    historico.loc[
        mascara_multipla,
        "cep_destino",
    ] = ""

    return historico


# ============================================================
# CACHE — HISTÓRICO CONSOLIDADO
# ============================================================

def obter_historico_consolidado():

    origem = str(
        C.PARQUET_PATH
    )

    cache = (
        origem
        + ".consolidado.parquet"
    )

    if (
        os.path.exists(cache)
        and os.path.getmtime(cache)
        >= os.path.getmtime(origem)
    ):

        return pd.read_parquet(
            cache
        )

    df = carregar_historico()

    resultado = consolidar_fretes(
        df
    )

    resultado.to_parquet(
        cache,
        index=False,
    )

    return resultado


# ============================================================
# CACHE — HISTÓRICO DETALHADO
# ============================================================

def obter_historico_detalhado():

    origem = str(
        C.PARQUET_PATH
    )

    cache = (
        origem
        + ".detalhado.parquet"
    )

    if (
        os.path.exists(cache)
        and os.path.getmtime(cache)
        >= os.path.getmtime(origem)
    ):

        return pd.read_parquet(
            cache
        )

    df = carregar_historico()

    resultado = preparar_historico_detalhado(
        df
    )

    resultado.to_parquet(
        cache,
        index=False,
    )

    return resultado