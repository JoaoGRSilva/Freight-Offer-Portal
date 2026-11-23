"""Leitura e validação de fretes (CSV/XLSX), preservando clientes por pedido.

Os nomes dos clientes são enriquecidos pelo histórico Parquet, quando configurado.
"""
import logging
import math
import os
from analytics.config import PARQUET_PATH
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
from analytics.plants import get_planta

log = logging.getLogger(__name__)

OBRIGATORIAS = [
    "Pedido / Ord. Venda", "Customer", "Cidade Destino", "Data do Frete",
    "Quantidade", "Nº. Frete", "Motorista", "Local Transferência",
]
RENAME_COLS = {
    "Pedido / Ord. Venda": "pedido", "Customer": "customer",
    "Material": "material", "Descrição do Material": "material_desc",
    "Cidade Destino": "cidade_destino", "Data do Frete": "data_frete",
    "Quantidade": "peso_kg", "Nº. Frete": "num_frete",
    "Motorista": "motorista", "Usuário": "usuario",
    "Local Transferência": "local_transbordo",
}
TEXTO_COLS = [
    "pedido", "customer", "num_frete", "motorista", "cidade_destino",
    "local_transbordo", "usuario", "material", "material_desc",
]


def _peso(valor) -> float | None:
    if valor is None or pd.isna(valor):
        return None
    s = str(valor).strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        peso = float(s)
    except (TypeError, ValueError):
        return None
    return peso if math.isfinite(peso) and peso > 0 else None


def _limpar_texto(serie: pd.Series) -> pd.Series:
    s = serie.astype("string").str.strip()
    return s.mask(s.isin(["", "nan", "None", "<NA>"]))


def _identificador(valor) -> str | None:
    """Mantém IDs como texto; remove apenas o sufixo .0 de conversões numéricas."""
    if valor is None or pd.isna(valor):
        return None
    texto = str(valor).strip()
    if not texto or texto.lower() in {"nan", "none", "<na>"}:
        return None
    return re.sub(r"\.0+$", "", texto) if re.fullmatch(r"\d+\.0+", texto) else texto


def _chave_cliente(valor) -> str | None:
    identificador = _identificador(valor)
    return identificador.upper() if identificador else None


@lru_cache(maxsize=4)
def _mapa_clientes_parquet(caminho: str, modificado_ns: int) -> dict[str, str]:
    """Lê apenas as duas colunas necessárias e reutiliza o resultado."""
    historico = pd.read_parquet(
        caminho, columns=["customer_id", "customer_name"]
    ).dropna(subset=["customer_id", "customer_name"])

    mapa = {}
    for customer_id, customer_name in historico.itertuples(index=False, name=None):
        chave = _chave_cliente(customer_id)
        nome = " ".join(str(customer_name).split())
        if chave and nome and nome.lower() not in {"nan", "none", "<na>"}:
            mapa.setdefault(chave, nome)
    return mapa


def _obter_mapa_clientes() -> dict[str, str]:
    """Defina HISTORICO_PARQUET com o caminho real do Parquet do projeto."""
    caminho_configurado = PARQUET_PATH
    if not caminho_configurado:
        log.warning(
            "HISTORICO_PARQUET não configurado; nomes de clientes não serão enriquecidos."
        )
        return {}

    caminho = Path(caminho_configurado)
    if not caminho.is_file():
        log.warning("Histórico Parquet não encontrado: %s", caminho)
        return {}

    try:
        return _mapa_clientes_parquet(str(caminho.resolve()), caminho.stat().st_mtime_ns)
    except Exception:
        log.exception("Falha ao ler customer_id/customer_name do histórico: %s", caminho)
        return {}


def _separar_cidade_uf(serie: pd.Series) -> pd.DataFrame:
    partes = serie.str.rsplit("-", n=1, expand=True)
    if partes.shape[1] < 2:
        partes[1] = pd.NA
    partes.columns = ["cidade", "uf"]
    partes["cidade"] = partes["cidade"].str.strip().str.title()
    partes["uf"] = partes["uf"].str.strip().str.upper()
    partes.loc[~partes["uf"].fillna("").str.fullmatch(r"[A-Z]{2}"), "uf"] = pd.NA
    return partes


def _ler(arquivo, nome: str) -> pd.DataFrame:
    if nome.endswith(".csv"):
        try:
            return pd.read_csv(arquivo, dtype=str, sep=None, engine="python")
        except UnicodeDecodeError:
            arquivo.seek(0)
            return pd.read_csv(arquivo, dtype=str, sep=None, engine="python", encoding="latin1")
    return pd.read_excel(arquivo, sheet_name="Sheet1", dtype=str)


def _data(serie):
    datas = pd.to_datetime(serie, format="ISO8601", errors="coerce")

    restante = datas.isna() & serie.notna()
    if restante.any():
        datas.loc[restante] = pd.to_datetime(
            serie.loc[restante], dayfirst=True, errors="coerce"
        )

    return datas


