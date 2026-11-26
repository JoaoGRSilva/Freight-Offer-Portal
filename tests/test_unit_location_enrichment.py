import pytest

from services import location_enrichment as le


# ============================================================
# _separar_cidade_uf
# ============================================================

@pytest.mark.parametrize(
    ("texto", "uf_padrao", "esperado"),
    [
        ("Ivai-PR", "SP", ("Ivai", "PR")),
        ("Irati / PR", "SP", ("Irati", "PR")),
        ("Guarapuava, PR", "SP", ("Guarapuava", "PR")),
        ("Campinas", "sp", ("Campinas", "SP")),
        ("  Curitiba  ", " pr ", ("Curitiba", "PR")),
        ("", "sp", ("", "SP")),
        (None, "sp", ("", "SP")),
        ("Cidade", None, ("Cidade", "")),
    ],
)
def test_separar_cidade_uf(texto, uf_padrao, esperado):
    assert le._separar_cidade_uf(texto, uf_padrao) == esperado


# ============================================================
# _norm e _mesma_cidade
# ============================================================

@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("São Paulo", "sao paulo"),
        ("  CURITIBA  ", "curitiba"),
        ("João Pessoa", "joao pessoa"),
        ("ÁÉÍÓÚ", "aeiou"),
        (None, ""),
        ("", ""),
    ],
)
def test_norm(texto, esperado):
    assert le._norm(texto) == esperado


@pytest.mark.parametrize(
    ("cidade_a", "cidade_b", "esperado"),
    [
        ("São Paulo-SP", "Sao Paulo-RJ", True),
        ("Ivai-PR", "Ivaí / SC", True),
        ("Curitiba", "CURITIBA-PR", True),
        ("Campinas-SP", "Santos-SP", False),
        ("", "", True),
    ],
)
def test_mesma_cidade(cidade_a, cidade_b, esperado):
    assert le._mesma_cidade(cidade_a, cidade_b) is esperado


# ============================================================
# _nomes_da_rota
# ============================================================

def test_nomes_da_rota_uses_stops_and_removes_empty_values():
    frete = {
        "stops": ["Curitiba-PR", None, "", "Irati-PR", "Guarapuava-PR"],
        "destino": "Ponta Grossa",
    }

    assert le._nomes_da_rota(frete) == [
        "Curitiba-PR",
        "Irati-PR",
        "Guarapuava-PR",
    ]


def test_nomes_da_rota_uses_segment_origins_and_destinations():
    frete = {
        "trechos": [
            {"origem": "Curitiba", "destino": "Irati"},
            {"origem": "Irati", "destino": "Guarapuava"},
        ]
    }

    assert le._nomes_da_rota(frete) == [
        "Curitiba",
        "Irati",
        "Guarapuava",
    ]


@pytest.mark.parametrize(
    ("trecho", "esperado"),
    [
        (
            {"from": "Curitiba", "to": "Irati"},
            ["Curitiba", "Irati"],
        ),
        (
            {"cidade_origem": "Curitiba", "cidade_destino": "Irati"},
            ["Curitiba", "Irati"],
        ),
        (
            {"origem_cidade": "Curitiba", "destino_cidade": "Irati"},
            ["Curitiba", "Irati"],
        ),
    ],
)
def test_nomes_da_rota_supports_alternative_segment_fields(trecho, esperado):
    assert le._nomes_da_rota({"trechos": [trecho]}) == esperado


def test_nomes_da_rota_uses_only_first_origin():
    frete = {
        "trechos": [
            {"origem": "Curitiba", "destino": "Irati"},
            {"origem": "Ponta Grossa", "destino": "Guarapuava"},
        ]
    }

    assert le._nomes_da_rota(frete) == [
        "Curitiba",
        "Irati",
        "Guarapuava",
    ]


def test_nomes_da_rota_falls_back_to_destination():
    assert le._nomes_da_rota({"destino": "Santos-SP"}) == ["Santos-SP"]


