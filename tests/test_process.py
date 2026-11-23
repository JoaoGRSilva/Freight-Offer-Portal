from services.freight_repository import conectar

with conectar() as conn:
    propostas = conn.execute("""
        SELECT
            id,
            frete_id,
            transportadora,
            valor,
            prazo_dias,
            criado_em
        FROM fretes_propostas
        ORDER BY id DESC
        LIMIT 10
    """).fetchall()

    for proposta in propostas:
        print(dict(proposta))