def process_fretes(arquivo) -> dict:
    """Retorna fretes, ignorados e erros; conserva a associação pedido-cliente."""
    nome = (getattr(arquivo, "filename", "") or "").lower()
    nome_sem_extensao, _ = os.path.splitext(nome)
    planta = get_planta(nome_sem_extensao)
    if planta is None:
        raise ValueError(
            "Não encontrei uma planta válida no nome do arquivo "
            f"('{nome_sem_extensao}'). Inclua o código (ex.: fretes_1304.xlsx)."
        )

    df = _ler(arquivo, nome)
    df.columns = [str(c).strip() for c in df.columns]
    faltando = [c for c in OBRIGATORIAS if c not in df.columns]
    if faltando:
        raise ValueError("Colunas ausentes no arquivo: " + ", ".join(faltando))

    df = df.rename(columns=RENAME_COLS).dropna(how="all").copy()
    df["linha_excel"] = df.index + 2
    for col in TEXTO_COLS:
        if col in df.columns:
            df[col] = _limpar_texto(df[col])
    for col in ("material", "material_desc"):
        if col not in df.columns:
            df[col] = pd.Series(pd.NA, index=df.index, dtype="string")

    for col in ("pedido", "customer", "num_frete"):
        df[col] = df[col].map(_identificador)
    df["data_frete"] = _data(df["data_frete"])
    df["peso_kg"] = df["peso_kg"].map(_peso)
    df[["cidade", "uf"]] = _separar_cidade_uf(df["cidade_destino"])

    erros: list[str] = []
    sem_frete = df["num_frete"].isna()
    for n in df.loc[sem_frete, "linha_excel"]:
        erros.append(f"Linha {n}: sem número de frete")
    df = df.loc[~sem_frete].copy()

    
    # Fretes com motorista também serão processados.
    # A identificação será feita por número de frete,
    # considerando todas as linhas e pedidos associados.
    ignorados = []


    invalidas = df["peso_kg"].isna() | df["cidade"].isna() | df["uf"].isna()
    for _, r in df.loc[invalidas].iterrows():
        motivo = "peso inválido" if pd.isna(r["peso_kg"]) else "destino fora do padrão CIDADE-UF"
        erros.append(f"Linha {r['linha_excel']} (frete {r['num_frete']}): {motivo}")
    fretes_com_erro = set(df.loc[invalidas, "num_frete"])
    df = df.loc[~df["num_frete"].isin(fretes_com_erro)].copy()

    mapa_clientes = _obter_mapa_clientes()

    fretes = []
    for num, g in df.groupby("num_frete", sort=False):
        primeira = g.iloc[0]
        
        motoristas = list(dict.fromkeys(
            str(valor).strip()
            for valor in g["motorista"].dropna()
            if str(valor).strip()
        ))

        possui_motorista = bool(motoristas)

        status_inicial = (
            "cotacao_aceita"
            if possui_motorista
            else "em_preparacao"
        )

        destinos = list(dict.fromkeys(zip(g["cidade"], g["uf"])))
        ultimo_cidade, ultimo_uf = destinos[-1]
        transf = (
            get_planta(primeira["local_transbordo"])
            if pd.notna(primeira["local_transbordo"]) else None
        )
        tipo = "Transbordo" if transf else "Múltiplas paradas" if len(destinos) > 1 else "Direta"

        # Um pedido pode ocupar várias linhas (materiais). Evita duplicação de pares.
        pedidos_clientes = []
        pares_vistos = set()
        clientes = []
        clientes_vistos = set()
        for _, linha in g.iterrows():
            pedido = _identificador(linha["pedido"])
            cliente = _identificador(linha["customer"])
            if pedido is not None and (pedido, cliente) not in pares_vistos:
                pedidos_clientes.append({"pedido": pedido, "customer_id": cliente})
                pares_vistos.add((pedido, cliente))
            if cliente is not None and cliente not in clientes_vistos:
                clientes.append({
                    "customer_id": cliente,
                    "customer_name": mapa_clientes.get(_chave_cliente(cliente)),
                })
                clientes_vistos.add(cliente)

        fretes.append({
            "num": str(num),
            "motoristas": motoristas,
            "possui_motorista": possui_motorista,
            "status_inicial": status_inicial,
            "pedidos": sorted(set(g["pedido"].dropna().tolist())),
            "customer": _identificador(primeira["customer"]),  # compatibilidade
            "clientes": clientes,
            "pedidos_clientes": pedidos_clientes,
            "peso_kg": float(g["peso_kg"].sum()),
            "data_carga": (
                primeira["data_frete"].strftime("%d-%m-%Y").replace("-","/")
                if pd.notna(primeira["data_frete"]) else None
            ),
            "planta": planta,
            "destino": ultimo_cidade,
            "uf": ultimo_uf,
            "stops": [f"{c}-{u}" for c, u in destinos],
            "transfer_planta": transf,
            "tipo": tipo,
            "troca_nota": planta["uf"] != ultimo_uf,
            "cep": "",
            "materiais": [
                {
                    "material": _identificador(m),
                    "descricao": None if pd.isna(d) else str(d),
                }
                for m, d in zip(g["material"], g["material_desc"])
            ],
        })

    log.info(
        "Fretes: %d processados, %d ignorados, %d erros (planta %s)",
        len(fretes), len(ignorados), len(erros), planta["codigo"],
    )
    return {"fretes": fretes, "ignorados": ignorados, "erros": erros}