def test_nomes_da_rota_returns_empty_without_route():
    assert le._nomes_da_rota({}) == []


def test_nomes_da_rota_ignores_empty_stops_and_uses_segments():
    frete = {
        "stops": [],
        "trechos": [{"origem": "Curitiba", "destino": "Irati"}],
    }

    assert le._nomes_da_rota(frete) == ["Curitiba", "Irati"]


# ============================================================
# _coordenadas
# ============================================================

def test_coordenadas_queries_and_caches_result(monkeypatch):
    chamadas = []

    def fake_pesquisar(cidade, uf):
        chamadas.append((cidade, uf))
        return {"lat": -25.4, "lon": -49.2}

    monkeypatch.setattr(le, "pesquisar_localizacao", fake_pesquisar)

    cache = {}

    primeira = le._coordenadas("Curitiba", "PR", cache)
    segunda = le._coordenadas("Curitiba", "PR", cache)

    assert primeira == segunda
    assert len(chamadas) == 1


def test_coordenadas_reuses_cache_case_insensitively(monkeypatch):
    chamadas = []

    def fake_pesquisar(cidade, uf):
        chamadas.append((cidade, uf))
        return {"lat": 1, "lon": 2}

    monkeypatch.setattr(le, "pesquisar_localizacao", fake_pesquisar)

    cache = {}

    le._coordenadas("Curitiba", "pr", cache)
    le._coordenadas("CURITIBA", "PR", cache)

    assert len(chamadas) == 1


def test_coordenadas_uses_different_cache_for_different_states(monkeypatch):
    chamadas = []

    def fake_pesquisar(cidade, uf):
        chamadas.append((cidade, uf))
        return {"lat": 1, "lon": 2}

    monkeypatch.setattr(le, "pesquisar_localizacao", fake_pesquisar)

    cache = {}

    le._coordenadas("Curitiba", "PR", cache)
    le._coordenadas("Curitiba", "SC", cache)

    assert len(chamadas) == 2


def test_coordenadas_caches_empty_result(monkeypatch):
    chamadas = []

    def fake_pesquisar(**kwargs):
        chamadas.append(kwargs)
        return {}

    monkeypatch.setattr(le, "pesquisar_localizacao", fake_pesquisar)

    cache = {}

    assert le._coordenadas("Cidade", "PR", cache) == {}
    assert le._coordenadas("Cidade", "PR", cache) == {}
    assert len(chamadas) == 1


# ============================================================
# _coordenadas_do_cep
# ============================================================

def test_coordenadas_do_cep_ignores_missing_local():
    assert le._coordenadas_do_cep(None, {}) is None


@pytest.mark.parametrize(
    "local",
    [
        {},
        {"cep": None},
        {"cep": ""},
        {"cep": "   "},
    ],
)
def test_coordenadas_do_cep_ignores_missing_cep(local):
    assert le._coordenadas_do_cep(local, {}) is None


def test_coordenadas_do_cep_preserves_existing_coordinates(monkeypatch):
    def fail_if_called(cep):
        pytest.fail("Não deveria consultar CEP com coordenadas existentes")

    monkeypatch.setattr(le, "validar_cep", fail_if_called)

    local = {
        "cep": "80000000",
        "lat": -25.4,
        "lon": -49.2,
    }

    le._coordenadas_do_cep(local, {})

    assert local["lat"] == -25.4
    assert local["lon"] == -49.2


def test_coordenadas_do_cep_fetches_and_normalizes_cep(monkeypatch):
    chamadas = []

    def fake_validar(cep):
        chamadas.append(cep)
        return {"lat": -25.4, "lon": -49.2}

    monkeypatch.setattr(le, "validar_cep", fake_validar)

    local = {"cep": "80.000-000"}
    cache = {}

    le._coordenadas_do_cep(local, cache)

    assert chamadas == ["80000000"]
    assert local["lat"] == -25.4
    assert local["lon"] == -49.2


