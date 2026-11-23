import analytics.recomendacao as R

V = R._filtrar_periodo(R._historico_viagens(), 12)
L = R._historico_linhas()
planta, cep, peso = "1211", "85410000", 18000   # <- ajuste o CEP

v = V[(V.issuing_plant_code == planta) & (V.cep_destino.str[:5] == cep[:5])
      & ~V.rota_multipla.fillna(False)]
faixa = v[v.peso_kg.between(peso * 0.6, peso * 1.6)]
print("viagens CEP5:", v.freight_id.nunique(), "| na faixa de peso:", faixa.freight_id.nunique())
print(faixa.peso_kg.describe().round(0))

l = L[L.freight_id.isin(faixa.freight_id) & (L.valor_pago > 0) & (L.peso_kg > 0)]
pv = l.groupby("freight_id")[["valor_pago", "peso_kg"]].sum()
pv["rs_100kg"] = pv.valor_pago / pv.peso_kg * 100
print(pv.rs_100kg.describe(percentiles=[.1, .5, .9]).round(1))
print(pv.valor_pago.describe(percentiles=[.1, .5, .9]).round(0))
print(pv.sort_values("rs_100kg").tail(5))