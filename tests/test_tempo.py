from analytics.history import obter_historico_consolidado
print(obter_historico_consolidado()["service_agent_group"].value_counts(dropna=False))