def test_coordenadas_do_cep_reuses_cache_for_same_cep(monkeypatch):
    chamadas = []

    def fake_validar(cep):
        chamadas.append(cep)
        return {"lat": -25.4, "lon": -49.2}

    monkeypatch.setattr(le, "validar_cep", fake_validar)

    cache = {}
    local_a = {"cep": "80000000"}
    local_b = {"cep": "80000-000"}

    le._coordenadas_do_cep(local_a, cache)
    le._coordenadas_do_cep(local_b, cache)

    assert len(chamadas) == 1
    assert local_b["lat"] == -25.4
    assert local_b["lon"] == -49.2


def test_coordenadas_do_cep_does_not_change_local_when_lookup_is_empty(
    monkeypatch,
):
    monkeypatch.setattr(le, "validar_cep", lambda cep: {})

    local = {"cep": "80000000"}

    le._coordenadas_do_cep(local, {})

    assert "lat" not in local
    assert "lon" not in local


# ============================================================
# _trechos_da_rota
# ============================================================

def test_trechos_da_rota_returns_none_without_plant_coordinates():
    frete = {"planta": {"cidade": "Curitiba"}}

    assert le._trechos_da_rota(frete, {}, {}) is None


def test_trechos_da_rota_returns_none_without_plant():
    assert le._trechos_da_rota({}, {}, {}) is None


def test_trechos_da_rota_skips_repeated_origin(monkeypatch):
    chamadas = []

    monkeypatch.setattr(
        le,
        "_coordenadas",
        lambda cidade, uf, cache: (
            chamadas.append((cidade, uf))
            or {"cidade": cidade, "lat": -23.5, "lon": -46.6}
        ),
    )

    monkeypatch.setattr(
        le,
        "trechos_rota_km",
        lambda pontos: [100.0],
    )

    frete = {
        "planta": {
            "cidade": "Curitiba",
            "lat": -25.4,
            "lon": -49.2,
        },
        "uf": "PR",
        "stops": ["Curitiba-PR", "Irati-PR"],
    }

    resultado = le._trechos_da_rota(frete, {}, {})

    assert resultado == [100.0]
    assert chamadas == [("Irati", "PR")]


def test_trechos_da_rota_includes_transfer_plant(monkeypatch):
    chamadas = []

    monkeypatch.setattr(
        le,
        "_coordenadas",
        lambda cidade, uf, cache: (
            chamadas.append(cidade)
            or {"cidade": cidade, "lat": -23.0, "lon": -46.0}
        ),
    )

    pontos_recebidos = []

    monkeypatch.setattr(
        le,
        "trechos_rota_km",
        lambda pontos: (
            pontos_recebidos.extend(pontos) or [50.0, 80.0]
        ),
    )

    frete = {
        "planta": {
            "cidade": "Curitiba",
            "lat": -25.4,
            "lon": -49.2,
        },
        "transfer_planta": {
            "cidade": "Ponta Grossa",
            "lat": -25.1,
            "lon": -50.1,
        },
        "uf": "PR",
        "stops": ["Irati-PR"],
    }

    resultado = le._trechos_da_rota(frete, {}, {})

    assert resultado == [50.0, 80.0]
    assert len(pontos_recebidos) == 3
    assert pontos_recebidos[1]["cidade"] == "Ponta Grossa"
    assert chamadas == ["Irati"]


def test_trechos_da_rota_skips_transfer_in_same_city(monkeypatch):
    pontos_recebidos = []

    monkeypatch.setattr(
        le,
        "_coordenadas",
        lambda cidade, uf, cache: {
            "cidade": cidade,
            "lat": -23.0,
            "lon": -46.0,
        },
    )

    monkeypatch.setattr(
        le,
        "trechos_rota_km",
        lambda pontos: (
            pontos_recebidos.extend(pontos) or [100.0]
        ),
    )

    frete = {
        "planta": {
            "cidade": "Curitiba-PR",
            "lat": -25.4,
            "lon": -49.2,
        },
        "transfer_planta": {
            "cidade": "Curitiba",
            "lat": -25.5,
            "lon": -49.3,
        },
        "uf": "PR",
        "stops": ["Irati-PR"],
    }

    resultado = le._trechos_da_rota(frete, {}, {})

    assert resultado == [100.0]
    assert len(pontos_recebidos) == 2


