"""Custos de referência. Calcula ANTT e mercado."""

from analytics.truck import antt, consumo_tabela, preco_gasolina_max


def calcular_custos(
    uf: str,
    peso_kg: float,
    eixos: int,
    categoria: str,
    trechos: list[dict]
) -> dict:

    # =========================
    # DADOS ANTT
    # =========================

    dados_antt = antt[eixos]

    ccd = dados_antt["ccd"]
    cc = dados_antt["cc"]

    # =========================
    # PREÇO DO COMBUSTÍVEL
    # =========================

    preco_litro = preco_gasolina_max[uf]

    # =========================
    # DISTÂNCIA E COMBUSTÍVEL
    # =========================

    distancia_total = 0
    litros_totais = 0

    for trecho in trechos:

        distancia = trecho["distancia_km"]
        pavimento = trecho["pavimento"]

        consumo = consumo_tabela[
            (categoria, eixos, pavimento)
        ]

        litros = distancia / consumo

        distancia_total += distancia
        litros_totais += litros

    custo_combustivel = preco_litro * litros_totais

    # =========================
    # VALORES DE REFERÊNCIA
    # =========================

    valor_antt = ccd * distancia_total + cc

    valor_mercado = custo_combustivel / 0.415

    return {
        "antt": valor_antt,
        "mercado": valor_mercado,
        "distancia_total_km": distancia_total,
        "litros_totais": litros_totais,
        "custo_combustivel": custo_combustivel,
    }