import pandas as pd
import numpy as np

# =====================================
# FUNÇÕES DE FORMATAÇÃO
# =====================================

def formatar_moeda(valor):
    """Formata valores numéricos no padrão monetário brasileiro."""
    if pd.isna(valor):
        return "R$ 0,00"

    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_dataframe_monetario(df, colunas):
    """Formata colunas monetárias apenas para exibição."""
    df_exibicao = df.copy()

    for coluna in colunas:
        if coluna in df_exibicao.columns:
            df_exibicao[coluna] = df_exibicao[coluna].apply(formatar_moeda)

    return df_exibicao


# =====================================
# LEITURA
# =====================================

df = pd.read_parquet(
    "data/processed/baseEA.parquet"
)

pd.set_option("display.float_format", "{:.2f}".format)


# =====================================
# SCHEMA
# =====================================

print("=" * 50)
print("COLUNAS")
print("=" * 50)

for coluna in df.columns:
    print(coluna)


# =====================================
# VISÃO GERAL
# =====================================

print("\n" + "=" * 50)
print("VISÃO GERAL")
print("=" * 50)

print(f"Linhas: {df.shape}")
print(f"Colunas: {df.shape[1]}")

print("\nTipos:")
print(df.dtypes)

print("\nTop 20 colunas com mais nulos:")
print(
    df.isnull()
      .sum()
      .sort_values(ascending=False)
      .head(20)
)


# =====================================
# KPIs GERAIS
# =====================================

print("\n" + "=" * 50)
print("KPIs")
print("=" * 50)

valor_total = df["negotiated_value"].sum()

print(
    f"Valor Total Negociado: "
    f"{formatar_moeda(valor_total)}"
)

print(
    f"Quantidade de Fretes: "
    f"{df['freight_id'].nunique():,}"
)

print(
    f"Quantidade de Clientes: "
    f"{df['customer_name'].nunique():,}"
)

print(
    f"Lead Time Médio: "
    f"{df['lead_time_days'].mean():.2f} dias"
)

if "sla_met" in df.columns:
    print(
        f"SLA Médio: "
        f"{df['sla_met'].mean() * 100:.2f}%"
    )


# =====================================
# TOP CLIENTES
# =====================================

print("\n" + "=" * 50)
print("TOP CLIENTES POR VALOR")
print("=" * 50)

top_clientes = (
    df.groupby("customer_name")["negotiated_value"]
      .sum()
      .sort_values(ascending=False)
      .head(10)
)

print(
    top_clientes
    .apply(formatar_moeda)
)


# =====================================
# CLIENTES - VISÃO GERENCIAL
# =====================================

print("\n" + "=" * 50)
print("CLIENTES")
print("=" * 50)

clientes = (
    df.groupby("customer_name")
      .agg(
          negotiated_value=("negotiated_value", "sum"),
          freight_count=("freight_id", "nunique"),
          sla=("sla_met", "mean"),
          lead_time=("lead_time_days", "mean")
      )
      .sort_values(
          "negotiated_value",
          ascending=False
      )
)

print(
    formatar_dataframe_monetario(
        clientes.head(20),
        ["negotiated_value"]
    )
)


# =====================================
# REGIÕES
# =====================================

print("\n" + "=" * 50)
print("REGIÕES")
print("=" * 50)

if "customer_region" in df.columns:

    regioes = (
        df.groupby("customer_region")
          .agg(
              negotiated_value=("negotiated_value", "sum"),
              freight_count=("freight_id", "nunique"),
              clientes=("customer_name", "nunique")
          )
          .sort_values(
              "negotiated_value",
              ascending=False
          )
    )

    print(
        formatar_dataframe_monetario(
            regioes,
            ["negotiated_value"]
        )
    )


# =====================================
# TRANSPORTADORAS
# =====================================

transportadoras = (
    df.groupby("service_agent_description")
      .agg(
          negotiated_value=("negotiated_value", "sum"),
          freight_count=("freight_id", "nunique")
      )
      .sort_values("negotiated_value", ascending=False)
)