def test_trechos_da_rota_returns_none_when_stop_has_no_uf(monkeypatch):
    frete = {
        "planta": {
            "cidade": "Curitiba",
            "lat": -25.4,
            "lon": -49.2,
        },
        "stops": ["Irati"],
    }

    monkeypatch.setattr(
        le,
        "_coordenadas",
        lambda *args: pytest.fail("Não deveria consultar parada sem UF"),
    )

    assert le._trechos_da_rota(frete, {}, {}) is None


def test_trechos_da_rota_returns_none_when_coordinates_are_not_found(
    monkeypatch,
):
    frete = {
        "planta": {
            "cidade": "Curitiba",
            "lat": -25.4,
            "lon": -49.2,
        },
        "uf": "PR",
        "stops": ["Irati"],
    }

    monkeypatch.setattr(le, "_coordenadas", lambda *args: {})

    assert le._trechos_da_rota(frete, {}, {}) is None


@pytest.mark.parametrize(
    "planta",
    [
        {"cidade": "Curitiba", "lat": "inválido", "lon": -49.2},
        {"cidade": "Curitiba", "lat": -25.4},
        {"cidade": "Curitiba", "lat": None, "lon": -49.2},
    ],
)
def test_trechos_da_rota_returns_none_for_invalid_plant_coordinates(planta):
    frete = {"planta": planta}

    assert le._trechos_da_rota(frete, {}, {}) is None


def test_trechos_da_rota_returns_none_for_invalid_stop_coordinates(monkeypatch):
    frete = {
        "planta": {
            "cidade": "Curitiba",
            "lat": -25.4,
            "lon": -49.2,
        },
        "uf": "PR",
        "stops": ["Irati"],
    }

    monkeypatch.setattr(
        le,
        "_coordenadas",
        lambda *args: {"lat": "inválido", "lon": -50.0},
    )

    assert le._trechos_da_rota(frete, {}, {}) is None


def test_trechos_da_rota_reuses_route_cache(monkeypatch):
    chamadas = []

    monkeypatch.setattr(
        le,
        "_coordenadas",
        lambda cidade, uf, cache: {
            "cidade": cidade,
            "lat": -24.0,
            "lon": -50.0,
        },
    )

    def fake_trechos(pontos):
        chamadas.append(pontos)
        return [100.0]

    monkeypatch.setattr(le, "trechos_rota_km", fake_trechos)

    frete = {
        "planta": {
            "cidade": "Curitiba",
            "lat": -25.4,
            "lon": -49.2,
        },
        "uf": "PR",
        "stops": ["Irati"],
    }

    cache_rotas = {}

    primeira = le._trechos_da_rota(frete, {}, cache_rotas)
    segunda = le._trechos_da_rota(frete, {}, cache_rotas)

    assert primeira == [100.0]
    assert segunda == [100.0]
    assert len(chamadas) == 1


def test_trechos_da_rota_returns_copy_of_cached_result(monkeypatch):
    monkeypatch.setattr(
        le,
        "_coordenadas",
        lambda *args: {"lat": -24.0, "lon": -50.0},
    )

    monkeypatch.setattr(
        le,
        "trechos_rota_km",
        lambda pontos: [100.0],
    )

    frete = {
        "planta": {
            "lat": -25.4,
            "lon": -49.2,
        },
        "uf": "PR",
        "stops": ["Irati"],
    }

    cache_rotas = {}

    primeira = le._trechos_da_rota(frete, {}, cache_rotas)
    primeira.append(999.0)

    segunda = le._trechos_da_rota(frete, {}, cache_rotas)

    assert segunda == [100.0]


