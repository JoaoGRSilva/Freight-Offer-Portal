
import pytest

from services import postal_code as postal


# ============================================================
# normalizar_cep
# ============================================================

@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("01310100", "01310100"),
        ("1310100", "01310100"),
        ("01310-100", "01310100"),
        ("013.101-00", "01310100"),
        (1310100, "01310100"),
        (None, None),
        ("", None),
        ("123456", None),
        ("123456789", None),
        ("abcdefgh", None),
    ],
)
def test_normalizar_cep(entrada, esperado):
    assert postal.normalizar_cep(entrada) == esperado


# ============================================================
# _normalizar_cidade
# ============================================================

@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("São Paulo", "sao paulo"),
        ("  SÃO PAULO  ", "sao paulo"),
        ("Belo Horizonte", "belo horizonte"),
        ("  Rio   de   Janeiro  ", "rio de janeiro"),
        ("CURITIBA", "curitiba"),
        (None, ""),
        ("", ""),
    ],
)
def test_normalizar_cidade(entrada, esperado):
    assert postal._normalizar_cidade(entrada) == esperado


# ============================================================
# distancia_km
# ============================================================

def test_distancia_km_returns_none_when_coordinates_are_missing():
    assert postal.distancia_km(
        {"lat": None, "lon": -46.6},
        {"lat": -23.5, "lon": -46.6},
    ) is None


def test_distancia_km_returns_zero_for_same_point():
    ponto = {"lat": -23.5505, "lon": -46.6333}

    assert postal.distancia_km(ponto, ponto) == 0.0


def test_distancia_km_applies_road_factor():
    origem = {"lat": -23.5505, "lon": -46.6333}
    destino = {"lat": -22.9068, "lon": -43.1729}

    distancia_direta = postal.distancia_km(
        origem, destino, fator_rodoviario=1.0
    )
    distancia_rodoviaria = postal.distancia_km(
        origem, destino, fator_rodoviario=1.25
    )

    assert distancia_direta > 0
    assert distancia_rodoviaria == round(distancia_direta * 1.25, 1)



import json

from services import db


@pytest.fixture
def postal_test_db(tmp_path, monkeypatch):
    monkeypatch.setitem(
        db.DATABASES,
        "fretes",
        tmp_path / "postal_test.db",
    )



def test_con_creates_all_cache_tables(postal_test_db):
    with postal._con() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            ).fetchall()
        }

    assert {
        "cep_cache",
        "cidade_cache",
        "rota_trechos_cache",
    }.issubset(tables)


@pytest.mark.parametrize(
    ("tabela", "parametros", "esperado"),
    [
        ("cep_cache", ("01310100", '{"cidade": "São Paulo"}'), {"cidade": "São Paulo"}),
        ("cidade_cache", ("sao paulo", "SP", '{"lat": -23.5}'), {"lat": -23.5}),
        ("rota_trechos_cache", ("rota1", "[10.5, 20.0]"), [10.5, 20.0]),
    ],
)
def test_put_and_get_cache(postal_test_db, tabela, parametros, esperado):
    postal._put_cache(tabela, parametros)

    chave = {
        "cep_cache": (parametros[0],),
        "cidade_cache": parametros[:2],
        "rota_trechos_cache": (parametros[0],),
    }[tabela]

    assert postal._get_cache(tabela, "dados", chave) == esperado


def test_get_cache_returns_none_when_record_does_not_exist(postal_test_db):
    assert postal._get_cache(
        "cep_cache", "dados", ("99999999",)
    ) is None


def test_get_cache_returns_none_when_json_is_corrupted(postal_test_db):
    postal._put_cache(
        "cep_cache",
        ("01310100", "{json inválido"),
    )

    assert postal._get_cache(
        "cep_cache", "dados", ("01310100",)
    ) is None


@pytest.mark.parametrize(
    "tabela",
    ["tabela_invalida", "", None],
)
def test_get_cache_rejects_invalid_table(tabela):
    with pytest.raises(ValueError, match="Tabela de cache inválida"):
        postal._get_cache(tabela, "dados", ())