print("\n" + "=" * 50)
print("TRANSPORTADORAS")
print("=" * 50)
print(formatar_dataframe_monetario(
    transportadoras.head(20),
    ["negotiated_value"]
))


# =====================================
# EVOLUÇÃO TEMPORAL
# =====================================

print("\n" + "=" * 50)
print("EVOLUÇÃO MENSAL")
print("=" * 50)

if "year_month" in df.columns:

    mensal = (
        df.groupby("year_month")
          .agg(
              negotiated_value=("negotiated_value", "sum"),
              freight_count=("freight_id", "nunique")
          )
          .sort_index()
    )

    print(
        formatar_dataframe_monetario(
            mensal,
            ["negotiated_value"]
        )
    )


# =====================================
# DISTRIBUIÇÃO DE VALORES
# =====================================

print("\n" + "=" * 50)
print("DESCRITIVAS DE VALOR")
print("=" * 50)

print(
    df["negotiated_value"]
      .describe()
      .apply(formatar_moeda)
)


# =====================================
# SLA POR REGIÃO
# =====================================

if (
    "customer_region" in df.columns
    and "sla_met" in df.columns
):

    print("\n" + "=" * 50)
    print("PIOR SLA POR REGIÃO")
    print("=" * 50)

    print(
        df.groupby("customer_region")["sla_met"]
          .mean()
          .sort_values()
          .head(10)
    )


# =====================================
# ATRASOS
# =====================================

print("\n" + "=" * 50)
print("ATRASOS")
print("=" * 50)

df["delay_days"] = (
    df["finish_date"] - df["due_date"]
).dt.days

df["delay_days"] = (
    df["delay_days"]
      .where(df["delay_days"] > 0)
)

print(
    df["delay_days"]
      .describe()
)


# =====================================
# CORRELAÇÃO
# =====================================

print("\n" + "=" * 50)
print("CORRELAÇÃO")
print("=" * 50)

num_cols = [
    "lead_time_days",
    "negotiated_value",
    "delay_days",
    "quantity",
    "unit_value"
]

num_cols = [
    col for col in num_cols
    if col in df.columns
]

corr = df[num_cols].corr(
    numeric_only=True
)

print(corr)


# =====================================
# DUPLICIDADES
# =====================================

print("\n" + "=" * 50)
print("FRETES DUPLICADOS")
print("=" * 50)

duplicados = (
    df.groupby("freight_id")
      .size()
      .sort_values(ascending=False)
)

print(
    duplicados[duplicados > 1]
    .head(20)
)


# =====================================
# ORIGEM DOS FRETES
# =====================================

if "freight_source" in df.columns:

    print("\n" + "=" * 50)
    print("FREIGHT SOURCE")
    print("=" * 50)

    print(
        df["freight_source"]
        .value_counts(dropna=False)
    )


# =====================================
# EMPRESA X AUTÔNOMO
# =====================================

df["carrier_type"] = np.where(
    df["service_agent_group_code"] == "VBR6",
    "Empresa",
    np.where(
        df["service_agent_group_code"] == "VBR7",
        "Autônomo",
        "Outros"
    )
)

print("\n" + "=" * 50)
print("EMPRESA X AUTÔNOMO")
print("=" * 50)

empresa_autonomo = (
    df.groupby("carrier_type")
      .agg(
          negotiated_value=("negotiated_value", "sum"),
          freight_count=("freight_id", "nunique"),
          sla=("sla_met", "mean"),
          lead_time=("lead_time_days", "mean")
      )
      .sort_values(
          "negotiated_value",
          ascending=False
      )
)

print(
    formatar_dataframe_monetario(
        empresa_autonomo,
        ["negotiated_value"]
    )
)


print("\n" + "=" * 50)
print("PARTICIPAÇÃO")
print("=" * 50)

total = df["negotiated_value"].sum()

