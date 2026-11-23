
"""Preenchimento de CEPs a partir do histórico de fretes."""

import logging
import re
import time
import unicodedata

import pandas as pd

from analytics import config as C


log = logging.getLogger(__name__)

# Cache em memória: carregado apenas uma vez por processo.
_MAPAS = None


def _norm(valor):
    """Normaliza texto, removendo acentos e espaços."""
    if valor is None or pd.isna(valor):
        return ""

    texto = unicodedata.normalize("NFD", str(valor))
    texto = "".join(
        caractere
        for caractere in texto
        if unicodedata.category(caractere) != "Mn"
    )

    return texto.casefold().strip()


def _cep8(valor):
    """Normaliza CEP para oito dígitos."""
    if valor is None or pd.isna(valor):
        return None

    texto = str(valor).strip()

    if texto.endswith(".0"):
        texto = texto[:-2]

    digitos = re.sub(r"\D", "", texto)

    if len(digitos) == 7:
        digitos = "0" + digitos

    return digitos if len(digitos) == 8 else None


def _carregar_mapas():
    """
    Carrega o histórico uma única vez e constrói:
      - CEP mais frequente por cliente
      - CEP mais frequente por cidade + UF

    Evita executar Series.mode() individualmente
    para milhares de grupos.
    """
    global _MAPAS

    if _MAPAS is not None:
        return _MAPAS

    inicio_total = time.perf_counter()

    # 1. Leitura do Parquet
    inicio = time.perf_counter()

    df = pd.read_parquet(
        C.PARQUET_PATH,
        columns=[
            "customer_id",
            "customer_city",
            "customer_region",
            "cep",
        ],
    )

    print(
        f"[CEP HISTORICO] Leitura Parquet: "
        f"{time.perf_counter() - inicio:.2f}s",
        flush=True,
    )

    # 2. Normalização
    inicio = time.perf_counter()

    df["cep"] = df["cep"].map(_cep8)
    df = df.dropna(subset=["cep"]).copy()

    df["customer_id"] = (
        df["customer_id"]
        .astype("string")
        .str.strip()
    )

    df["uf"] = (
        df["customer_region"]
        .astype("string")
        .str.upper()
        .str.extract(r"([A-Z]{2})\s*$")[0]
    )

    df["cidade_n"] = df["customer_city"].map(_norm)

    print(
        f"[CEP HISTORICO] Normalização: "
        f"{time.perf_counter() - inicio:.2f}s",
        flush=True,
    )

    # 3. CEP mais frequente por cliente
    inicio = time.perf_counter()

    clientes = (
        df.dropna(subset=["customer_id"])
        .groupby(["customer_id", "cep"])
        .size()
        .reset_index(name="frequencia")
        .sort_values(
            ["customer_id", "frequencia", "cep"],
            ascending=[True, False, True],
        )
        .drop_duplicates(subset=["customer_id"])
    )

    por_cliente = dict(
        zip(clientes["customer_id"], clientes["cep"])
    )

    print(
        f"[CEP HISTORICO] Agrupamento clientes: "
        f"{time.perf_counter() - inicio:.2f}s",
        flush=True,
    )

    # 4. CEP mais frequente por cidade + UF
    inicio = time.perf_counter()

    cidades = (
        df.dropna(subset=["uf"])
        .groupby(["cidade_n", "uf", "cep"])
        .size()
        .reset_index(name="frequencia")
        .sort_values(
            ["cidade_n", "uf", "frequencia", "cep"],
            ascending=[True, True, False, True],
        )
        .drop_duplicates(subset=["cidade_n", "uf"])
    )

    por_cidade = {
        (cidade, uf): cep
        for cidade, uf, cep in zip(
            cidades["cidade_n"],
            cidades["uf"],
            cidades["cep"],
        )
    }

    print(
        f"[CEP HISTORICO] Agrupamento cidades: "
        f"{time.perf_counter() - inicio:.2f}s",
        flush=True,
    )

    _MAPAS = (por_cliente, por_cidade)

    print(
        f"[CEP HISTORICO] TOTAL: "
        f"{time.perf_counter() - inicio_total:.2f}s | "
        f"{len(por_cliente)} clientes | "
        f"{len(por_cidade)} cidades/UF",
        flush=True,
    )

    return _MAPAS


def preencher_cep(frete):
    """Preenche o CEP do frete utilizando o histórico."""

    # Preserva um CEP válido já existente.
    cep_existente = _cep8(frete.get("cep"))

    if cep_existente:
        frete["cep"] = cep_existente
        frete.setdefault("cep_origem", "arquivo")
        return

    frete["cep"] = ""
    frete["cep_origem"] = None

    # Mantém a regra atual para múltiplas paradas.
    if frete.get("tipo") == "Múltiplas paradas":
        return

    por_cliente, por_cidade = _carregar_mapas()

    cliente = str(frete.get("customer") or "").strip()

    # Prioridade 1: CEP histórico do cliente
    cep = por_cliente.get(cliente)
    origem = "cliente"

    # Prioridade 2: cidade + UF
    if not cep:
        cidade = _norm(frete.get("destino"))
        uf = str(frete.get("uf") or "").strip().upper()

        cep = por_cidade.get((cidade, uf))
        origem = "cidade_uf"

    if cep:
        frete["cep"] = cep
        frete["cep_origem"] = origem
