import pandas as pd


def formatar_moeda(valor):

    if pd.isna(valor):
        return "R$ 0,00"

    return (
        f"R$ {valor:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )



def obter_kpis():

    df = pd.read_parquet(
        "data/processed/baseEA.parquet"
    )

    savings_total = df["savings_value"].sum() * -1

    kpis = {
        "fretes":
            f"{df['freight_id'].nunique():,}".replace(",", "."),

        "valor_negociado":
            formatar_moeda(
                df["negotiated_value"].sum()
            ),

        "savings":
            formatar_moeda(
                abs(savings_total)
            ),

        "savings_positivo": (
            savings_total < 0 
        ),

        "lead_time":
            f"{df["lead_time_days"].mean():.1f} dias",

        "sla_medio":
            f"{df['sla_met'].mean() * 100:.2f}%"
    }

    return kpis


def obter_evolucao_mensal():

    df = pd.read_parquet(
        "data/processed/baseEA.parquet"
    )

    df_evolucao = df[
        df["negotiated_value"].notna()
        &
        (df["negotiated_value"] > 0)
    ].copy()

    evolucao = (
        df_evolucao
        .groupby(
            "year_month",
            as_index=False
        )
        .agg(
            negotiated_value=(
                "negotiated_value",
                "sum"
            ),

            freight_count=(
                "freight_id",
                "nunique"
            )
        )
    )

    return evolucao


def obter_top_transportadoras():

    df = pd.read_parquet(
        "data/processed/baseEA.parquet"
    )

    top_transportadoras = (
        df.groupby(
            "service_agent_description"
        )
        .agg(
            negotiated_value=(
                "negotiated_value",
                "sum"
            ),

            freight_count=(
                "freight_id",
                "nunique"
            ),

            sla=(
                "sla_met",
                "mean"
            )
        )
        .sort_values(
            "negotiated_value",
            ascending=False
        )
    )

    return top_transportadoras.head(10)


def obter_performance_estado():

    df = pd.read_parquet(
        "data/processed/baseEA.parquet"
    )

    estados = (
        df.groupby(
            "customer_region"
        )
        .agg(
            negotiated_value=(
                "negotiated_value",
                "sum"
            ),

            freight_count=(
                "freight_id",
                "nunique"
            ),

            clientes=(
                "customer_name",
                "nunique"
            ),
            sla = (
                "sla_met",
                "mean"
            )
        )
        .reset_index()
    )

    return estados