participacao = (
    df.groupby("carrier_type")["negotiated_value"]
      .sum()
      .div(total)
      .mul(100)
      .round(2)
)

print(participacao)


# =====================================
# TOP TRANSPORTADORAS
# =====================================

print("\n" + "=" * 50)
print("TOP TRANSPORTADORAS")
print("=" * 50)

top_transportadoras = (
    df.groupby("service_agent_description")
      .agg(
          negotiated_value=("negotiated_value", "sum"),
          freight_count=("freight_id", "nunique"),
          sla=("sla_met", "mean")
      )
      .sort_values(
          "negotiated_value",
          ascending=False
      )
)

print(
    formatar_dataframe_monetario(
        top_transportadoras.head(20),
        ["negotiated_value"]
    )
)


# =====================================
# TOP EMPRESAS
# =====================================

print("\n" + "=" * 50)
print("TOP EMPRESAS")
print("=" * 50)

top_empresas = (
    df[df["carrier_type"] == "Empresa"]
    .groupby("service_agent_description")
    .agg(
        negotiated_value=("negotiated_value", "sum"),
        freight_count=("freight_id", "nunique")
    )
    .sort_values(
        "negotiated_value",
        ascending=False
    )
)

print(
    formatar_dataframe_monetario(
        top_empresas.head(20),
        ["negotiated_value"]
    )
)


# =====================================
# TOP AUTÔNOMOS
# =====================================

print("\n" + "=" * 50)
print("TOP AUTÔNOMOS")
print("=" * 50)

top_autonomos = (
    df[df["carrier_type"] == "Autônomo"]
    .groupby("service_agent_description")
    .agg(
        negotiated_value=("negotiated_value", "sum"),
        freight_count=("freight_id", "nunique")
    )
    .sort_values(
        "negotiated_value",
        ascending=False
    )
)

print(
    formatar_dataframe_monetario(
        top_autonomos.head(20),
        ["negotiated_value"]
    )
)


# =====================================
# MELHOR TRANSPORTADORA POR REGIÃO
# =====================================

print("\n" + "=" * 50)
print("MELHOR TRANSPORTADORA POR REGIÃO")
print("=" * 50)

regiao_transportadora = (
    df.groupby(
        [
            "customer_region",
            "service_agent_description"
        ]
    )
    .agg(
        negotiated_value=("negotiated_value", "sum"),
        freight_count=("freight_id", "nunique"),
        on_time=("on_time", "mean"),
        lead_time=("lead_time_days", "mean")
    )
    .reset_index()
)

desempenho_transportadoras = (
    df.groupby(
        [
            "customer_region",
            "service_agent_description"
        ]
    )
    .agg(
        negotiated_value=("negotiated_value", "sum"),
        freight_count=("freight_id", "nunique"),
        on_time=("on_time", "mean"),
        lead_time=("lead_time_days", "mean")
    )
    .reset_index()
)

top_regiao = (
    regiao_transportadora
    .sort_values(
        ["customer_region", "negotiated_value"],
        ascending=[True, False]
    )
    .groupby("customer_region")
    .head(1)
)

print(
    formatar_dataframe_monetario(
        top_regiao.sort_values(
            "negotiated_value",
            ascending=False
        ),
        ["negotiated_value"]
    )
)


# =====================================
# EMPRESA X AUTÔNOMO POR REGIÃO
# =====================================

print("\n" + "=" * 50)
print("EMPRESA X AUTÔNOMO POR REGIÃO")
print("=" * 50)

regiao_tipo = (
    df.groupby(
        [
            "customer_region",
            "carrier_type"
        ]
    )
    .agg(
        negotiated_value=("negotiated_value", "sum"),
        freight_count=("freight_id", "nunique")
    )
    .reset_index()
)

print(
    formatar_dataframe_monetario(
        regiao_tipo,
        ["negotiated_value"]
    )
)


# =====================================
# SLA EMPRESA X AUTÔNOMO
# =====================================

