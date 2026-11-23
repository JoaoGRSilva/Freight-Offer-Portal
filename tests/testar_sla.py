
from analytics.sla import calcular_sla_transportadoras

sla = calcular_sla_transportadoras()

print("\nSLA GERAL POR TRANSPORTADORA\n")

print(
    sla.head(20).to_string(index=False)
)

print("\nSLA DE UMA TRANSPORTADORA\n")

nome = "TRANSPORTADORA SANA LTDA"

resultado = sla[
    sla["service_agent_description"] == nome
]

if not resultado.empty:
    print(resultado.to_string(index=False))
else:
    print(f"Transportadora não encontrada: {nome}")