def test_trechos_da_rota_returns_none_when_route_calculation_fails(
    monkeypatch,
):
    monkeypatch.setattr(
        le,
        "_coordenadas",
        lambda *args: {"lat": -24.0, "lon": -50.0},
    )

    monkeypatch.setattr(
        le,
        "trechos_rota_km",
        lambda pontos: None,
    )

    frete = {
        "planta": {"lat": -25.4, "lon": -49.2},
        "uf": "PR",
        "stops": ["Irati"],
    }

    assert le._trechos_da_rota(frete, {}, {}) is None


def test_trechos_da_rota_preserves_route_order(monkeypatch):
    pontos_recebidos = []

    def fake_coordenadas(cidade, uf, cache):
        return {
            "cidade": cidade,
            "lat": float(len(cidade)),
            "lon": -50.0,
        }

    monkeypatch.setattr(le, "_coordenadas", fake_coordenadas)

    def fake_rota(pontos):
        pontos_recebidos.extend(pontos)
        return [10.0, 20.0, 30.0]

    monkeypatch.setattr(le, "trechos_rota_km", fake_rota)

    frete = {
        "planta": {
            "cidade": "Origem",
            "lat": -25.0,
            "lon": -49.0,
        },
        "uf": "PR",
        "stops": ["Irati", "Guarapuava", "Pato Branco"],
    }

    resultado = le._trechos_da_rota(frete, {}, {})

    assert resultado == [10.0, 20.0, 30.0]
    assert [p.get("cidade") for p in pontos_recebidos[1:]] == [
        "Irati",
        "Guarapuava",
        "Pato Branco",
    ]


# ============================================================
# enriquecer_localizacoes
# ============================================================

def test_enriquecer_localizacoes_adds_destination_and_route_data(
    monkeypatch,
):
    monkeypatch.setattr(
        le,
        "_coordenadas_do_cep",
        lambda *args: None,
    )

    monkeypatch.setattr(
        le,
        "_coordenadas",
        lambda cidade, uf, cache: {
            "cidade": cidade,
            "lat": -23.5,
            "lon": -46.6,
        },
    )

    monkeypatch.setattr(
        le,
        "_trechos_da_rota",
        lambda *args: [100.0, 200.0, 50.0],
    )

    fretes = [
        {
            "destino": "Santos",
            "uf": "SP",
            "planta": {},
        }
    ]

    resultado = le.enriquecer_localizacoes(fretes)

    assert resultado is fretes
    assert fretes[0]["localizacao_destino"]["cidade"] == "Santos"
    assert fretes[0]["km_trechos"] == [100.0, 200.0, 50.0]
    assert fretes[0]["km_estimado"] == 350.0


def test_enriquecer_localizacoes_sets_empty_destination_without_city_or_uf(
    monkeypatch,
):
    monkeypatch.setattr(
        le,
        "_coordenadas_do_cep",
        lambda *args: None,
    )

    monkeypatch.setattr(
        le,
        "_trechos_da_rota",
        lambda *args: None,
    )

    fretes = [{"planta": {}}]

    le.enriquecer_localizacoes(fretes)

    assert fretes[0]["localizacao_destino"] == {}
    assert fretes[0]["km_trechos"] is None
    assert fretes[0]["km_estimado"] is None


@pytest.mark.parametrize(
    "frete",
    [
        {"destino": "Santos"},
        {"uf": "SP"},
        {},
    ],
)
def test_enriquecer_localizacoes_requires_destination_and_uf(
    monkeypatch,
    frete,
):
    monkeypatch.setattr(
        le,
        "_coordenadas_do_cep",
        lambda *args: None,
    )

    monkeypatch.setattr(
        le,
        "_coordenadas",
        lambda *args: pytest.fail(
            "Não deveria consultar destino sem cidade e UF"
        ),
    )

    monkeypatch.setattr(
        le,
        "_trechos_da_rota",
        lambda *args: None,
    )

    fretes = [frete]

    le.enriquecer_localizacoes(fretes)

    assert fretes[0]["localizacao_destino"] == {}