@pytest.mark.parametrize(
    "tabela",
    ["tabela_invalida", "", None],
)
def test_put_cache_rejects_invalid_table(tabela):
    with pytest.raises(ValueError, match="Tabela de cache inválida"):
        postal._put_cache(tabela, ())


from unittest.mock import Mock


def test_validar_cep_returns_data_from_brasilapi(monkeypatch, postal_test_db):
    resposta = Mock()
    resposta.status_code = 200
    resposta.json.return_value = {
        "city": "São Paulo",
        "state": "SP",
        "location": {
            "coordinates": {
                "latitude": "-23.5505",
                "longitude": "-46.6333",
            }
        },
    }

    monkeypatch.setattr(postal.SESSION, "get", lambda *a, **kw: resposta)
    monkeypatch.setattr(
        postal, "_completar_coordenadas_cep", lambda dados: dados
    )

    resultado = postal.validar_cep("01310-100")

    assert resultado == {
        "cidade": "São Paulo",
        "uf": "SP",
        "lat": -23.5505,
        "lon": -46.6333,
    }

    assert postal._get_cache(
        "cep_cache", "dados", ("01310100",)
    ) == resultado


def test_validar_cep_returns_empty_for_invalid_cep(monkeypatch):
    def unexpected_request(*args, **kwargs):
        pytest.fail("Não deveria consultar a API para CEP inválido")

    monkeypatch.setattr(postal.SESSION, "get", unexpected_request)

    assert postal.validar_cep("123") == {}


def test_validar_cep_returns_empty_for_http_error(monkeypatch):
    resposta = Mock()
    resposta.status_code = 404

    monkeypatch.setattr(postal.SESSION, "get", lambda *a, **kw: resposta)

    assert postal.validar_cep("01310100") == {}


def test_validar_cep_uses_cache_without_http_request(postal_test_db, monkeypatch):
    dados = {
        "cidade": "São Paulo",
        "uf": "SP",
        "lat": -23.5505,
        "lon": -46.6333,
    }

    postal._put_cache(
        "cep_cache",
        ("01310100", json.dumps(dados)),
    )

    def unexpected_request(*args, **kwargs):
        pytest.fail("Não deveria consultar a API quando existe cache")

    monkeypatch.setattr(postal.SESSION, "get", unexpected_request)

    assert postal.validar_cep("01310100") == dados


def test_validar_cep_returns_empty_when_api_json_is_invalid(monkeypatch):
    resposta = Mock()
    resposta.status_code = 200
    resposta.json.side_effect = ValueError("JSON inválido")

    monkeypatch.setattr(postal.SESSION, "get", lambda *a, **kw: resposta)

    assert postal.validar_cep("01310100") == {}


def test_validar_cep_handles_missing_coordinates(monkeypatch, postal_test_db):
    resposta = Mock()
    resposta.status_code = 200
    resposta.json.return_value = {
        "city": "São Paulo",
        "state": "SP",
        "location": {"coordinates": {}},
    }

    monkeypatch.setattr(postal.SESSION, "get", lambda *a, **kw: resposta)
    monkeypatch.setattr(
        postal, "_completar_coordenadas_cep", lambda dados: dados
    )

    resultado = postal.validar_cep("01310100")

    assert resultado["cidade"] == "São Paulo"
    assert resultado["uf"] == "SP"
    assert resultado["lat"] is None
    assert resultado["lon"] is None


