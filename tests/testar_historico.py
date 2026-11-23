from services.carrier_recommendation import _historico_viagens

h = _historico_viagens()
x = h[(h["issuing_plant_code"] == "1211") & (h["cep_destino"].str[:5] == "84145")]
print(len(x), "viagens", x["freight_id"].nunique(), "fretes")
print(x.groupby("service_agent_description")["freight_id"].nunique().sort_values(ascending=False))