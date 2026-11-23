"""Consultas de CEP, cidades e rotas com cache persistente SQLite.

Dependências: requests, analytics.config.DB.
Mantém as assinaturas públicas do módulo services.postal_code.
"""
import json
import logging
import math
import re
import threading
import time
import unicodedata
from contextlib import contextmanager

import requests

from services.db import connect

log = logging.getLogger(__name__)
SESSION = requests.Session()
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
BRASILAPI_URL = "https://brasilapi.com.br/api/cep/v2/{}"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{}"
HEADERS = {"User-Agent": "FreightPortal/1.0 (internal prototype; contact: joaog.silva@dsm-firmenich.com)"}
# Configure um contato real e autorizado no User-Agent antes de uso intensivo.
_NOMINATIM_LOCK = threading.Lock()
_ULTIMA_CONSULTA_NOMINATIM = 0.0
_NOMINATIM_BLOQUEADO_ATE = 0.0  # Pausa após HTTP 403/429



@contextmanager
def _con():
    """
    Abre o banco de fretes e garante a existência
    das tabelas utilizadas pelo cache geográfico.
    """

    with connect("fretes") as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS cep_cache (
                cep TEXT PRIMARY KEY,
                dados TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS cidade_cache (
                cidade TEXT NOT NULL,
                uf TEXT NOT NULL,
                dados TEXT NOT NULL,
                PRIMARY KEY (cidade, uf)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS rota_trechos_cache (
                chave TEXT PRIMARY KEY,
                trechos TEXT NOT NULL
            )
        """)

        yield conn


def _get_cache(tabela, coluna, parametros):
    """Consulta informações armazenadas no cache."""

    consultas = {
        "cidade_cache": (
            "SELECT dados FROM cidade_cache WHERE cidade=? AND uf=?"
        ),
        "cep_cache": (
            "SELECT dados FROM cep_cache WHERE cep=?"
        ),
        "rota_trechos_cache": (
            "SELECT trechos FROM rota_trechos_cache WHERE chave=?"
        ),
    }

    sql = consultas.get(tabela)

    if sql is None:
        raise ValueError(f"Tabela de cache inválida: {tabela}")

    with _con() as conn:
        row = conn.execute(sql, parametros).fetchone()

    if not row:
        return None

    try:
        return json.loads(row[0])

    except (TypeError, ValueError):
        return None


def _put_cache(tabela, parametros):
    """Insere ou atualiza informações no cache."""

    comandos = {
        "cidade_cache": """
            INSERT OR REPLACE INTO cidade_cache
            (cidade, uf, dados)
            VALUES (?, ?, ?)
        """,

        "cep_cache": """
            INSERT OR REPLACE INTO cep_cache
            (cep, dados)
            VALUES (?, ?)
        """,

        "rota_trechos_cache": """
            INSERT OR REPLACE INTO rota_trechos_cache
            (chave, trechos)
            VALUES (?, ?)
        """,
    }

    sql = comandos.get(tabela)

    if sql is None:
        raise ValueError(f"Tabela de cache inválida: {tabela}")

    with _con() as conn:
        conn.execute(sql, parametros)

def _normalizar_cidade(cidade):
    """
    Normaliza o nome da cidade para uso como chave de cache.
    Remove acentos, espaços extras e diferenças entre maiúsculas/minúsculas.
    """
    if not cidade:
        return ""

    cidade = str(cidade).strip().lower()
    cidade = unicodedata.normalize("NFKD", cidade)
    cidade = "".join(
        caractere
        for caractere in cidade
        if not unicodedata.combining(caractere)
    )

    cidade = re.sub(r"\s+", " ", cidade)

    return cidade

def pesquisar_localizacao(cidade: str, uf: str) -> dict:
    global _ULTIMA_CONSULTA_NOMINATIM, _NOMINATIM_BLOQUEADO_ATE
    cidade = str(cidade or "").strip()
    uf = str(uf or "").strip().upper()
    if not cidade or not uf:
        return {}
    chave = (cidade.casefold(), uf)  # Compatível com cache anterior
    cached = _get_cache("cidade_cache", "dados", chave)
    if cached is not None:
        return cached
    # Consulta também chave normalizada sem acentos, mas não altera o resultado salvo anteriormente.
    chave_normalizada = (_normalizar_cidade(cidade), uf)
    if chave_normalizada != chave:
        cached = _get_cache("cidade_cache", "dados", chave_normalizada)
        if cached is not None:
            return cached
    inicio = time.perf_counter()
    try:
        # Serializa consultas ao serviço público e respeita >=1,1s entre inícios.
        with _NOMINATIM_LOCK:
            if time.monotonic() < _NOMINATIM_BLOQUEADO_ATE:
                log.warning("Nominatim em pausa temporária; usando apenas cache")
                return {}
            espera = 1.1 - (time.monotonic() - _ULTIMA_CONSULTA_NOMINATIM)
            if espera > 0:
                time.sleep(espera)
            _ULTIMA_CONSULTA_NOMINATIM = time.monotonic()
            resposta = SESSION.get(
                NOMINATIM_URL,
                params={"city": cidade, "state": uf, "country": "Brazil", "format": "jsonv2", "limit": 1},
                headers=HEADERS, timeout=(3, 8),
            )
        if resposta.status_code in (403, 429):
            with _NOMINATIM_LOCK:
                _NOMINATIM_BLOQUEADO_ATE = time.monotonic() + 3600
            log.warning("Nominatim HTTP %s: consultas suspensas por 1 hora", resposta.status_code)
            return {}
        resposta.raise_for_status()
        resultados = resposta.json()
        if not resultados:
            return {}
        local = resultados[0]
        dados = {"cidade": cidade, "uf": uf, "lat": float(local["lat"]), "lon": float(local["lon"])}
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        log.warning("Consulta Nominatim falhou para %s-%s: %s", cidade, uf, exc)
        return {}
    finally:
        log.info("[GEO] Nominatim %s-%s: %.2fs", cidade, uf, time.perf_counter() - inicio)
    _put_cache("cidade_cache", (chave_normalizada[0], uf, json.dumps(dados, ensure_ascii=False)))
    if chave_normalizada != chave:
        _put_cache("cidade_cache", (chave[0], uf, json.dumps(dados, ensure_ascii=False)))
    return dados


def normalizar_cep(cep) -> str | None:
    digitos = re.sub(r"\D", "", str(cep or ""))
    if len(digitos) == 7:
        digitos = "0" + digitos
    return digitos if len(digitos) == 8 else None


def _completar_coordenadas_cep(dados: dict) -> dict:
    """Usa centro da cidade como alternativa, nunca como coordenada exata do CEP."""
    if not isinstance(dados, dict):
        return {}
    if dados.get("lat") is not None and dados.get("lon") is not None:
        return dados

    cidade = dados.get("cidade")
    uf = dados.get("uf")
    if not cidade or not uf:
        return dados

    local = pesquisar_localizacao(cidade, uf)
    if local.get("lat") is None or local.get("lon") is None:
        return dados

    atualizado = dict(dados)
    atualizado["lat"] = local["lat"]
    atualizado["lon"] = local["lon"]
    atualizado["coordenadas_aproximadas"] = True
    atualizado["fonte_coordenadas"] = "centro_cidade_nominatim"
    return atualizado


def validar_cep(cep: str) -> dict:
    cep_normalizado = normalizar_cep(cep)
    if not cep_normalizado:
        return {}

    # Cache antigo continua válido; completa coordenadas ausentes quando possível.
    for chave in dict.fromkeys((cep_normalizado, str(cep))):
        cached = _get_cache("cep_cache", "dados", (chave,))
        if cached is not None:
            if not isinstance(cached, dict):
                return {}
            completo = _completar_coordenadas_cep(cached)
            if completo != cached:
                _put_cache("cep_cache", (
                    cep_normalizado, json.dumps(completo, ensure_ascii=False)
                ))
            return completo

    inicio = time.perf_counter()
    try:
        resposta = SESSION.get(BRASILAPI_URL.format(cep_normalizado), timeout=(3, 8))
        if resposta.status_code != 200:
            log.warning("BrasilAPI CEP %s: HTTP %s", cep_normalizado, resposta.status_code)
            return {}
        j = resposta.json()
        co = (j.get("location") or {}).get("coordinates") or {}
        dados = {
            "cidade": j.get("city"),
            "uf": j.get("state"),
            "lat": float(co["latitude"]) if co.get("latitude") not in (None, "") else None,
            "lon": float(co["longitude"]) if co.get("longitude") not in (None, "") else None,
        }
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        log.warning("BrasilAPI falhou para CEP %s: %s", cep_normalizado, exc)
        return {}
    finally:
        log.info("[GEO] BrasilAPI CEP %s: %.2fs", cep_normalizado, time.perf_counter() - inicio)

    dados = _completar_coordenadas_cep(dados)
    _put_cache("cep_cache", (cep_normalizado, json.dumps(dados, ensure_ascii=False)))
    return dados


def distancia_km(a: dict, b: dict, fator_rodoviario: float = 1.25) -> float | None:
    if not all(x.get(k) is not None for x in (a, b) for k in ("lat", "lon")):
        return None
    p1, p2 = math.radians(float(a["lat"])), math.radians(float(b["lat"]))
    dp = p2 - p1
    dl = math.radians(float(b["lon"]) - float(a["lon"]))
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * 6371 * math.asin(math.sqrt(h)) * fator_rodoviario, 1)


def trechos_rota_km(pontos: list[dict], fator_fallback: float = 1.35) -> list[float] | None:
    # Não elimina silenciosamente paradas inválidas: isso alteraria o percurso.
    if not pontos or any(
        not p or p.get("lat") is None or p.get("lon") is None for p in pontos
    ) or len(pontos) < 2:
        return None
    try:
        chave = ";".join(f'{float(p["lon"]):.5f},{float(p["lat"]):.5f}' for p in pontos)
    except (ValueError, TypeError):
        return None
    cached = _get_cache("rota_trechos_cache", "trechos", (chave,))
    if isinstance(cached, list) and len(cached) == len(pontos) - 1:
        return cached
    inicio = time.perf_counter()
    trechos = None
    try:
        resposta = SESSION.get(
            OSRM_URL.format(chave),
            params={"overview": "false"},
            headers=HEADERS,
            timeout=(3, 8),
        )
        resposta.raise_for_status()
        j = resposta.json()
        if j.get("code") == "Ok" and j.get("routes"):
            legs = j["routes"][0].get("legs") or []
            if len(legs) == len(pontos) - 1:
                trechos = [round(float(leg["distance"]) / 1000, 1) for leg in legs]
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        log.warning("OSRM falhou para rota de %d pontos: %s", len(pontos), exc)
    finally:
        log.info("[GEO] OSRM (%d pontos): %.2fs", len(pontos), time.perf_counter() - inicio)
    if trechos is None:
        # Preserva fallback anterior e NÃO persiste estimativas como distâncias reais.
        trechos = []
        for a, b in zip(pontos, pontos[1:]):
            km = distancia_km(a, b, fator_fallback)
            if km is None:
                return None
            trechos.append(km)
        return trechos
    _put_cache("rota_trechos_cache", (chave, json.dumps(trechos)))
    return trechos


def distancia_rota_km(pontos: list[dict], fator_fallback: float = 1.35) -> float | None:
    trechos = trechos_rota_km(pontos, fator_fallback)
    return None if trechos is None else round(sum(trechos), 1)