@pytest.fixture
def nominatim_clock(monkeypatch):
    monkeypatch.setattr(postal, "_ULTIMA_CONSULTA_NOMINATIM", 0.0)
    monkeypatch.setattr(postal, "_NOMINATIM_BLOQUEADO_ATE", 0.0)
    monkeypatch.setattr(postal.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(postal.time, "sleep", lambda _: None)


def test_pesquisar_localizacao_returns_coordinates(
    monkeypatch, postal_test_db, nominatim_clock
):
    resposta = Mock()
    resposta.status_code = 200
    resposta.json.return_value = [{"lat": "-23.55", "lon": "-46.63"}]

    monkeypatch.setattr(postal.SESSION, "get", lambda *a, **kw: resposta)

    resultado = postal.pesquisar_localizacao("São Paulo", "sp")

    assert resultado == {
        "cidade": "São Paulo",
        "uf": "SP",
        "lat": -23.55,
        "lon": -46.63,
    }


def test_pesquisar_localizacao_returns_empty_when_city_is_missing(monkeypatch):
    monkeypatch.setattr(
        postal.SESSION,
        "get",
        lambda *a, **kw: pytest.fail("Não deveria consultar"),
    )

    assert postal.pesquisar_localizacao("", "SP") == {}


def test_pesquisar_localizacao_returns_empty_when_state_is_missing(monkeypatch):
    monkeypatch.setattr(
        postal.SESSION,
        "get",
        lambda *a, **kw: pytest.fail("Não deveria consultar"),
    )

    assert postal.pesquisar_localizacao("São Paulo", "") == {}


def test_pesquisar_localizacao_uses_original_cache_key(
    monkeypatch, postal_test_db
):
    dados = {"cidade": "São Paulo", "uf": "SP", "lat": -23.5, "lon": -46.6}

    postal._put_cache(
        "cidade_cache",
        ("são paulo", "SP", json.dumps(dados)),
    )

    monkeypatch.setattr(
        postal.SESSION,
        "get",
        lambda *a, **kw: pytest.fail("Não deveria consultar"),
    )

    assert postal.pesquisar_localizacao("São Paulo", "sp") == dados


def test_pesquisar_localizacao_uses_normalized_cache_key(
    monkeypatch, postal_test_db
):
    dados = {"cidade": "São Paulo", "uf": "SP", "lat": -23.5, "lon": -46.6}

    postal._put_cache(
        "cidade_cache",
        ("sao paulo", "SP", json.dumps(dados)),
    )

    monkeypatch.setattr(
        postal.SESSION,
        "get",
        lambda *a, **kw: pytest.fail("Não deveria consultar"),
    )

    assert postal.pesquisar_localizacao("São Paulo", "SP") == dados


@pytest.mark.parametrize("status_code", [403, 429])
def test_pesquisar_localizacao_blocks_after_http_rate_limit(
    monkeypatch, nominatim_clock, status_code, postal_test_db
):
    resposta = Mock()
    resposta.status_code = status_code

    monkeypatch.setattr(postal.SESSION, "get", lambda *a, **kw: resposta)

    resultado = postal.pesquisar_localizacao("Campinas", "SP")

    assert resultado == {}
    assert postal._NOMINATIM_BLOQUEADO_ATE == 3700.0


def test_pesquisar_localizacao_does_not_request_when_temporarily_blocked(
    monkeypatch, nominatim_clock, postal_test_db
):
    monkeypatch.setattr(postal, "_NOMINATIM_BLOQUEADO_ATE", 200.0)

    monkeypatch.setattr(
        postal.SESSION,
        "get",
        lambda *a, **kw: pytest.fail("Nominatim está bloqueado"),
    )

    assert postal.pesquisar_localizacao("Campinas", "SP") == {}


def test_pesquisar_localizacao_returns_empty_when_api_has_no_results(
    monkeypatch, nominatim_clock, postal_test_db
):
    resposta = Mock()
    resposta.status_code = 200
    resposta.json.return_value = []

    monkeypatch.setattr(postal.SESSION, "get", lambda *a, **kw: resposta)

    assert postal.pesquisar_localizacao("Campinas", "SP") == {}


def test_pesquisar_localizacao_handles_request_exception(
    monkeypatch, nominatim_clock, postal_test_db
):
    def failed_request(*args, **kwargs):
        raise postal.requests.RequestException("Falha de conexão")

    monkeypatch.setattr(postal.SESSION, "get", failed_request)

    assert postal.pesquisar_localizacao("Campinas", "SP") == {}


def test_pesquisar_localizacao_handles_invalid_coordinates(
    monkeypatch, nominatim_clock, postal_test_db
):
    resposta = Mock()
    resposta.status_code = 200
    resposta.json.return_value = [{"lat": "invalida", "lon": "-46.6"}]

    monkeypatch.setattr(postal.SESSION, "get", lambda *a, **kw: resposta)

    assert postal.pesquisar_localizacao("Campinas", "SP") == {}


def test_pesquisar_localizacao_persists_both_cache_keys(
    monkeypatch, postal_test_db, nominatim_clock, 
):
    resposta = Mock()
    resposta.status_code = 200
    resposta.json.return_value = [{"lat": "-22.9", "lon": "-47.0"}]

    monkeypatch.setattr(postal.SESSION, "get", lambda *a, **kw: resposta)

    resultado = postal.pesquisar_localizacao("Campinas", "SP")

    assert postal._get_cache(
        "cidade_cache", "dados", ("campinas", "SP")
    ) == resultado

    assert postal._get_cache(
        "cidade_cache", "dados", ("campinas", "SP")
    ) == resultado


def test_pesquisar_localizacao_waits_when_last_request_was_recent(
    monkeypatch, nominatim_clock, postal_test_db
):
    tempos = iter([100.0, 100.0, 100.0])
    monkeypatch.setattr(postal.time, "monotonic", lambda: next(tempos))
    monkeypatch.setattr(postal, "_ULTIMA_CONSULTA_NOMINATIM", 100.0)

    esperas = []
    monkeypatch.setattr(postal.time, "sleep", esperas.append)

    resposta = Mock()
    resposta.status_code = 200
    resposta.json.return_value = [{"lat": "-22.9", "lon": "-47.0"}]

    monkeypatch.setattr(postal.SESSION, "get", lambda *a, **kw: resposta)

    postal.pesquisar_localizacao("Campinas", "SP")

    assert esperas == pytest.approx([1.1])


def test_completar_coordenadas_returns_empty_for_invalid_data():
    assert postal._completar_coordenadas_cep(None) == {}
    assert postal._completar_coordenadas_cep("inválido") == {}


def test_completar_coordenadas_preserves_existing_coordinates(monkeypatch):
    dados = {
        "cidade": "São Paulo",
        "uf": "SP",
        "lat": -23.5,
        "lon": -46.6,
    }

    monkeypatch.setattr(
        postal,
        "pesquisar_localizacao",
        lambda *a: pytest.fail("Não deveria consultar a cidade"),
    )

    assert postal._completar_coordenadas_cep(dados) == dados


@pytest.mark.parametrize(
    "dados",
    [
        {"cidade": "São Paulo"},
        {"uf": "SP"},
        {},
    ],
)
def test_completar_coordenadas_preserves_data_without_city_or_state(
    monkeypatch, dados
):
    monkeypatch.setattr(
        postal,
        "pesquisar_localizacao",
        lambda *a: pytest.fail("Não deveria consultar"),
    )

    assert postal._completar_coordenadas_cep(dados) == dados


def test_completar_coordenadas_preserves_data_when_city_lookup_fails(
    monkeypatch
):
    dados = {"cidade": "Campinas", "uf": "SP"}

    monkeypatch.setattr(postal, "pesquisar_localizacao", lambda *a: {})

    assert postal._completar_coordenadas_cep(dados) == dados


def test_completar_coordenadas_uses_city_center(monkeypatch):
    dados = {"cidade": "Campinas", "uf": "SP"}

    monkeypatch.setattr(
        postal,
        "pesquisar_localizacao",
        lambda *a: {"lat": -22.9, "lon": -47.0},
    )

    resultado = postal._completar_coordenadas_cep(dados)

    assert resultado["lat"] == -22.9
    assert resultado["lon"] == -47.0
    assert resultado["coordenadas_aproximadas"] is True
    assert resultado["fonte_coordenadas"] == "centro_cidade_nominatim"

    # Não deve modificar o dicionário original.
    assert "lat" not in dados

@pytest.fixture
def pontos_rota():
    return [
        {"lat": -23.5505, "lon": -46.6333},
        {"lat": -22.9068, "lon": -43.1729},
    ]


@pytest.mark.parametrize(
    "pontos",
    [
        [],
        None,
        [{}],
        [{"lat": None, "lon": -46.6}, {"lat": -22.9, "lon": -43.2}],
        [{"lat": -23.5, "lon": -46.6}],
    ],
)
def test_trechos_rota_returns_none_for_invalid_points(monkeypatch, pontos):
    monkeypatch.setattr(
        postal.SESSION,
        "get",
        lambda *a, **kw: pytest.fail("Não deveria consultar OSRM"),
    )

    assert postal.trechos_rota_km(pontos) is None


@pytest.mark.parametrize(
    "pontos",
    [
        [{"lat": "invalida", "lon": -46.6}, {"lat": -22.9, "lon": -43.2}],
        [{"lat": -23.5, "lon": None}, {"lat": -22.9, "lon": -43.2}],
    ],
)
def test_trechos_rota_returns_none_for_invalid_coordinate_conversion(
    monkeypatch, pontos
):
    monkeypatch.setattr(
        postal.SESSION,
        "get",
        lambda *a, **kw: pytest.fail("Não deveria consultar OSRM"),
    )

    assert postal.trechos_rota_km(pontos) is None


def test_trechos_rota_uses_osrm_success(
    monkeypatch, pontos_rota, postal_test_db
):
    resposta = Mock()
    resposta.json.return_value = {
        "code": "Ok",
        "routes": [{
            "legs": [{"distance": 12500.0}],
        }],
    }

    monkeypatch.setattr(postal.SESSION, "get", lambda *a, **kw: resposta)

    resultado = postal.trechos_rota_km(pontos_rota)

    assert resultado == [12.5]


def test_trechos_rota_uses_cache(
    monkeypatch, pontos_rota, postal_test_db
):
    chave = ";".join(
        f'{float(p["lon"]):.5f},{float(p["lat"]):.5f}'
        for p in pontos_rota
    )

    postal._put_cache(
        "rota_trechos_cache",
        (chave, json.dumps([12.5])),
    )

    monkeypatch.setattr(
        postal.SESSION,
        "get",
        lambda *a, **kw: pytest.fail("Não deveria consultar OSRM"),
    )

    assert postal.trechos_rota_km(pontos_rota) == [12.5]


def test_trechos_rota_ignores_cache_with_wrong_number_of_legs(
    monkeypatch, pontos_rota, postal_test_db
):
    chave = ";".join(
        f'{float(p["lon"]):.5f},{float(p["lat"]):.5f}'
        for p in pontos_rota
    )

    postal._put_cache(
        "rota_trechos_cache",
        (chave, json.dumps([10.0, 20.0])),
    )

    resposta = Mock()
    resposta.json.return_value = {
        "code": "Ok",
        "routes": [{"legs": [{"distance": 15000.0}]}],
    }

    monkeypatch.setattr(postal.SESSION, "get", lambda *a, **kw: resposta)

    assert postal.trechos_rota_km(pontos_rota) == [15.0]


def test_trechos_rota_uses_fallback_when_osrm_returns_error(
    monkeypatch, pontos_rota
):
    resposta = Mock()
    resposta.raise_for_status.side_effect = postal.requests.RequestException(
        "OSRM indisponível"
    )

    monkeypatch.setattr(postal.SESSION, "get", lambda *a, **kw: resposta)

    resultado = postal.trechos_rota_km(pontos_rota)

    esperado = postal.distancia_km(
        pontos_rota[0],
        pontos_rota[1],
        fator_rodoviario=1.35,
    )

    assert resultado == [esperado]


def test_trechos_rota_uses_fallback_when_osrm_code_is_not_ok(
    monkeypatch, pontos_rota
):
    resposta = Mock()
    resposta.json.return_value = {"code": "NoRoute", "routes": []}

    monkeypatch.setattr(postal.SESSION, "get", lambda *a, **kw: resposta)

    resultado = postal.trechos_rota_km(pontos_rota)

    esperado = postal.distancia_km(
        pontos_rota[0],
        pontos_rota[1],
        fator_rodoviario=1.35,
    )

    assert resultado == [esperado]


def test_trechos_rota_uses_fallback_when_osrm_legs_are_incomplete(
    monkeypatch, pontos_rota
):
    resposta = Mock()
    resposta.json.return_value = {
        "code": "Ok",
        "routes": [{"legs": []}],
    }

    monkeypatch.setattr(postal.SESSION, "get", lambda *a, **kw: resposta)

    resultado = postal.trechos_rota_km(pontos_rota)

    esperado = postal.distancia_km(
        pontos_rota[0],
        pontos_rota[1],
        fator_rodoviario=1.35,
    )

    assert resultado == [esperado]


def test_trechos_rota_does_not_cache_fallback_estimates(
    monkeypatch, pontos_rota, postal_test_db
):
    resposta = Mock()
    resposta.raise_for_status.side_effect = postal.requests.RequestException(
        "OSRM indisponível"
    )

    monkeypatch.setattr(postal.SESSION, "get", lambda *a, **kw: resposta)

    postal.trechos_rota_km(pontos_rota)

    chave = ";".join(
        f'{float(p["lon"]):.5f},{float(p["lat"]):.5f}'
        for p in pontos_rota
    )

    assert postal._get_cache(
        "rota_trechos_cache", "trechos", (chave,)
    ) is None


def test_trechos_rota_caches_real_osrm_result(
    monkeypatch, pontos_rota, postal_test_db
):
    resposta = Mock()
    resposta.json.return_value = {
        "code": "Ok",
        "routes": [{"legs": [{"distance": 23500.0}]}],
    }

    monkeypatch.setattr(postal.SESSION, "get", lambda *a, **kw: resposta)

    resultado = postal.trechos_rota_km(pontos_rota)

    chave = ";".join(
        f'{float(p["lon"]):.5f},{float(p["lat"]):.5f}'
        for p in pontos_rota
    )

    assert resultado == [23.5]
    assert postal._get_cache(
        "rota_trechos_cache", "trechos", (chave,)
    ) == [23.5]


def test_distancia_rota_returns_none_when_route_is_invalid(monkeypatch):
    monkeypatch.setattr(postal, "trechos_rota_km", lambda *a: None)

    assert postal.distancia_rota_km([]) is None


def test_distancia_rota_sums_route_segments(monkeypatch):
    monkeypatch.setattr(
        postal,
        "trechos_rota_km",
        lambda *a: [10.2, 20.3, 30.4],
    )

    assert postal.distancia_rota_km([{}, {}]) == 60.9

def test_validar_cep_returns_empty_when_cached_data_is_not_dict(monkeypatch):
    from services import postal_code

    monkeypatch.setattr(
        postal_code,
        "_get_cache",
        lambda *args: ["dados", "invalidos"],
    )

    def fail_if_called(*args, **kwargs):
        pytest.fail("A API não deveria ser chamada quando o cache é inválido")

    monkeypatch.setattr(postal_code.SESSION, "get", fail_if_called)

    assert postal_code.validar_cep("01310100") == {}

def test_validar_cep_updates_cache_when_coordinates_are_completed(monkeypatch):
    from services import postal_code

    cached = {
        "cep": "01310100",
        "cidade": "São Paulo",
        "estado": "SP",
    }

    completed = {
        **cached,
        "lat": -23.5505,
        "lon": -46.6333,
    }

    saved = []

    monkeypatch.setattr(
        postal_code,
        "_get_cache",
        lambda *args: cached,
    )

    monkeypatch.setattr(
        postal_code,
        "_completar_coordenadas_cep",
        lambda dados: completed,
    )

    monkeypatch.setattr(
        postal_code,
        "_put_cache",
        lambda tabela, valores: saved.append((tabela, valores)),
    )

    result = postal_code.validar_cep("01310100")

    assert result == completed
    assert len(saved) == 1
    assert saved[0][0] == "cep_cache"
    assert saved[0][1][0] == "01310100"
    assert '"lat": -23.5505' in saved[0][1][1]
    assert '"lon": -46.6333' in saved[0][1][1]

def test_trechos_rota_returns_none_when_fallback_distance_is_unavailable(
    monkeypatch,
    postal_test_db,
):
    from services import postal_code

    pontos = [
        {"lat": -23.5505, "lon": -46.6333},
        {"lat": -22.9068, "lon": -43.1729},
    ]

    monkeypatch.setattr(
        postal_code,
        "_get_cache",
        lambda *args: None,
    )

    monkeypatch.setattr(
        postal_code.SESSION,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            postal_code.requests.RequestException("OSRM indisponível")
        ),
    )

    monkeypatch.setattr(
        postal_code,
        "distancia_km",
        lambda *args, **kwargs: None,
    )

    assert postal_code.trechos_rota_km(pontos) is None