print("\n" + "=" * 50)
print("SLA EMPRESA X AUTÔNOMO")
print("=" * 50)

sla_tipo = (
    df.groupby("carrier_type")
      .agg(
          sla=("sla_met", "mean"),
          lead_time=("lead_time_days", "mean"),
          fretes=("freight_id", "nunique")
      )
)

print(sla_tipo)


# =====================================
# DEPENDÊNCIA DE TRANSPORTADORA
# =====================================

print("\n" + "=" * 50)
print("DEPENDÊNCIA DE TRANSPORTADORA")
print("=" * 50)

dependencia = (
    df.groupby(
        [
            "customer_region",
            "service_agent_description"
        ]
    )["negotiated_value"]
    .sum()
    .reset_index()
)

dependencia["regional_total"] = (
    dependencia.groupby("customer_region")
               ["negotiated_value"]
               .transform("sum")
)

dependencia["share"] = (
    dependencia["negotiated_value"]
    /
    dependencia["regional_total"]
    * 100
)

lideres = (
    dependencia
    .sort_values(
        ["customer_region", "share"],
        ascending=False
    )
    .groupby("customer_region")
    .head(1)
)

print(
    lideres[
        [
            "customer_region",
            "service_agent_description",
            "share"
        ]
    ]
)


import pandas as pd
import numpy as np


# =====================================
# FUNÇÕES DE FORMATAÇÃO
# =====================================

def formatar_moeda(valor):
    """Formata valores numéricos no padrão monetário brasileiro."""
    if pd.isna(valor):
        return "R$ 0,00"

    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_dataframe_monetario(df, colunas):
    """Formata colunas monetárias apenas para exibição."""
    df_exibicao = df.copy()

    for coluna in colunas:
        if coluna in df_exibicao.columns:
            df_exibicao[coluna] = df_exibicao[coluna].apply(formatar_moeda)

    return df_exibicao


# =====================================
# LEITURA
# =====================================

df = pd.read_parquet(
    "data/processed/baseEA.parquet"
)

pd.set_option("display.float_format", "{:.2f}".format)


# =====================================
# SCHEMA
# =====================================

print("=" * 50)
print("COLUNAS")
print("=" * 50)

for coluna in df.columns:
    print(coluna)


# =====================================
# VISÃO GERAL
# =====================================

print("\n" + "=" * 50)
print("VISÃO GERAL")
print("=" * 50)

print(f"Linhas: {df.shape}")
print(f"Colunas: {df.shape[1]}")

print("\nTipos:")
print(df.dtypes)

print("\nTop 20 colunas com mais nulos:")
print(
    df.isnull()
      .sum()
      .sort_values(ascending=False)
      .head(20)
)


# =====================================
# KPIs GERAIS
# =====================================

print("\n" + "=" * 50)
print("KPIs")
print("=" * 50)

valor_total = df["negotiated_value"].sum()

print(
    f"Valor Total Negociado: "
    f"{formatar_moeda(valor_total)}"
)

print(
    f"Quantidade de Fretes: "
    f"{df['freight_id'].nunique():,}"
)

print(
    f"Quantidade de Clientes: "
    f"{df['customer_name'].nunique():,}"
)

print(
    f"Lead Time Médio: "
    f"{df['lead_time_days'].mean():.2f} dias"
)

if "sla_met" in df.columns:
    print(
        f"SLA Médio: "
        f"{df['sla_met'].mean() * 100:.2f}%"
    )


# =====================================
# TOP CLIENTES
# =====================================

print("\n" + "=" * 50)
print("TOP CLIENTES POR VALOR")
print("=" * 50)

top_clientes = (
    df.groupby("customer_name")["negotiated_value"]
      .sum()
      .sort_values(ascending=False)
      .head(10)
)

print(
    top_clientes
    .apply(formatar_moeda)
)


# =====================================
# CLIENTES - VISÃO GERENCIAL
# =====================================

