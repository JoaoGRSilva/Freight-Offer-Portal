"""Enriquecimento dos fretes: coordenadas e distância da rota completa."""
import logging
import re
import unicodedata

from services.postal_code import (
    pesquisar_localizacao,
    trechos_rota_km,
    validar_cep,
)

log = logging.getLogger(__name__)

# "Ivai-PR", "Irati / PR", "Guarapuava, PR" -> (cidade, UF)
_CIDADE_UF = re.compile(r"^(.*?)\s*[-/,]\s*([A-Za-z]{2})$")


def _separar_cidade_uf(texto, uf_padrao):
    texto = str(texto or "").strip()
    achou = _CIDADE_UF.match(texto)

    if achou:
        return achou.group(1).strip(), achou.group(2).upper()

    return texto, (uf_padrao or "").strip().upper()


def _norm(texto):
    texto = unicodedata.normalize("NFD", str(texto or ""))
    texto = "".join(ch for ch in texto if unicodedata.category(ch) != "Mn")
    return texto.casefold().strip()


def _mesma_cidade(a, b):
    cidade_a, _ = _separar_cidade_uf(a, "")
    cidade_b, _ = _separar_cidade_uf(b, "")
    return _norm(cidade_a) == _norm(cidade_b)


def _nomes_da_rota(frete):
    """Cidades na ordem em que o caminhão passa (a planta pode ou não vir)."""

    stops = frete.get("stops")

    if stops:
        return [s for s in stops if s]

    cidades = []

    for i, t in enumerate(frete.get("trechos") or []):
        origem = (
            t.get("origem") or t.get("from")
            or t.get("cidade_origem") or t.get("origem_cidade")
        )
        destino = (
            t.get("destino") or t.get("to")
            or t.get("cidade_destino") or t.get("destino_cidade")
        )

        if i == 0 and origem:
            cidades.append(origem)
        if destino:
            cidades.append(destino)

    if cidades:
        return cidades

    return [frete["destino"]] if frete.get("destino") else []


def _coordenadas(cidade, uf, cache_local):
    chave = (cidade.strip().casefold(), uf.strip().upper())

    if chave not in cache_local:
        cache_local[chave] = pesquisar_localizacao(cidade=cidade, uf=uf)

    return cache_local[chave]



def _coordenadas_do_cep(local, cache_cep):
    """Consulta o CEP uma vez por lote e reutiliza as coordenadas."""

    if not local:
        return

    cep = re.sub(r"\D", "", str(local.get("cep") or ""))

    if not cep:
        return

    if local.get("lat") is not None and local.get("lon") is not None:
        return

    if cep not in cache_cep:
        cache_cep[cep] = validar_cep(cep)

    info = cache_cep[cep]

    if info:
        local["lat"] = info.get("lat")
        local["lon"] = info.get("lon")

def _trechos_da_rota(frete, cache_local, cache_rotas):
    """
    Calcula os km de cada trecho da rota completa:
        planta -> transbordo -> paradas -> destino final.

    Reutiliza distâncias já calculadas para rotas idênticas
    dentro do mesmo upload.
    """

    planta = frete.get("planta") or {}

    if planta.get("lat") is None or planta.get("lon") is None:
        return None

    pontos = [planta]
    anterior = planta.get("cidade", "")

    # Incluir planta de transbordo, quando existir
    transf = frete.get("transfer_planta") or {}

    if (
        transf.get("lat") is not None
        and transf.get("lon") is not None
        and not _mesma_cidade(transf.get("cidade", ""), anterior)
    ):
        pontos.append(transf)
        anterior = transf.get("cidade", "")

    nomes = _nomes_da_rota(frete)

    # Evitar repetir a planta de origem
    if nomes and _mesma_cidade(nomes[0], planta.get("cidade", "")):
        nomes = nomes[1:]

    for nome in nomes:

        if _mesma_cidade(nome, anterior):
            continue

        cidade, uf = _separar_cidade_uf(nome, frete.get("uf"))

        if not cidade or not uf:
            log.warning("Parada sem cidade/UF: %r", nome)
            return None

        local = _coordenadas(cidade, uf, cache_local)

        if not local:
            log.warning(
                "Sem coordenadas para a parada %s-%s",
                cidade,
                uf
            )
            return None

        pontos.append(local)
        anterior = nome

    # Cache baseado nas coordenadas de todos os pontos,
    # preservando a ordem da rota.
    try:
        chave_rota = tuple(
            (
                round(float(p["lat"]), 6),
                round(float(p["lon"]), 6)
            )
            for p in pontos
        )
    except (KeyError, TypeError, ValueError):
        log.warning("Rota com coordenadas inválidas")
        return None

    if chave_rota not in cache_rotas:
        cache_rotas[chave_rota] = trechos_rota_km(pontos)

    resultado = cache_rotas[chave_rota]

    return list(resultado) if resultado is not None else None

def enriquecer_localizacoes(fretes: list[dict]) -> list[dict]:
    """
    Adiciona a cada frete:
        localizacao_destino  coordenadas do destino final
        km_trechos           km de cada trecho da rota (pela estrada)
        km_estimado          soma dos trechos
    """

    cache_local = {}
    cache_cep = {}
    cache_rotas = {}

    for frete in fretes:

        # Coordenadas da planta (e da planta de transbordo): pelo CEP cadastrado
        _coordenadas_do_cep(frete.get("planta"), cache_cep)
        _coordenadas_do_cep(frete.get("transfer_planta"), cache_cep)

        # Coordenadas do destino final (mantido para o restante do sistema)
        cidade = frete.get("destino")
        uf = frete.get("uf")

        if cidade and uf:
            frete["localizacao_destino"] = _coordenadas(
                cidade, uf, cache_local
            )
        else:
            frete["localizacao_destino"] = {}

        # Km da rota completa, passando pelas paradas
        trechos = _trechos_da_rota(frete,cache_local,cache_rotas)

        frete["km_trechos"] = trechos
        frete["km_estimado"] = (
            round(sum(trechos), 1) if trechos else None
        )

    return fretes