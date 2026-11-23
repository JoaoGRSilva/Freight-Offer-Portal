"""Leitura e validação do arquivo de fretes enviado pelo usuário (xlsx/csv).

Colunas obrigatórias: pedido, planta, cep_destino, peso_kg
"""
import pandas as pd

from analytics.plants import get_planta
from services.postal_code import normalizar_cep

OBRIGATORIAS = ["pedido", "planta", "cep_destino", "peso_kg"]


def _peso(valor) -> float:
    s = str(valor).strip()
    if "," in s:  # formato BR: 1.750,5
        s = s.replace(".", "").replace(",", ".")
    return float(s)


def ler_arquivo(arquivo) -> tuple[list[dict], list[str]]:
    """Retorna (linhas válidas, lista de erros por linha)."""
    nome = (getattr(arquivo, "filename", "") or "").lower()
    if nome.endswith(".csv"):
        df = pd.read_csv(arquivo, dtype=str, sep=None, engine="python")
    else:
        df = pd.read_excel(arquivo, dtype=str)
    df.columns = [str(c).strip().lower() for c in df.columns]

    faltando = [c for c in OBRIGATORIAS if c not in df.columns]
    if faltando:
        raise ValueError("Colunas ausentes no arquivo: " + ", ".join(faltando))

    linhas, erros = [], []
    for i, r in df.iterrows():
        n = i + 2  # número da linha no Excel (cabeçalho = 1)
        planta = get_planta(r["planta"])
        cep = normalizar_cep(r["cep_destino"])
        try:
            peso = _peso(r["peso_kg"])
        except ValueError:
            peso = None
        if not planta:
            erros.append(f"Linha {n}: planta '{r['planta']}' não encontrada")
        elif not cep:
            erros.append(f"Linha {n}: CEP '{r['cep_destino']}' inválido")
        elif not peso or peso <= 0:
            erros.append(f"Linha {n}: peso inválido")
        else:
            linhas.append({"pedido": str(r["pedido"]).strip(), "planta": planta,
                           "cep": cep, "peso_kg": peso})
    return linhas, erros