print("\n" + "=" * 50)
print("CLIENTES")
print("=" * 50)

clientes = (
    df.groupby("customer_name")
      .agg(
          negotiated_value=("negotiated_value", "sum"),
          freight_count=("freight_id", "nunique"),
          sla=("sla_met", "mean"),
          lead_time=("lead_time_days", "mean")
      )
      .sort_values(
          "negotiated_value",
          ascending=False
      )
)

print(
    formatar_dataframe_monetario(
        clientes.head(20),
        ["negotiated_value"]
    )
)


# =====================================
# REGIÕES
# =====================================

print("\n" + "=" * 50)
print("REGIÕES")
print("=" * 50)

if "customer_region" in df.columns:

    regioes = (
        df.groupby("customer_region")
          .agg(
              negotiated_value=("negotiated_value", "sum"),
              freight_count=("freight_id", "nunique"),
              clientes=("customer_name", "nunique")
          )
          .sort_values(
              "negotiated_value",
              ascending=False
          )
    )

    print(
        formatar_dataframe_monetario(
            regioes,
            ["negotiated_value"]
        )
    )


# =====================================
# TRANSPORTADORAS
# =====================================

transportadoras = (
    df.groupby("service_agent_description")
      .agg(
          negotiated_value=("negotiated_value", "sum"),
          freight_count=("freight_id", "nunique")
      )
      .sort_values("negotiated_value", ascending=False)
)

print("\n" + "=" * 50)
print("TRANSPORTADORAS")
print("=" * 50)
print(formatar_dataframe_monetario(
    transportadoras.head(20),
    ["negotiated_value"]
))


# =====================================
# EVOLUÇÃO TEMPORAL
# =====================================

print("\n" + "=" * 50)
print("EVOLUÇÃO MENSAL")
print("=" * 50)

if "year_month" in df.columns:

    mensal = (
        df.groupby("year_month")
          .agg(
              negotiated_value=("negotiated_value", "sum"),
              freight_count=("freight_id", "nunique")
          )
          .sort_index()
    )

    print(
        formatar_dataframe_monetario(
            mensal,
            ["negotiated_value"]
        )
    )


# =====================================
# DISTRIBUIÇÃO DE VALORES
# =====================================

print("\n" + "=" * 50)
print("DESCRITIVAS DE VALOR")
print("=" * 50)

print(
    df["negotiated_value"]
      .describe()
      .apply(formatar_moeda)
)


# =====================================
# SLA POR REGIÃO
# =====================================

if (
    "customer_region" in df.columns
    and "sla_met" in df.columns
):

    print("\n" + "=" * 50)
    print("PIOR SLA POR REGIÃO")
    print("=" * 50)

    print(
        df.groupby("customer_region")["sla_met"]
          .mean()
          .sort_values()
          .head(10)
    )


# =====================================
# ATRASOS
# =====================================

print("\n" + "=" * 50)
print("ATRASOS")
print("=" * 50)

df["delay_days"] = (
    df["finish_date"] - df["due_date"]
).dt.days

df["delay_days"] = (
    df["delay_days"]
      .where(df["delay_days"] > 0)
)

print(
    df["delay_days"]
      .describe()
)


# =====================================
# CORRELAÇÃO
# =====================================

print("\n" + "=" * 50)
print("CORRELAÇÃO")
print("=" * 50)

num_cols = [
    "lead_time_days",
    "negotiated_value",
    "delay_days",
    "quantity",
    "unit_value"
]

num_cols = [
    col for col in num_cols
    if col in df.columns
]

corr = df[num_cols].corr(
    numeric_only=True
)

print(corr)


# =====================================
# DUPLICIDADES
# =====================================

print("\n" + "=" * 50)
print("FRETES DUPLICADOS")
print("=" * 50)

duplicados = (
    df.groupby("freight_id")
      .size()
      .sort_values(ascending=False)
)

print(
    duplicados[duplicados > 1]
    .head(20)
)