def test_enriquecer_localizacoes_does_not_calculate_total_for_empty_segments(
    monkeypatch,
):
    monkeypatch.setattr(
        le,
        "_coordenadas_do_cep",
        lambda *args: None,
    )

    monkeypatch.setattr(
        le,
        "_coordenadas",
        lambda *args: {},
    )

    monkeypatch.setattr(
        le,
        "_trechos_da_rota",
        lambda *args: [],
    )

    fretes = [{"destino": "Santos", "uf": "SP"}]

    le.enriquecer_localizacoes(fretes)

    assert fretes[0]["km_trechos"] == []
    assert fretes[0]["km_estimado"] is None


def test_enriquecer_localizacoes_reuses_caches_across_batch(monkeypatch):
    chamadas_cep = []
    chamadas_destino = []
    chamadas_rota = []

    monkeypatch.setattr(
        le,
        "_coordenadas_do_cep",
        lambda local, cache: chamadas_cep.append(
            (local, id(cache))
        ),
    )

    monkeypatch.setattr(
        le,
        "_coordenadas",
        lambda cidade, uf, cache: (
            chamadas_destino.append((cidade, uf, id(cache))) or {}
        ),
    )

    monkeypatch.setattr(
        le,
        "_trechos_da_rota",
        lambda frete, cache_local, cache_rotas: (
            chamadas_rota.append(
                (id(cache_local), id(cache_rotas))
            )
            or [10.0]
        ),
    )

    fretes = [
        {"destino": "Santos", "uf": "SP", "planta": {}},
        {"destino": "Santos", "uf": "SP", "planta": {}},
    ]

    le.enriquecer_localizacoes(fretes)

    assert len(chamadas_cep) == 4
    assert len(chamadas_destino) == 2
    assert len(chamadas_rota) == 2

    assert chamadas_destino[0][2] == chamadas_destino[1][2]
    assert chamadas_rota[0] == chamadas_rota[1]

def test_nomes_da_rota_ignora_trecho_sem_destino():
    frete = {
        "trechos": [
            {"origem": "Campinas - SP"},
        ]
    }

    assert le._nomes_da_rota(frete) == ["Campinas - SP"]

def test_nomes_da_rota_continua_quando_trecho_nao_tem_destino():
    frete = {
        "trechos": [
            {"origem": "Campinas - SP"},
            {"origem": "Jundiai - SP", "destino": "Santos - SP"},
        ]
    }

    assert le._nomes_da_rota(frete) == [
        "Campinas - SP",
        "Santos - SP",
    ]

def test_trechos_da_rota_ignora_parada_repetida(monkeypatch):
    chamadas_coordenadas = []

    def fake_coordenadas(cidade, uf, cache):
        chamadas_coordenadas.append((cidade, uf))
        return {
            "cidade": cidade,
            "uf": uf,
            "lat": -23.18,
            "lon": -46.88,
        }

    chamadas_rota = []

    def fake_trechos_rota_km(pontos):
        chamadas_rota.append(pontos)
        return [100.0]

    monkeypatch.setattr(le, "_coordenadas", fake_coordenadas)
    monkeypatch.setattr(le, "trechos_rota_km", fake_trechos_rota_km)

    frete = {
        "uf": "SP",
        "planta": {
            "cidade": "Campinas",
            "lat": -22.90,
            "lon": -47.06,
        },
        "stops": [
            "Campinas - SP",
            "Jundiai - SP",
            "Jundiai - SP",
        ],
    }

    resultado = le._trechos_da_rota(
        frete,
        cache_local={},
        cache_rotas={},
    )

    assert resultado == [100.0]

    # Jundiaí deve ser consultada apenas uma vez.
    assert chamadas_coordenadas == [("Jundiai", "SP")]

    # A rota deve conter somente planta e Jundiaí.
    assert len(chamadas_rota) == 1
    assert len(chamadas_rota[0]) == 2