# =====================================
# ORIGEM DOS FRETES
# =====================================

if "freight_source" in df.columns:

    print("\n" + "=" * 50)
    print("FREIGHT SOURCE")
    print("=" * 50)

    print(
        df["freight_source"]
        .value_counts(dropna=False)
    )


# =====================================
# EMPRESA X AUTÔNOMO
# =====================================

df["carrier_type"] = np.where(
    df["service_agent_group_code"] == "VBR6",
    "Empresa",
    np.where(
        df["service_agent_group_code"] == "VBR7",
        "Autônomo",
        "Outros"
    )
)

print("\n" + "=" * 50)
print("EMPRESA X AUTÔNOMO")
print("=" * 50)

empresa_autonomo = (
    df.groupby("carrier_type")
      .agg(
          negotiated_value=("negotiated_value", "sum"),
          freight_count=("freight_id", "nunique"),
          sla=("sla_met", "mean"),
          lead_time=("lead_time_days", "mean")
      )
      .sort_values(
          "negotiated_value",
          ascending=False
      )
)

print(
    formatar_dataframe_monetario(
        empresa_autonomo,
        ["negotiated_value"]
    )
)


print("\n" + "=" * 50)
print("PARTICIPAÇÃO")
print("=" * 50)

total = df["negotiated_value"].sum()

participacao = (
    df.groupby("carrier_type")["negotiated_value"]
      .sum()
      .div(total)
      .mul(100)
      .round(2)
)

print(participacao)


# =====================================
# TOP TRANSPORTADORAS
# =====================================

print("\n" + "=" * 50)
print("TOP TRANSPORTADORAS")
print("=" * 50)

top_transportadoras = (
    df.groupby("service_agent_description")
      .agg(
          negotiated_value=("negotiated_value", "sum"),
          freight_count=("freight_id", "nunique"),
          sla=("sla_met", "mean")
      )
      .sort_values(
          "negotiated_value",
          ascending=False
      )
)

print(
    formatar_dataframe_monetario(
        top_transportadoras.head(20),
        ["negotiated_value"]
    )
)


# =====================================
# TOP EMPRESAS
# =====================================

print("\n" + "=" * 50)
print("TOP EMPRESAS")
print("=" * 50)

top_empresas = (
    df[df["carrier_type"] == "Empresa"]
    .groupby("service_agent_description")
    .agg(
        negotiated_value=("negotiated_value", "sum"),
        freight_count=("freight_id", "nunique")
    )
    .sort_values(
        "negotiated_value",
        ascending=False
    )
)

print(
    formatar_dataframe_monetario(
        top_empresas.head(20),
        ["negotiated_value"]
    )
)


# =====================================
# TOP AUTÔNOMOS
# =====================================

print("\n" + "=" * 50)
print("TOP AUTÔNOMOS")
print("=" * 50)

top_autonomos = (
    df[df["carrier_type"] == "Autônomo"]
    .groupby("service_agent_description")
    .agg(
        negotiated_value=("negotiated_value", "sum"),
        freight_count=("freight_id", "nunique")
    )
    .sort_values(
        "negotiated_value",
        ascending=False
    )
)

print(
    formatar_dataframe_monetario(
        top_autonomos.head(20),
        ["negotiated_value"]
    )
)


# =====================================
# MELHOR TRANSPORTADORA POR REGIÃO
# =====================================

print("\n" + "=" * 50)
print("MELHOR TRANSPORTADORA POR REGIÃO")
print("=" * 50)

regiao_transportadora = (
    df.groupby(
        [
            "customer_region",
            "service_agent_description"
        ]
    )
    .agg(
        negotiated_value=("negotiated_value", "sum"),
        freight_count=("freight_id", "nunique"),
        on_time=("on_time", "mean"),
        lead_time=("lead_time_days", "mean")
    )
    .reset_index()
)

desempenho_transportadoras = (
    df.groupby(
        [
            "customer_region",
            "service_agent_description"
        ]
    )
    .agg(
        negotiated_value=("negotiated_value", "sum"),
        freight_count=("freight_id", "nunique"),
        on_time=("on_time", "mean"),
        lead_time=("lead_time_days", "mean")
    )
    .reset_index()
)

top_regiao = (
    regiao_transportadora
    .sort_values(
        ["customer_region", "negotiated_value"],
        ascending=[True, False]
    )
    .groupby("customer_region")
    .head(1)
)

print(
    formatar_dataframe_monetario(
        top_regiao.sort_values(
            "negotiated_value",
            ascending=False
        ),
        ["negotiated_value"]
    )
)


# =====================================
# EMPRESA X AUTÔNOMO POR REGIÃO
# =====================================

print("\n" + "=" * 50)
print("EMPRESA X AUTÔNOMO POR REGIÃO")
print("=" * 50)

regiao_tipo = (
    df.groupby(
        [
            "customer_region",
            "carrier_type"
        ]
    )
    .agg(
        negotiated_value=("negotiated_value", "sum"),
        freight_count=("freight_id", "nunique")
    )
    .reset_index()
)

print(
    formatar_dataframe_monetario(
        regiao_tipo,
        ["negotiated_value"]
    )
)


# =====================================
# SLA EMPRESA X AUTÔNOMO
# =====================================

print("\n" + "=" * 50)
print("SLA EMPRESA X AUTÔNOMO")
print("=" * 50)

sla_tipo = (
    df.groupby("carrier_type")
      .agg(
          sla=("sla_met", "mean"),
          lead_time=("lead_time_days", "mean"),
          fretes=("freight_id", "nunique")
      )
)

print(sla_tipo)


# =====================================
# INVESTIGAÇÃO DE FREIGHT_ID
# =====================================

print("\n" + "=" * 50)
print("INVESTIGAÇÃO DE FREIGHT_ID")
print("=" * 50)

freight_id_teste = "3123674442"

frete = df[
    df["freight_id"].astype(str).str.strip() == freight_id_teste
].copy()

print(f"\nFreight ID analisado: {freight_id_teste}")
print(f"Linhas: {len(frete)}")

print(
    f"Quantidade total: "
    f"{frete['quantity'].sum():,.2f}"
)

print(
    f"Valor total: "
    f"{formatar_moeda(frete['negotiated_value'].sum())}"
)

print("\nValores diferentes:")
print(
    frete["negotiated_value"]
    .value_counts()
    .head(20)
)

print("\nSLA:")
print(
    frete["sla_met"]
    .value_counts()
)

print("\nDatas:")
print(
    frete["billing_date"]
    .dropna()
    .unique()
)


# =====================================
# SLA DENTRO DO FREIGHT_ID
# =====================================

print("\n" + "=" * 50)
print("DETALHE DO SLA")
print("=" * 50)

print(
    frete.groupby("sla_met").agg(
        linhas=("freight_id", "size"),
        quantidade=("quantity", "sum"),
        valor=("negotiated_value", "sum")
    )
)


# =====================================
# LINHAS COM SLA TRUE
# =====================================

print("\n" + "=" * 50)
print("LINHAS COM SLA TRUE")
print("=" * 50)

print(
    frete[
        frete["sla_met"] == True
    ][
        [
            "freight_id",
            "quantity",
            "negotiated_value",
            "sla_met",
            "service_agent_description",
            "billing_date"
        ]
    ].to_string(index=False)
)


jcrm = historico_consolidado[
    historico_consolidado["service_agent_description"]
    == "JCRM TRANSP E LOGISTICA"
]

print("Qtd fretes")
print(len(jcrm))

print("SLA Frete")
print(jcrm["sla_frete"].mean())


# ============================================================
# 7. FIM
# ============================================================

print("\n" + "=" * 70)
print("FIM DO DIAGNÓSTICO")
print("=" * 70)


print("\nEDA FINALIZADA")