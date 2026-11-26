
import numpy as np
import pandas as pd
import pytest
from services import carrier_recommendation as carrier_module
from services import carrier_recommendation as recommendation


# ============================================================
# CEP
# ============================================================

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        ("", ""),
        ("   ", ""),
        (np.nan, ""),
        (pd.NA, ""),
        ("01310-100", "01310100"),
        ("01310100", "01310100"),
        (1310100, "01310100"),
        (1310100.0, "01310100"),
        ("CEP 01310-100", "01310100"),
        ("abc", ""),
    ],
)
def test_clean_zip(value, expected):
    assert recommendation._clean_zip(value) == expected


@pytest.mark.parametrize(
    ("zip_code", "expected"),
    [
        ("01000-000", "SP"),
        ("19999-999", "SP"),
        ("20000-000", "RJ"),
        ("29000-000", "ES"),
        ("30000-000", "MG"),
        ("40000-000", "BA"),
        ("49000-000", "SE"),
        ("50000-000", "PE"),
        ("57000-000", "AL"),
        ("58000-000", "PB"),
        ("59000-000", "RN"),
        ("60000-000", "CE"),
        ("64000-000", "PI"),
        ("65000-000", "MA"),
        ("66000-000", "PA"),
        ("68900-000", "AP"),
        ("69000-000", "AM"),
        ("69300-000", "RR"),
        ("69400-000", "AM"),
        ("69900-000", "AC"),
        ("70000-000", "DF"),
        ("72800-000", "GO"),
        ("73000-000", "DF"),
        ("73700-000", "GO"),
        ("76800-000", "RO"),
        ("77000-000", "TO"),
        ("78000-000", "MT"),
        ("78900-000", "RO"),
        ("79000-000", "MS"),
        ("80000-000", "PR"),
        ("88000-000", "SC"),
        ("90000-000", "RS"),
    ],
)
def test_zip_to_state_covers_brazilian_ranges(zip_code, expected):
    assert recommendation.zip_to_state(zip_code) == expected


@pytest.mark.parametrize(
    "zip_code",
    [
        None,
        "",
        "abc",
        "00000-000",
    ],
)
def test_zip_to_state_returns_none_for_invalid_or_unmapped_zip(zip_code):
    assert recommendation.zip_to_state(zip_code) is None


def test_zip_to_state_accepts_last_zip_range():
    assert recommendation.zip_to_state("99999-999") == "RS"


# ============================================================
# CONVERSÃO NUMÉRICA
# ============================================================

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (np.nan, None),
        (pd.NA, None),
        ("", None),
        ("abc", None),
        ("12.5", 12.5),
        (10, 10.0),
        (10.5, 10.5),
        (True, 1.0),
    ],
)
def test_to_float(value, expected):
    assert recommendation._to_float(value) == expected


# ============================================================
# FORMATAÇÃO
# ============================================================

@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "—"),
        (np.nan, "—"),
        (0.5, "50%"),
        (0.125, "12%"),
        (1, "100%"),
        (-0.25, "-25%"),
    ],
)
def test_pct(value, expected):
    assert recommendation._pct(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "—"),
        (np.nan, "—"),
        (0, "R$ 0,00"),
        (1234.5, "R$ 1.234,50"),
        (1234567.89, "R$ 1.234.567,89"),
        (-100.5, "R$ -100,50"),
    ],
)
def test_brl(value, expected):
    assert recommendation._brl(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (np.nan, None),
        (100, 1.0),
        (250.5, 2.505),
        (0, 0),
    ],
)
def test_per_kg(value, expected):
    assert recommendation._per_kg(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "0"),
        (1234.5, "1.234"),
        (1000000, "1.000.000"),
        (-1234.5, "-1.234"),
    ],
)
def test_thousands(value, expected):
    assert recommendation._thousands(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (4.43, "4,4x"),
        (1, "1,0x"),
        (0, "0,0x"),
        (-2.25, "-2,2x"),
    ],
)
def test_times(value, expected):
    assert recommendation._times(value) == expected


# ============================================================
# ESCOPO
# ============================================================

@pytest.mark.parametrize(
    ("key", "level", "expected"),
    [
        ("zip", 5, "CEP5"),
        ("zip", 4, "CEP4"),
        ("zip", 3, "CEP3"),
        ("state", None, "uf"),
        ("plant", None, "uf"),
    ],
)
def test_scope_name(key, level, expected):
    assert recommendation._scope_name(key, level) == expected


# ============================================================
# NORMALIZAÇÃO DE TRANSPORTADORAS
# ============================================================

def test_normalize_carrier_removes_empty_names_and_trims_whitespace():
    original = pd.DataFrame(
        {
            recommendation.CARRIER_COL: [
                " Transportadora A ",
                "",
                None,
                "   ",
                "Transportadora B",
            ],
            "valor": [1, 2, 3, 4, 5],
        }
    )

    result = recommendation._normalize_carrier(original)

    assert result[recommendation.CARRIER_COL].tolist() == [
        "Transportadora A",
        "Transportadora B",
    ]
    assert result["valor"].tolist() == [1, 5]


def test_normalize_carrier_applies_configured_aliases(monkeypatch):
    monkeypatch.setattr(
        recommendation,
        "CARRIER_ALIASES",
        {"TRANSPORTADORA A LTDA": "Transportadora A"},
    )

    original = pd.DataFrame(
        {
            recommendation.CARRIER_COL: [
                "TRANSPORTADORA A LTDA",
                "Transportadora B",
            ],
        }
    )

    result = recommendation._normalize_carrier(original)

    assert result[recommendation.CARRIER_COL].tolist() == [
        "Transportadora A",
        "Transportadora B",
    ]


# ============================================================
# PREPARAÇÃO DO HISTÓRICO DE VIAGENS (TRIPS)
# ============================================================

def _trips_dataframe(**overrides):
    """DataFrame mínimo válido para os testes de _prepare_trips."""
    data = {
        "freight_id": ["F001", "F002"],
        recommendation.CARRIER_COL: [
            "Transportadora A",
            "Transportadora B",
        ],
        "issuing_plant_code": [" 1210 ", " 1211 "],
        "cep_destino": ["01310-100", "20000-000"],
        "sla_frete": ["1", "abc"],
        "valor_pago": ["1500.50", "inválido"],
        "quantidade": ["10000", "20000"],
        "data_fim": ["2026-01-10", "data inválida"],
    }
    data.update(overrides)
    return pd.DataFrame(data)


def test_prepare_trips_returns_empty_dataframe_for_none_or_empty():
    assert recommendation._prepare_trips(None).empty
    assert recommendation._prepare_trips(pd.DataFrame()).empty


def test_prepare_trips_normalizes_columns_and_numeric_values():
    result = recommendation._prepare_trips(_trips_dataframe())

    assert result["issuing_plant_code"].tolist() == ["1210", "1211"]
    assert result["cep_destino"].tolist() == ["01310100", "20000000"]

    assert result["sla_ok"].iloc[0] == 1.0
    assert pd.isna(result["sla_ok"].iloc[1])

    assert result["valor_pago"].iloc[0] == 1500.50
    assert result["valor_pago"].iloc[1] == 0

    assert result["peso_kg"].tolist() == [10000, 20000]


def test_prepare_trips_converts_dates_and_preserves_invalid_dates_as_nat():
    result = recommendation._prepare_trips(_trips_dataframe())

    assert pd.Timestamp("2026-01-10") == result["data_fim"].iloc[0]
    assert pd.isna(result["data_fim"].iloc[1])


def test_prepare_trips_derives_destination_state_from_primary_zip():
    result = recommendation._prepare_trips(
        _trips_dataframe(cep_destino=["01310-100", "20000-000"])
    )

    assert result[recommendation.DEST_STATE_COL].tolist() == ["SP", "RJ"]


def test_prepare_trips_derives_state_from_first_zip_in_ceps_destino():
    result = recommendation._prepare_trips(
        _trips_dataframe(
            cep_destino=["", ""],
            ceps_destino=[
                "01310-100|20000-000",
                "29000-000|30000-000",
            ],
        )
    )

    assert result[recommendation.DEST_STATE_COL].tolist() == ["SP", "ES"]


def test_prepare_trips_keeps_existing_destination_state():
    result = recommendation._prepare_trips(
        _trips_dataframe(
            uf_destino=["MG", "PR"],
        )
    )

    assert result[recommendation.DEST_STATE_COL].tolist() == ["MG", "PR"]


def test_prepare_trips_uses_quantity_in_preference_to_existing_weight():
    result = recommendation._prepare_trips(
        _trips_dataframe(
            quantidade=["1234", "5678"],
            peso_kg=[999, 888],
        )
    )

    assert result["peso_kg"].tolist() == [1234, 5678]


def test_prepare_trips_creates_missing_weight_as_nan():
    result = recommendation._prepare_trips(
        _trips_dataframe().drop(columns=["quantidade"])
    )

    assert result["peso_kg"].isna().all()


def test_prepare_trips_removes_rows_without_carrier():
    result = recommendation._prepare_trips(
        _trips_dataframe(
            **{
                recommendation.CARRIER_COL: [
                    "Transportadora A",
                    "   ",
                ]
            }
        )
    )

    assert len(result) == 1
    assert result[recommendation.CARRIER_COL].tolist() == [
        "Transportadora A"
    ]


def test_prepare_trips_applies_carrier_aliases(monkeypatch):
    monkeypatch.setattr(
        recommendation,
        "CARRIER_ALIASES",
        {"TRANSPORTADORA A LTDA": "Transportadora A"},
    )

    result = recommendation._prepare_trips(
        _trips_dataframe(
            **{
                recommendation.CARRIER_COL: [
                    "TRANSPORTADORA A LTDA",
                    "Transportadora B",
                ]
            }
        )
    )

    assert result[recommendation.CARRIER_COL].tolist() == [
        "Transportadora A",
        "Transportadora B",
    ]


def test_prepare_trips_does_not_modify_original_dataframe():
    original = _trips_dataframe()
    before = original.copy(deep=True)

    recommendation._prepare_trips(original)

    pd.testing.assert_frame_equal(original, before)


# ============================================================
# PREPARAÇÃO DO HISTÓRICO DETALHADO (ROWS)
# ============================================================

def _rows_dataframe(**overrides):
    """DataFrame mínimo válido para os testes de _prepare_rows."""
    data = {
        "freight_id": [" F001 ", " F002 ", " F003 "],
        recommendation.CARRIER_COL: [
            "Transportadora A",
            "Transportadora B",
            "Transportadora C",
        ],
        "valor_pago": ["1000.50", "inválido", None],
        "peso_kg": ["10000", "20000", "peso inválido"],
        recommendation.GROUP_COL: ["VBR6", "VBR7", "VBR6"],
        "coluna_extra": ["x", "y", "z"],
    }
    data.update(overrides)
    return pd.DataFrame(data)


def test_prepare_rows_returns_expected_empty_structure_for_none_or_empty():
    expected_columns = [
        "freight_id",
        recommendation.CARRIER_COL,
        "valor_pago",
        "peso_kg",
    ]

    result_none = recommendation._prepare_rows(None)
    result_empty = recommendation._prepare_rows(pd.DataFrame())

    assert result_none.empty
    assert result_empty.empty
    assert result_none.columns.tolist() == expected_columns
    assert result_empty.columns.tolist() == expected_columns


def test_prepare_rows_normalizes_ids_and_numeric_values():
    result = recommendation._prepare_rows(_rows_dataframe())

    assert result["freight_id"].tolist() == ["F001", "F002", "F003"]
    assert result["valor_pago"].tolist() == [1000.50, 0, 0]

    assert result["peso_kg"].iloc[0] == 10000
    assert result["peso_kg"].iloc[1] == 20000
    assert pd.isna(result["peso_kg"].iloc[2])


def test_prepare_rows_keeps_group_and_ignores_unrelated_columns():
    result = recommendation._prepare_rows(_rows_dataframe())

    assert recommendation.GROUP_COL in result.columns
    assert result[recommendation.GROUP_COL].tolist() == [
        "VBR6",
        "VBR7",
        "VBR6",
    ]
    assert "coluna_extra" not in result.columns


def test_prepare_rows_works_without_optional_group_column():
    source = _rows_dataframe().drop(
        columns=[recommendation.GROUP_COL]
    )

    result = recommendation._prepare_rows(source)

    assert recommendation.GROUP_COL not in result.columns
    assert len(result) == 3


def test_prepare_rows_removes_rows_without_carrier():
    result = recommendation._prepare_rows(
        _rows_dataframe(
            **{
                recommendation.CARRIER_COL: [
                    "Transportadora A",
                    "",
                    None,
                ]
            }
        )
    )

    assert len(result) == 1
    assert result["freight_id"].tolist() == ["F001"]


def test_prepare_rows_applies_carrier_aliases(monkeypatch):
    monkeypatch.setattr(
        recommendation,
        "CARRIER_ALIASES",
        {"TRANSPORTADORA A LTDA": "Transportadora A"},
    )

    result = recommendation._prepare_rows(
        _rows_dataframe(
            **{
                recommendation.CARRIER_COL: [
                    "TRANSPORTADORA A LTDA",
                    "Transportadora B",
                    "Transportadora C",
                ]
            }
        )
    )

    assert result[recommendation.CARRIER_COL].tolist() == [
        "Transportadora A",
        "Transportadora B",
        "Transportadora C",
    ]


def test_prepare_rows_does_not_modify_original_dataframe():
    original = _rows_dataframe()
    before = original.copy(deep=True)

    recommendation._prepare_rows(original)

    pd.testing.assert_frame_equal(original, before)


def test_prepare_rows_does_not_include_unrequested_source_columns():
    result = recommendation._prepare_rows(_rows_dataframe())

    assert result.columns.tolist() == [
        "freight_id",
        recommendation.CARRIER_COL,
        "valor_pago",
        "peso_kg",
        recommendation.GROUP_COL,
    ]

# ============================================================
# CACHE EM MEMÓRIA
# ============================================================

@pytest.fixture
def isolated_recommendation_cache():
    """Preserva e restaura o cache global entre os testes."""
    original = {
        name: {
            "df": (
                entry["df"].copy(deep=True)
                if isinstance(entry["df"], pd.DataFrame)
                else entry["df"]
            ),
            "loaded_at": entry["loaded_at"],
        }
        for name, entry in recommendation._cache.items()
    }

    recommendation.reload_history()

    yield recommendation._cache

    recommendation._cache.clear()
    recommendation._cache.update(original)


def test_get_cached_loads_data_when_cache_is_empty(
    isolated_recommendation_cache,
    monkeypatch,
):
    now = [100.0]
    monkeypatch.setattr(
        recommendation.time,
        "monotonic",
        lambda: now[0],
    )

    expected = pd.DataFrame({"valor": [10]})
    calls = []

    def load():
        calls.append(True)
        return expected

    result = recommendation._get_cached("trips", load)

    assert result is expected
    assert len(calls) == 1
    assert recommendation._cache["trips"]["df"] is expected
    assert recommendation._cache["trips"]["loaded_at"] == 100.0


def test_get_cached_reuses_valid_cache_without_loading_again(
    isolated_recommendation_cache,
    monkeypatch,
):
    now = [100.0]
    monkeypatch.setattr(
        recommendation.time,
        "monotonic",
        lambda: now[0],
    )

    expected = pd.DataFrame({"valor": [10]})
    calls = []

    def load():
        calls.append(True)
        return expected

    first = recommendation._get_cached("trips", load)

    now[0] += recommendation.HISTORY_TTL_SEC - 1

    second = recommendation._get_cached("trips", load)

    assert first is expected
    assert second is expected
    assert len(calls) == 1


def test_get_cached_reloads_after_ttl_expiration(
    isolated_recommendation_cache,
    monkeypatch,
):
    now = [100.0]
    monkeypatch.setattr(
        recommendation.time,
        "monotonic",
        lambda: now[0],
    )

    first_data = pd.DataFrame({"valor": [10]})
    second_data = pd.DataFrame({"valor": [20]})
    results = iter([first_data, second_data])
    calls = []

    def load():
        calls.append(True)
        return next(results)

    first = recommendation._get_cached("trips", load)

    now[0] += recommendation.HISTORY_TTL_SEC + 1

    second = recommendation._get_cached("trips", load)

    assert first is first_data
    assert second is second_data
    assert len(calls) == 2
    assert recommendation._cache["trips"]["loaded_at"] == now[0]


def test_get_cached_does_not_reload_at_exact_ttl_boundary(
    isolated_recommendation_cache,
    monkeypatch,
):
    now = [100.0]
    monkeypatch.setattr(
        recommendation.time,
        "monotonic",
        lambda: now[0],
    )

    expected = pd.DataFrame({"valor": [10]})
    calls = []

    def load():
        calls.append(True)
        return expected

    recommendation._get_cached("trips", load)

    now[0] += recommendation.HISTORY_TTL_SEC

    result = recommendation._get_cached("trips", load)

    assert result is expected
    assert len(calls) == 1


def test_get_cached_retries_when_initial_load_fails(
    isolated_recommendation_cache,
    monkeypatch,
):
    now = [100.0]
    monkeypatch.setattr(
        recommendation.time,
        "monotonic",
        lambda: now[0],
    )

    calls = []

    def failing_load():
        calls.append("failure")
        raise RuntimeError("Falha de leitura")

    with pytest.raises(RuntimeError, match="Falha de leitura"):
        recommendation._get_cached("trips", failing_load)

    assert recommendation._cache["trips"]["df"] is None

    expected = pd.DataFrame({"valor": [30]})

    def successful_load():
        calls.append("success")
        return expected

    result = recommendation._get_cached(
        "trips",
        successful_load,
    )

    assert result is expected
    assert calls == ["failure", "success"]


def test_get_cached_preserves_old_data_when_expired_reload_fails(
    isolated_recommendation_cache,
    monkeypatch,
):
    now = [100.0]
    monkeypatch.setattr(
        recommendation.time,
        "monotonic",
        lambda: now[0],
    )

    old_data = pd.DataFrame({"valor": [10]})

    recommendation._cache["trips"]["df"] = old_data
    recommendation._cache["trips"]["loaded_at"] = 100.0

    now[0] += recommendation.HISTORY_TTL_SEC + 1

    def failing_load():
        raise RuntimeError("Falha na atualização")

    with pytest.raises(RuntimeError, match="Falha na atualização"):
        recommendation._get_cached("trips", failing_load)

    assert recommendation._cache["trips"]["df"] is old_data
    assert recommendation._cache["trips"]["loaded_at"] == 100.0


def test_trip_history_uses_consolidated_loader(
    isolated_recommendation_cache,
    monkeypatch,
):
    expected = pd.DataFrame(
        {
            "freight_id": ["F001"],
            recommendation.CARRIER_COL: ["Transportadora A"],
            "issuing_plant_code": ["1210"],
            "cep_destino": ["01310100"],
            "sla_frete": [True],
            "valor_pago": [1000],
            "quantidade": [10000],
        }
    )

    calls = []

    monkeypatch.setattr(
        recommendation,
        "obter_historico_consolidado",
        lambda: calls.append(True) or expected,
    )

    first = recommendation._trip_history()
    second = recommendation._trip_history()

    assert len(calls) == 1
    assert first is second
    assert first["freight_id"].tolist() == ["F001"]


def test_row_history_uses_detailed_loader(
    isolated_recommendation_cache,
    monkeypatch,
):
    expected = pd.DataFrame(
        {
            "freight_id": ["F001"],
            recommendation.CARRIER_COL: ["Transportadora A"],
            "valor_pago": [1000],
            "peso_kg": [10000],
        }
    )

    calls = []

    monkeypatch.setattr(
        recommendation,
        "obter_historico_detalhado",
        lambda: calls.append(True) or expected,
    )

    first = recommendation._row_history()
    second = recommendation._row_history()

    assert len(calls) == 1
    assert first is second
    assert first["freight_id"].tolist() == ["F001"]


def test_trip_and_row_history_have_independent_caches(
    isolated_recommendation_cache,
    monkeypatch,
):
    trips_calls = []
    rows_calls = []

    trips = pd.DataFrame(
        {
            "freight_id": ["F001"],
            recommendation.CARRIER_COL: ["Transportadora A"],
            "issuing_plant_code": ["1210"],
            "cep_destino": ["01310100"],
            "sla_frete": [True],
            "valor_pago": [1000],
            "quantidade": [10000],
        }
    )

    rows = pd.DataFrame(
        {
            "freight_id": ["F001"],
            recommendation.CARRIER_COL: ["Transportadora A"],
            "valor_pago": [1000],
            "peso_kg": [10000],
        }
    )

    monkeypatch.setattr(
        recommendation,
        "obter_historico_consolidado",
        lambda: trips_calls.append(True) or trips,
    )
    monkeypatch.setattr(
        recommendation,
        "obter_historico_detalhado",
        lambda: rows_calls.append(True) or rows,
    )

    trip_result = recommendation._trip_history()

    assert len(trips_calls) == 1
    assert len(rows_calls) == 0

    row_result = recommendation._row_history()

    assert len(trips_calls) == 1
    assert len(rows_calls) == 1

    assert trip_result is recommendation._cache["trips"]["df"]
    assert row_result is recommendation._cache["rows"]["df"]


def test_reload_history_invalidates_both_caches(
    isolated_recommendation_cache,
):
    trips = pd.DataFrame({"valor": [1]})
    rows = pd.DataFrame({"valor": [2]})

    recommendation._cache["trips"] = {
        "df": trips,
        "loaded_at": 100.0,
    }
    recommendation._cache["rows"] = {
        "df": rows,
        "loaded_at": 200.0,
    }

    recommendation.reload_history()

    for entry in recommendation._cache.values():
        assert entry["df"] is None
        assert entry["loaded_at"] == 0.0


def test_reload_history_forces_both_histories_to_load_again(
    isolated_recommendation_cache,
    monkeypatch,
):
    trips_calls = []
    rows_calls = []

    trips = pd.DataFrame(
        {
            "freight_id": ["F001"],
            recommendation.CARRIER_COL: ["Transportadora A"],
            "issuing_plant_code": ["1210"],
            "cep_destino": ["01310100"],
            "sla_frete": [True],
            "valor_pago": [1000],
            "quantidade": [10000],
        }
    )

    rows = pd.DataFrame(
        {
            "freight_id": ["F001"],
            recommendation.CARRIER_COL: ["Transportadora A"],
            "valor_pago": [1000],
            "peso_kg": [10000],
        }
    )

    monkeypatch.setattr(
        recommendation,
        "obter_historico_consolidado",
        lambda: trips_calls.append(True) or trips,
    )
    monkeypatch.setattr(
        recommendation,
        "obter_historico_detalhado",
        lambda: rows_calls.append(True) or rows,
    )

    recommendation._trip_history()
    recommendation._row_history()

    assert len(trips_calls) == 1
    assert len(rows_calls) == 1

    recommendation.reload_history()

    recommendation._trip_history()
    recommendation._row_history()

    assert len(trips_calls) == 2
    assert len(rows_calls) == 2


# ============================================================
# FILTRO DE PERÍODO
# ============================================================

def test_filter_period_returns_empty_dataframe_unchanged():
    original = pd.DataFrame()

    result = recommendation._filter_period(original, 12)

    assert result is original


def test_filter_period_returns_dataframe_unchanged_without_date_column():
    original = pd.DataFrame({"valor": [10, 20]})

    result = recommendation._filter_period(original, 12)

    assert result is original
    pd.testing.assert_frame_equal(result, original)


def test_filter_period_returns_dataframe_unchanged_when_all_dates_are_nat():
    original = pd.DataFrame(
        {
            "data_fim": pd.to_datetime(
                [None, None]
            ),
            "valor": [10, 20],
        }
    )

    result = recommendation._filter_period(original, 12)

    assert result is original
    pd.testing.assert_frame_equal(result, original)


def test_filter_period_keeps_only_records_inside_period():
    original = pd.DataFrame(
        {
            "freight_id": ["ANTIGO", "LIMITE", "RECENTE"],
            "data_fim": pd.to_datetime(
                [
                    "2024-01-01",
                    "2025-01-01",
                    "2025-06-01",
                ]
            ),
        }
    )

    result = recommendation._filter_period(original, 12)

    assert result["freight_id"].tolist() == [
        "LIMITE",
        "RECENTE",
    ]


def test_filter_period_uses_latest_valid_date_as_reference():
    original = pd.DataFrame(
        {
            "freight_id": ["ANTIGO", "RECENTE", "SEM_DATA"],
            "data_fim": pd.to_datetime(
                [
                    "2024-01-01",
                    "2025-06-01",
                    None,
                ]
            ),
        }
    )

    result = recommendation._filter_period(original, 12)

    assert result["freight_id"].tolist() == [
        "RECENTE",
    ]


def test_filter_period_returns_copy_when_filtering():
    original = pd.DataFrame(
        {
            "freight_id": ["ANTIGO", "RECENTE"],
            "data_fim": pd.to_datetime(
                ["2024-01-01", "2025-06-01"]
            ),
        }
    )

    result = recommendation._filter_period(original, 12)

    assert result is not original
    pd.testing.assert_frame_equal(
        original,
        pd.DataFrame(
            {
                "freight_id": ["ANTIGO", "RECENTE"],
                "data_fim": pd.to_datetime(
                    ["2024-01-01", "2025-06-01"]
                ),
            }
        ),
    )

# ============================================================
# ANALYTICS.HISTORY — FIXTURES E DADOS
# ============================================================

from analytics import history as history_module


def _history_dataframe():
    """Base de exemplo com múltiplos fretes e granularidades."""
    return pd.DataFrame(
        {
            "freight_id": [
                "F001",
                "F001",
                "F002",
                "F003",
            ],
            "pd_header": [
                "P001",
                "P002",
                "P003",
                "P004",
            ],
            "issuing_plant_code": [
                "1210",
                "1210",
                "1210",
                "1211",
            ],
            "service_agent_description": [
                "Transportadora A",
                "Transportadora A",
                "Transportadora B",
                "Transportadora C",
            ],
            "sla_met": pd.Series(
                [True, False, True, pd.NA],
                dtype="boolean",
            ),
            "negotiated_value": [
                1000.0,
                500.0,
                2000.0,
                3000.0,
            ],
            "quantity": [
                10000.0,
                5000.0,
                20000.0,
                30000.0,
            ],
            "service_agent_group": [
                "VBR6",
                "VBR6",
                "VBR6",
                "VBR7",
            ],
            "customer_city": [
                "Campinas",
                "Jundiaí",
                "São Paulo",
                "Maringá",
            ],
            "cep": [
                "13053050",
                "13280000",
                "01000000",
                "87065170",
            ],
            "created_on": pd.to_datetime(
                [
                    "2025-01-01",
                    "2025-01-02",
                    "2025-02-01",
                    "2025-03-01",
                ]
            ),
            "due_date": pd.to_datetime(
                [
                    "2025-01-10",
                    "2025-01-11",
                    "2025-02-10",
                    "2025-03-10",
                ]
            ),
            "finish_date": pd.to_datetime(
                [
                    "2025-01-09",
                    "2025-01-12",
                    "2025-02-09",
                    None,
                ]
            ),
            "billing_date": pd.to_datetime(
                [
                    "2025-01-15",
                    "2025-01-16",
                    "2025-02-15",
                    None,
                ]
            ),
        }
    )


# ============================================================
# analytics.history — LISTA ÚNICA DE TEXTOS
# ============================================================

@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["Campinas", "Campinas", "Jundiaí"], "Campinas | Jundiaí"),
        ([" B ", "A", "B"], "A | B"),
        ([None, None], ""),
        (["", " ", None], ""),
        (["nan", "None", "Campinas"], "Campinas"),
        ([1, 2, 1], "1 | 2"),
    ],
)
def test_lista_unica_texto(values, expected):
    result = history_module._lista_unica_texto(
        pd.Series(values, dtype="object")
    )

    assert result == expected


# ============================================================
# analytics.history — CARREGAMENTO DO PARQUET
# ============================================================

def test_carregar_historico_reads_configured_parquet_columns(
    monkeypatch,
):
    source = _history_dataframe()
    captured = {}

    def fake_read_parquet(path, columns=None):
        captured["path"] = path
        captured["columns"] = columns
        return source.copy()

    monkeypatch.setattr(
        history_module.pd,
        "read_parquet",
        fake_read_parquet,
    )

    result = history_module.carregar_historico()

    assert captured["path"] == history_module.C.PARQUET_PATH
    assert captured["columns"] == history_module.COLUNAS
    assert len(result) == 4


def test_carregar_historico_normalizes_ids_and_plant_codes(
    monkeypatch,
):
    source = _history_dataframe()

    source["freight_id"] = [
        " F001 ",
        " F001 ",
        " F002 ",
        " F003 ",
    ]
    source["pd_header"] = [
        " P001 ",
        " P002 ",
        " P003 ",
        " P004 ",
    ]
    source["issuing_plant_code"] = [
        " 1210 ",
        " 1210 ",
        " 1210 ",
        " 1211 ",
    ]

    monkeypatch.setattr(
        history_module.pd,
        "read_parquet",
        lambda *args, **kwargs: source.copy(),
    )

    result = history_module.carregar_historico()

    assert result["freight_id"].tolist() == [
        "F001", "F001", "F002", "F003"
    ]
    assert result["pd_header"].tolist() == [
        "P001", "P002", "P003", "P004"
    ]
    assert result["issuing_plant_code"].tolist() == [
        "1210", "1210", "1210", "1211"
    ]


def test_carregar_historico_removes_rows_without_carrier(
    monkeypatch,
):
    source = _history_dataframe()

    source.loc[0, "service_agent_description"] = None
    source.loc[1, "service_agent_description"] = "   "

    monkeypatch.setattr(
        history_module.pd,
        "read_parquet",
        lambda *args, **kwargs: source.copy(),
    )

    result = history_module.carregar_historico()

    assert len(result) == 2
    assert result["freight_id"].tolist() == ["F002", "F003"]


def test_carregar_historico_converts_numeric_columns(
    monkeypatch,
):
    source = _history_dataframe()

    source["negotiated_value"] = [
        "1000",
        "inválido",
        None,
        "3000",
    ]
    source["quantity"] = [
        "10000",
        "inválido",
        None,
        "30000",
    ]

    monkeypatch.setattr(
        history_module.pd,
        "read_parquet",
        lambda *args, **kwargs: source.copy(),
    )

    result = history_module.carregar_historico()

    assert result["negotiated_value"].tolist() == [
        1000.0, 0.0, 0.0, 3000.0
    ]
    assert result["quantity"].tolist() == [
        10000.0, 0.0, 0.0, 30000.0
    ]


def test_carregar_historico_converts_sla_and_dates(
    monkeypatch,
):
    source = _history_dataframe()

    source["finish_date"] = [
        "2025-01-09",
        "data inválida",
        "2025-02-09",
        None,
    ]

    monkeypatch.setattr(
        history_module.pd,
        "read_parquet",
        lambda *args, **kwargs: source.copy(),
    )

    result = history_module.carregar_historico()

    assert str(result["sla_met"].dtype) == "boolean"
    assert pd.Timestamp("2025-01-09") == result["finish_date"].iloc[0]
    assert pd.isna(result["finish_date"].iloc[1])
    assert pd.isna(result["finish_date"].iloc[3])


def test_carregar_historico_normalizes_zip_codes(
    monkeypatch,
):
    source = _history_dataframe()

    source["cep"] = [
        "13053-050",
        "13280000",
        None,
        "abc",
    ]

    monkeypatch.setattr(
        history_module.pd,
        "read_parquet",
        lambda *args, **kwargs: source.copy(),
    )

    result = history_module.carregar_historico()

    assert result["cep"].tolist() == [
        "13053050",
        "13280000",
        "",
        "",
    ]


# ============================================================
# analytics.history — HISTÓRICO DETALHADO
# ============================================================

def test_preparar_historico_detalhado_returns_empty_dataframe():
    result = history_module.preparar_historico_detalhado(
        pd.DataFrame()
    )

    assert result.empty


def test_preparar_historico_detalhado_preserves_original_granularity():
    source = _history_dataframe()

    result = history_module.preparar_historico_detalhado(source)

    assert len(result) == len(source)
    assert result["freight_id"].tolist() == [
        "F001", "F001", "F002", "F003"
    ]


def test_preparar_historico_detalhado_maps_standard_columns():
    source = _history_dataframe()

    result = history_module.preparar_historico_detalhado(source)

    assert result["valor_pago"].tolist() == [
        1000.0, 500.0, 2000.0, 3000.0
    ]
    assert result["peso_kg"].tolist() == [
        10000.0, 5000.0, 20000.0, 30000.0
    ]
    assert result["data_fim"].equals(source["finish_date"])
    assert result["cep_destino"].equals(source["cep"])


def test_preparar_historico_detalhado_creates_correct_flags():
    source = _history_dataframe()

    result = history_module.preparar_historico_detalhado(source)

    assert result["tem_valor"].tolist() == [
        True, True, True, True
    ]
    assert result["tem_finish_date"].tolist() == [
        True, True, True, False
    ]


def test_preparar_historico_detalhado_does_not_modify_source():
    source = _history_dataframe()
    before = source.copy(deep=True)

    history_module.preparar_historico_detalhado(source)

    pd.testing.assert_frame_equal(source, before)


# ============================================================
# analytics.history — CONSOLIDAÇÃO
# ============================================================

def test_consolidar_fretes_returns_empty_dataframe():
    result = history_module.consolidar_fretes(pd.DataFrame())

    assert result.empty


def test_consolidar_fretes_groups_by_freight_plant_and_carrier():
    source = _history_dataframe()

    result = history_module.consolidar_fretes(source)

    assert len(result) == 3

    assert result[
        [
            "freight_id",
            "issuing_plant_code",
            "service_agent_description",
        ]
    ].values.tolist() == [
        ["F001", "1210", "Transportadora A"],
        ["F002", "1210", "Transportadora B"],
        ["F003", "1211", "Transportadora C"],
    ]


def test_consolidar_fretes_sums_weight_and_amount_per_trip():
    source = _history_dataframe()

    result = history_module.consolidar_fretes(source)

    first = result.loc[result["freight_id"] == "F001"].iloc[0]

    assert first["quantidade"] == 15000
    assert first["valor_pago"] == 1500
    assert first["linhas"] == 2
    assert first["qtd_pedidos"] == 2


def test_consolidar_fretes_calculates_sla_for_mixed_results():
    source = _history_dataframe()

    result = history_module.consolidar_fretes(source)

    first = result.loc[result["freight_id"] == "F001"].iloc[0]

    assert first["sla_linhas"] == 2
    assert first["sla_true"] == 1
    assert first["sla_percentual"] == 0.5
    assert first["sla_frete"] == False


def test_consolidar_fretes_marks_freight_on_time_when_all_sla_true():
    source = _history_dataframe()

    result = history_module.consolidar_fretes(source)

    second = result.loc[result["freight_id"] == "F002"].iloc[0]

    assert second["sla_percentual"] == 1.0
    assert second["sla_frete"] == True


def test_consolidar_fretes_preserves_unknown_sla_when_no_known_values():
    source = _history_dataframe()

    result = history_module.consolidar_fretes(source)

    third = result.loc[result["freight_id"] == "F003"].iloc[0]

    assert third["sla_linhas"] == 0
    assert pd.isna(third["sla_percentual"])
    assert pd.isna(third["sla_frete"])


def test_consolidar_fretes_joins_unique_text_fields_in_sorted_order():
    source = _history_dataframe()

    result = history_module.consolidar_fretes(source)

    first = result.loc[result["freight_id"] == "F001"].iloc[0]

    assert first["pedidos"] == "P001 | P002"
    assert first["cidades_destino"] == "Campinas | Jundiaí"
    assert first["ceps_destino"] == "13053050 | 13280000"


def test_consolidar_fretes_detects_multiple_destinations():
    source = _history_dataframe()

    result = history_module.consolidar_fretes(source)

    first = result.loc[result["freight_id"] == "F001"].iloc[0]

    assert first["qtd_destinos"] == 2
    assert first["qtd_ceps"] == 2
    assert first["rota_multipla"]
    assert pd.isna(first["cidade_destino"])
    assert first["cep_destino"] == ""


def test_consolidar_fretes_keeps_single_destination():
    source = _history_dataframe()

    result = history_module.consolidar_fretes(source)

    second = result.loc[result["freight_id"] == "F002"].iloc[0]

    assert second["qtd_destinos"] == 1
    assert second["qtd_ceps"] == 1
    assert not second["rota_multipla"]
    assert second["cidade_destino"] == "São Paulo"
    assert second["cep_destino"] == "01000000"


def test_consolidar_fretes_preserves_carrier_group():
    source = _history_dataframe()

    result = history_module.consolidar_fretes(source)

    assert result["service_agent_group"].tolist() == [
        "VBR6", "VBR6", "VBR7"
    ]


def test_consolidar_fretes_does_not_modify_source():
    source = _history_dataframe()
    before = source.copy(deep=True)

    history_module.consolidar_fretes(source)

    pd.testing.assert_frame_equal(source, before)


# ============================================================
# analytics.history — CACHE PARQUET
# ============================================================

def test_obter_historico_consolidado_uses_fresh_parquet_cache(
    tmp_path,
    monkeypatch,
):
    source_path = tmp_path / "base.parquet"
    cache_path = tmp_path / "base.parquet.consolidado.parquet"

    source_path.touch()
    cache_path.touch()

    monkeypatch.setattr(
        history_module.C,
        "PARQUET_PATH",
        source_path,
    )

    monkeypatch.setattr(
        history_module.os.path,
        "getmtime",
        lambda path: 200.0 if str(path) == str(source_path) else 300.0,
    )

    cached = pd.DataFrame({"freight_id": ["F001"]})
    calls = []

    monkeypatch.setattr(
        history_module.pd,
        "read_parquet",
        lambda path: calls.append(str(path)) or cached,
    )

    monkeypatch.setattr(
        history_module,
        "carregar_historico",
        lambda: pytest.fail("Não deveria carregar a origem"),
    )

    result = history_module.obter_historico_consolidado()

    assert result is cached
    assert calls == [str(cache_path)]


def test_obter_historico_detalhado_uses_fresh_parquet_cache(
    tmp_path,
    monkeypatch,
):
    source_path = tmp_path / "base.parquet"
    cache_path = tmp_path / "base.parquet.detalhado.parquet"

    source_path.touch()
    cache_path.touch()

    monkeypatch.setattr(
        history_module.C,
        "PARQUET_PATH",
        source_path,
    )

    monkeypatch.setattr(
        history_module.os.path,
        "getmtime",
        lambda path: 200.0 if str(path) == str(source_path) else 300.0,
    )

    cached = pd.DataFrame({"freight_id": ["F001"]})
    calls = []

    monkeypatch.setattr(
        history_module.pd,
        "read_parquet",
        lambda path: calls.append(str(path)) or cached,
    )

    monkeypatch.setattr(
        history_module,
        "carregar_historico",
        lambda: pytest.fail("Não deveria carregar a origem"),
    )

    result = history_module.obter_historico_detalhado()

    assert result is cached
    assert calls == [str(cache_path)]


@pytest.mark.parametrize(
    ("function_name", "cache_suffix"),
    [
        ("obter_historico_consolidado", ".consolidado.parquet"),
        ("obter_historico_detalhado", ".detalhado.parquet"),
    ],
)
def test_obter_historico_rebuilds_cache_when_cache_does_not_exist(
    function_name,
    cache_suffix,
    tmp_path,
    monkeypatch,
):
    source_path = tmp_path / "base.parquet"
    source_path.touch()

    monkeypatch.setattr(
        history_module.C,
        "PARQUET_PATH",
        source_path,
    )

    monkeypatch.setattr(
        history_module.os.path,
        "exists",
        lambda path: False,
    )

    source = _history_dataframe()
    loaded = []

    monkeypatch.setattr(
        history_module,
        "carregar_historico",
        lambda: loaded.append(True) or source.copy(),
    )

    saved = []

    def fake_to_parquet(self, path, index=False):
        saved.append((str(path), index))

    monkeypatch.setattr(
        pd.DataFrame,
        "to_parquet",
        fake_to_parquet,
    )

    if function_name == "obter_historico_consolidado":
        monkeypatch.setattr(
            history_module,
            "consolidar_fretes",
            lambda df: pd.DataFrame({"tipo": ["consolidado"]}),
        )
    else:
        monkeypatch.setattr(
            history_module,
            "preparar_historico_detalhado",
            lambda df: pd.DataFrame({"tipo": ["detalhado"]}),
        )

    result = getattr(history_module, function_name)()

    assert len(loaded) == 1
    assert result["tipo"].iloc[0] in ["consolidado", "detalhado"]
    assert saved == [
        (str(source_path) + cache_suffix, False)
    ]


@pytest.mark.parametrize(
    ("function_name", "cache_suffix"),
    [
        ("obter_historico_consolidado", ".consolidado.parquet"),
        ("obter_historico_detalhado", ".detalhado.parquet"),
    ],
)
def test_obter_historico_rebuilds_cache_when_source_is_newer(
    function_name,
    cache_suffix,
    tmp_path,
    monkeypatch,
):
    source_path = tmp_path / "base.parquet"
    cache_path = tmp_path / ("base.parquet" + cache_suffix)

    source_path.touch()
    cache_path.touch()

    monkeypatch.setattr(
        history_module.C,
        "PARQUET_PATH",
        source_path,
    )

    monkeypatch.setattr(
        history_module.os.path,
        "exists",
        lambda path: True,
    )

    monkeypatch.setattr(
        history_module.os.path,
        "getmtime",
        lambda path: 300.0 if str(path) == str(source_path) else 200.0,
    )

    source = _history_dataframe()
    loaded = []

    monkeypatch.setattr(
        history_module,
        "carregar_historico",
        lambda: loaded.append(True) or source.copy(),
    )

    saved = []

    def fake_to_parquet(self, path, index=False):
        saved.append((str(path), index))

    monkeypatch.setattr(
        pd.DataFrame,
        "to_parquet",
        fake_to_parquet,
    )

    if function_name == "obter_historico_consolidado":
        monkeypatch.setattr(
            history_module,
            "consolidar_fretes",
            lambda df: pd.DataFrame({"tipo": ["consolidado"]}),
        )
    else:
        monkeypatch.setattr(
            history_module,
            "preparar_historico_detalhado",
            lambda df: pd.DataFrame({"tipo": ["detalhado"]}),
        )

    getattr(history_module, function_name)()

    assert len(loaded) == 1
    assert saved == [(str(cache_path), False)]


# ============================================================
# DISTANCE, TRUCK AND REFERENCE COSTS
# ============================================================

def test_calculate_distance_returns_none_when_plant_is_not_dict():
    assert carrier_module._calculate_distance(
        None,
        "13053050",
    ) is None


def test_calculate_distance_returns_none_when_zip_is_missing():
    assert carrier_module._calculate_distance(
        {"cep": ""},
        "13053050",
    ) is None


def test_calculate_distance_returns_none_when_zip_info_is_invalid(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "_zip_info",
        lambda cep: None,
    )

    assert carrier_module._calculate_distance(
        {"cep": "13053050"},
        "13280000",
    ) is None


def test_calculate_distance_uses_normalized_zips(monkeypatch):
    calls = []

    monkeypatch.setattr(
        carrier_module,
        "_zip_info",
        lambda cep: calls.append(cep) or {"cep": cep},
    )

    monkeypatch.setattr(
        carrier_module,
        "distancia_km",
        lambda origin, destination: 125.5,
    )

    result = carrier_module._calculate_distance(
        {"cep": "13053-050"},
        "13280-000",
    )

    assert result == 125.5
    assert calls == ["13053050", "13280000"]


def test_calculate_distance_returns_none_when_distance_fails(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "_zip_info",
        lambda cep: {"cep": cep},
    )

    def fail(*args):
        raise RuntimeError("Falha no cálculo")

    monkeypatch.setattr(
        carrier_module,
        "distancia_km",
        fail,
    )

    assert carrier_module._calculate_distance(
        {"cep": "13053050"},
        "13280000",
    ) is None


def test_truck_returns_recommendation(monkeypatch):
    monkeypatch.setattr(
        carrier_module,
        "recomendar_caminhao",
        lambda weight: {"tipo": "Truck"},
    )

    assert carrier_module._truck(10000) == {
        "tipo": "Truck",
    }


def test_truck_returns_none_when_recommendation_fails(
    monkeypatch,
):
    def fail(weight):
        raise RuntimeError("Falha")

    monkeypatch.setattr(
        carrier_module,
        "recomendar_caminhao",
        fail,
    )

    assert carrier_module._truck(10000) is None


def test_reference_costs_passes_all_freight_parameters(
    monkeypatch,
):
    received = {}

    def fake_calculate_costs(**kwargs):
        received.update(kwargs)
        return {"antt": 1500, "mercado": 1800}

    monkeypatch.setattr(
        carrier_module,
        "calcular_custos",
        fake_calculate_costs,
    )

    freight = {
        "uf": "SP",
        "peso_kg": 10000,
        "eixos": 6,
        "categoria": "Carga geral",
        "trechos": ["SP", "RJ"],
    }

    result = carrier_module._reference_costs(freight)

    assert received == freight
    assert result == {
        "antt": 1500,
        "mercado": 1800,
    }


def test_reference_costs_returns_fallback_when_calculation_fails(
    monkeypatch,
):
    def fail(**kwargs):
        raise RuntimeError("Falha")

    monkeypatch.setattr(
        carrier_module,
        "calcular_custos",
        fail,
    )

    result = carrier_module._reference_costs({
        "uf": "SP",
        "peso_kg": 10000,
        "eixos": 6,
        "categoria": "Carga geral",
        "trechos": [],
    })

    assert result == {
        "antt": None,
        "mercado": None,
        "distancia_total_km": None,
        "litros_totais": None,
        "custo_combustivel": None,
    }


# ============================================================
# WEIGHT FACTOR
# ============================================================

def test_weight_factor_calculates_similarity_by_weight(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "MISSING_WEIGHT_FACTOR",
        0.25,
    )

    weights = pd.Series(
        [100, 200, 400, 0, None],
        index=["A", "B", "C", "D", "E"],
    )

    result = carrier_module._weight_factor(
        weights,
        100,
    )

    assert result.loc["A"] == pytest.approx(1.0)
    assert result.loc["B"] == pytest.approx(0.5)
    assert result.loc["C"] == pytest.approx(0.25)
    assert result.loc["D"] == pytest.approx(0.25)
    assert result.loc["E"] == pytest.approx(0.25)


@pytest.mark.parametrize(
    "new_weight",
    [
        None,
        "inválido",
        0,
        -100,
    ],
)
def test_weight_factor_returns_neutral_factor_for_invalid_new_weight(
    new_weight,
):
    weights = pd.Series(
        [100, 200, None],
        index=["A", "B", "C"],
    )

    result = carrier_module._weight_factor(
        weights,
        new_weight,
    )

    assert result.equals(
        pd.Series(
            [1.0, 1.0, 1.0],
            index=["A", "B", "C"],
        )
    )


def test_weight_factor_preserves_original_index():
    weights = pd.Series(
        [100, None, 200],
        index=[10, 20, 30],
    )

    result = carrier_module._weight_factor(
        weights,
        100,
    )

    assert result.index.tolist() == [10, 20, 30]


# ============================================================
# RECENCY FACTOR
# ============================================================

def test_recency_factor_applies_half_life(monkeypatch):
    monkeypatch.setattr(
        carrier_module,
        "HALF_LIFE_DAYS",
        10,
    )

    reference = pd.Timestamp("2026-01-21")

    dates = pd.Series(
        [
            reference,
            reference - pd.Timedelta(days=10),
            reference - pd.Timedelta(days=20),
            reference + pd.Timedelta(days=5),
            pd.NaT,
        ]
    )

    result = carrier_module._recency_factor(
        dates,
        reference,
    )

    assert result.iloc[0] == pytest.approx(1.0)
    assert result.iloc[1] == pytest.approx(0.5)
    assert result.iloc[2] == pytest.approx(0.25)
    assert result.iloc[3] == pytest.approx(1.0)
    assert result.iloc[4] == pytest.approx(0.5)


def test_recency_factor_returns_neutral_when_reference_is_none():
    dates = pd.Series(
        pd.to_datetime([
            "2026-01-01",
            "2026-01-10",
            None,
        ])
    )

    result = carrier_module._recency_factor(
        dates,
        None,
    )

    assert result.tolist() == [1.0, 1.0, 1.0]


def test_recency_factor_returns_neutral_when_reference_is_nat():
    dates = pd.Series(
        pd.to_datetime([
            "2026-01-01",
            "2026-01-10",
        ])
    )

    result = carrier_module._recency_factor(
        dates,
        pd.NaT,
    )

    assert result.tolist() == [1.0, 1.0]


# ============================================================
# COMBINED WEIGHTING
# ============================================================

def test_weighting_combines_weight_and_recency_factors(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "HALF_LIFE_DAYS",
        10,
    )

    trips = pd.DataFrame({
        "peso_kg": [100, 200],
        "data_fim": pd.to_datetime([
            "2026-01-21",
            "2026-01-11",
        ]),
    })

    result = carrier_module._weighting(
        trips,
        100,
        pd.Timestamp("2026-01-21"),
    )

    assert result.iloc[0] == pytest.approx(1.0)
    assert result.iloc[1] == pytest.approx(0.25)


def test_weighting_uses_latest_date_when_reference_is_omitted(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "HALF_LIFE_DAYS",
        10,
    )

    trips = pd.DataFrame({
        "peso_kg": [100, 100],
        "data_fim": pd.to_datetime([
            "2026-01-11",
            "2026-01-21",
        ]),
    })

    result = carrier_module._weighting(
        trips,
        100,
    )

    assert result.iloc[0] == pytest.approx(0.5)
    assert result.iloc[1] == pytest.approx(1.0)


def test_weighting_without_date_column_uses_only_weight():
    trips = pd.DataFrame({
        "peso_kg": [100, 200],
    })

    result = carrier_module._weighting(
        trips,
        100,
    )

    assert result.iloc[0] == pytest.approx(1.0)
    assert result.iloc[1] == pytest.approx(0.5)


# ============================================================
# WEIGHT VALIDATION AND WEIGHT BAND
# ============================================================

@pytest.mark.parametrize(
    "value, expected",
    [
        (100, 100.0),
        ("100.5", 100.5),
        (None, None),
        ("inválido", None),
        (0, None),
        (-100, None),
    ],
)
def test_weight_as_float(value, expected):
    assert carrier_module._weight_as_float(value) == expected


def test_trips_in_weight_band_includes_both_boundaries(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "WEIGHT_BAND_MIN",
        0.8,
    )

    monkeypatch.setattr(
        carrier_module,
        "WEIGHT_BAND_MAX",
        1.2,
    )

    trips = pd.DataFrame({
        "freight_id": [
            "F1", "F2", "F3", "F4", "F5", "F6",
        ],
        "peso_kg": [
            79, 80, 100, 120, 121, None,
        ],
    })

    result = carrier_module._trips_in_weight_band(
        trips,
        100,
    )

    assert result["freight_id"].tolist() == [
        "F2", "F3", "F4",
    ]


@pytest.mark.parametrize(
    "weight",
    [
        None,
        0,
        -100,
        "inválido",
    ],
)
def test_trips_in_weight_band_returns_empty_for_invalid_weight(
    weight,
):
    trips = pd.DataFrame({
        "freight_id": ["F1"],
        "peso_kg": [100],
    })

    result = carrier_module._trips_in_weight_band(
        trips,
        weight,
    )

    assert result.empty
    assert list(result.columns) == list(trips.columns)


# ============================================================
# ROWS WITH AMOUNT AND WEIGHT
# ============================================================

def test_rows_with_value_and_weight_keeps_only_valid_rows():
    rows = pd.DataFrame({
        "freight_id": [
            "F1", "F1", "F2", "F3", "F4",
        ],
        "valor_pago": [
            1000, 0, 2000, None, 3000,
        ],
        "peso_kg": [
            1000, 1000, 0, 1000, 1500,
        ],
    })

    trips = pd.DataFrame({
        "freight_id": ["F1", "F2", "F3"],
    })

    result = carrier_module._rows_with_value_and_weight(
        rows,
        trips,
    )

    assert result["freight_id"].tolist() == ["F1"]


def test_rows_with_value_and_weight_returns_empty_when_trips_empty():
    rows = pd.DataFrame({
        "freight_id": ["F1"],
        "valor_pago": [1000],
        "peso_kg": [1000],
    })

    trips = pd.DataFrame(columns=["freight_id"])

    result = carrier_module._rows_with_value_and_weight(
        rows,
        trips,
    )

    assert result.empty


def test_rows_with_value_and_weight_accepts_none_rows():
    trips = pd.DataFrame({
        "freight_id": ["F1"],
    })

    result = carrier_module._rows_with_value_and_weight(
        None,
        trips,
    )

    assert isinstance(result, pd.DataFrame)
    assert result.empty


# ============================================================
# BRL PER 100 KG BY CARRIER
# ============================================================

def test_brl_per_100kg_by_carrier_uses_median_per_trip(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "WEIGHT_BAND_MIN",
        0.8,
    )

    monkeypatch.setattr(
        carrier_module,
        "WEIGHT_BAND_MAX",
        1.2,
    )

    monkeypatch.setattr(
        carrier_module,
        "MIN_BRL_PER_100KG",
        0,
    )

    carrier_col = carrier_module.CARRIER_COL

    scope_trips = pd.DataFrame({
        "freight_id": ["F1", "F2", "F3", "F4"],
        carrier_col: ["A", "A", "A", "B"],
        "peso_kg": [1000, 1000, 1000, 2000],
    })

    rows = pd.DataFrame({
        "freight_id": ["F1", "F2", "F3", "F4"],
        carrier_col: ["A", "A", "A", "B"],
        "valor_pago": [1000, 2000, 3000, 8000],
        "peso_kg": [1000, 1000, 1000, 2000],
    })

    result = carrier_module._brl_per_100kg_by_carrier(
        rows,
        scope_trips,
        1000,
    )

    assert result["A"] == pytest.approx(200)
    assert "B" not in result.index


def test_brl_per_100kg_by_carrier_returns_empty_when_no_valid_rows(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "WEIGHT_BAND_MIN",
        0.8,
    )

    monkeypatch.setattr(
        carrier_module,
        "WEIGHT_BAND_MAX",
        1.2,
    )

    carrier_col = carrier_module.CARRIER_COL

    scope_trips = pd.DataFrame({
        "freight_id": ["F1"],
        carrier_col: ["A"],
        "peso_kg": [1000],
    })

    rows = pd.DataFrame({
        "freight_id": ["F1"],
        carrier_col: ["A"],
        "valor_pago": [None],
        "peso_kg": [1000],
    })

    result = carrier_module._brl_per_100kg_by_carrier(
        rows,
        scope_trips,
        1000,
    )

    assert result.empty


def test_brl_per_100kg_by_carrier_applies_minimum_threshold(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "WEIGHT_BAND_MIN",
        0.8,
    )

    monkeypatch.setattr(
        carrier_module,
        "WEIGHT_BAND_MAX",
        1.2,
    )

    monkeypatch.setattr(
        carrier_module,
        "MIN_BRL_PER_100KG",
        100,
    )

    carrier_col = carrier_module.CARRIER_COL

    scope_trips = pd.DataFrame({
        "freight_id": ["F1", "F2"],
        carrier_col: ["A", "A"],
        "peso_kg": [1000, 1000],
    })

    rows = pd.DataFrame({
        "freight_id": ["F1", "F2"],
        carrier_col: ["A", "A"],
        "valor_pago": [500, 2000],
        "peso_kg": [1000, 1000],
    })

    result = carrier_module._brl_per_100kg_by_carrier(
        rows,
        scope_trips,
        1000,
    )

    assert result["A"] == pytest.approx(200)


# ============================================================
# SUMMARY BY TRIP
# ============================================================

def test_summarize_by_trip_sums_amount_and_weight():
    rows = pd.DataFrame({
        "freight_id": [
            "F1", "F1", "F2",
        ],
        "valor_pago": [
            500, 500, 3000,
        ],
        "peso_kg": [
            500, 500, 1000,
        ],
    })

    result = carrier_module._summarize_by_trip(rows)

    assert result.loc["F1", "valor_pago"] == 1000
    assert result.loc["F1", "peso_kg"] == 1000
    assert result.loc["F1", "rs_100kg"] == pytest.approx(100)

    assert result.loc["F2", "valor_pago"] == 3000
    assert result.loc["F2", "peso_kg"] == 1000
    assert result.loc["F2", "rs_100kg"] == pytest.approx(300)


def test_summarize_by_trip_removes_values_below_minimum(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "MIN_BRL_PER_100KG",
        100,
    )

    rows = pd.DataFrame({
        "freight_id": ["F1", "F2"],
        "valor_pago": [500, 2000],
        "peso_kg": [1000, 1000],
    })

    result = carrier_module._summarize_by_trip(rows)

    assert result.index.tolist() == ["F2"]


# ============================================================
# ECONOMIC REFERENCE
# ============================================================

def _economic_reference_data():
    carrier_col = carrier_module.CARRIER_COL

    trips = pd.DataFrame({
        "freight_id": ["F1", "F2"],
        carrier_col: ["A", "A"],
        "peso_kg": [1000, 1000],
    })

    rows = pd.DataFrame({
        "freight_id": ["F1", "F2"],
        carrier_col: ["A", "A"],
        "valor_pago": [1000, 3000],
        "peso_kg": [1000, 1000],
    })

    return trips, rows


def _configure_economic_reference(monkeypatch):
    monkeypatch.setattr(
        carrier_module,
        "WEIGHT_BAND_MIN",
        0.8,
    )

    monkeypatch.setattr(
        carrier_module,
        "WEIGHT_BAND_MAX",
        1.2,
    )

    monkeypatch.setattr(
        carrier_module,
        "MIN_REFERENCE_TRIPS",
        2,
    )

    monkeypatch.setattr(
        carrier_module,
        "MIN_BRL_PER_100KG",
        0,
    )


def test_economic_reference_prefers_recommended_carrier(
    monkeypatch,
):
    _configure_economic_reference(monkeypatch)

    trips, rows = _economic_reference_data()

    result = carrier_module._economic_reference(
        trips,
        rows,
        "A",
        1000,
    )

    assert result is not None
    assert result["origem"] == "transportadora"
    assert result["viagens"] == 2


def test_economic_reference_calculates_median_quartiles_and_estimate(
    monkeypatch,
):
    _configure_economic_reference(monkeypatch)

    trips, rows = _economic_reference_data()

    result = carrier_module._economic_reference(
        trips,
        rows,
        "A",
        1000,
    )

    assert result["rs_por_100kg"] == pytest.approx(200)
    assert result["rs_por_100kg_p25"] == pytest.approx(150)
    assert result["rs_por_100kg_p75"] == pytest.approx(250)

    assert result["rs_por_kg"] == pytest.approx(2)
    assert result["rs_por_kg_p25"] == pytest.approx(1.5)
    assert result["rs_por_kg_p75"] == pytest.approx(2.5)

    assert result["estimativa_frete"] == pytest.approx(2000)
    assert result["estimativa_min"] == pytest.approx(1500)
    assert result["estimativa_max"] == pytest.approx(2500)


def test_economic_reference_calculates_weighted_total_ratio(
    monkeypatch,
):
    _configure_economic_reference(monkeypatch)

    trips, rows = _economic_reference_data()

    result = carrier_module._economic_reference(
        trips,
        rows,
        "A",
        1000,
    )

    assert result["rs_por_100kg_soma"] == pytest.approx(200)
    assert result["rs_por_kg_soma"] == pytest.approx(2)

    assert result["soma_valor"] == pytest.approx(4000)
    assert result["soma_peso_kg"] == pytest.approx(2000)

    assert result["peso_tipico_kg"] == pytest.approx(1000)
    assert result["razao_peso_vs_tipico"] == pytest.approx(1)

    assert result["linhas"] == 2
    assert result["viagens"] == 2
    assert result["faixa_kg"] == (800, 1200)


def test_economic_reference_falls_back_to_all_carriers(
    monkeypatch,
):
    _configure_economic_reference(monkeypatch)

    carrier_col = carrier_module.CARRIER_COL

    trips = pd.DataFrame({
        "freight_id": ["F1", "F2"],
        carrier_col: ["A", "B"],
        "peso_kg": [1000, 1000],
    })

    rows = pd.DataFrame({
        "freight_id": ["F1", "F2"],
        carrier_col: ["A", "B"],
        "valor_pago": [1000, 3000],
        "peso_kg": [1000, 1000],
    })

    result = carrier_module._economic_reference(
        trips,
        rows,
        "A",
        1000,
    )

    assert result is not None
    assert result["origem"] == "rota (todas as transportadoras)"
    assert result["viagens"] == 2
    assert result["rs_por_100kg"] == pytest.approx(200)


def test_economic_reference_returns_none_when_rows_are_none():
    trips, _ = _economic_reference_data()

    assert carrier_module._economic_reference(
        trips,
        None,
        "A",
        1000,
    ) is None


def test_economic_reference_returns_none_when_rows_are_empty():
    trips, rows = _economic_reference_data()

    assert carrier_module._economic_reference(
        trips,
        rows.iloc[0:0],
        "A",
        1000,
    ) is None


@pytest.mark.parametrize(
    "weight",
    [
        None,
        0,
        -100,
        "inválido",
    ],
)
def test_economic_reference_returns_none_for_invalid_weight(
    weight,
):
    trips, rows = _economic_reference_data()

    assert carrier_module._economic_reference(
        trips,
        rows,
        "A",
        weight,
    ) is None


def test_economic_reference_returns_none_when_no_trips_in_band(
    monkeypatch,
):
    _configure_economic_reference(monkeypatch)

    trips, rows = _economic_reference_data()
    trips["peso_kg"] = 5000

    assert carrier_module._economic_reference(
        trips,
        rows,
        "A",
        1000,
    ) is None


def test_economic_reference_returns_none_when_minimum_trips_not_met(
    monkeypatch,
):
    _configure_economic_reference(monkeypatch)

    monkeypatch.setattr(
        carrier_module,
        "MIN_REFERENCE_TRIPS",
        3,
    )

    trips, rows = _economic_reference_data()

    assert carrier_module._economic_reference(
        trips,
        rows,
        "A",
        1000,
    ) is None


def test_economic_reference_ignores_rows_without_amount_or_weight(
    monkeypatch,
):
    _configure_economic_reference(monkeypatch)

    trips, rows = _economic_reference_data()

    extra_rows = pd.DataFrame({
        "freight_id": ["F1", "F2"],
        carrier_module.CARRIER_COL: ["A", "A"],
        "valor_pago": [10000, 10000],
        "peso_kg": [0, None],
    })

    rows = pd.concat(
        [rows, extra_rows],
        ignore_index=True,
    )

    result = carrier_module._economic_reference(
        trips,
        rows,
        "A",
        1000,
    )

    assert result is not None
    assert result["rs_por_100kg"] == pytest.approx(200)
    assert result["soma_valor"] == pytest.approx(4000)
    assert result["soma_peso_kg"] == pytest.approx(2000)



# ============================================================
# RANKING, VALIDATION, CONFIDENCE AND GEOGRAPHIC SCOPES
# ============================================================

def _ranking_trips():
    return pd.DataFrame({
        "freight_id": ["F1", "F2", "F3", "F4"],
        carrier_module.CARRIER_COL: ["A", "A", "B", "B"],
        "peso_kg": [1000, 1000, 1000, 1000],
        "sla_ok": [True, False, True, True],
    })


def _ranking_table():
    return pd.DataFrame(
        {
            "trips": [10, 8, 3],
            "effective_n": [8.0, 7.0, 2.0],
            "sla": [0.9, 0.8, 1.0],
            "adjusted_sla": [0.88, 0.82, 0.75],
            "brl_per_100kg": [100.0, 110.0, 120.0],
            "avg_paid_trip": [1000.0, 1100.0, 1200.0],
            "avg_paid_trip_valued": [1000.0, 1100.0, 1200.0],
        },
        index=["A", "B", "C"],
    )


def test_ratio_vs_antt_calculates_historical_ratio():
    result = carrier_module._ratio_vs_antt(
        250,
        {"antt": 100},
    )

    assert result == 2.5


@pytest.mark.parametrize(
    "estimate,reference",
    [
        (None, {"antt": 100}),
        ("inválido", {"antt": 100}),
        (100, None),
        (100, []),
        (100, {}),
        (100, {"antt": None}),
        (100, {"antt": 0}),
        (100, {"antt": -10}),
        (100, {"antt": "inválido"}),
    ],
)
def test_ratio_vs_antt_returns_none_for_invalid_inputs(
    estimate,
    reference,
):
    assert carrier_module._ratio_vs_antt(
        estimate,
        reference,
    ) is None


def test_by_carrier_returns_empty_table_for_empty_scope():
    result = carrier_module._by_carrier(
        pd.DataFrame(),
        global_sla_mean=0.8,
    )

    assert result.empty
    assert list(result.columns) == [
        "trips",
        "effective_n",
        "sla",
        "adjusted_sla",
        "brl_per_100kg",
        "avg_paid_trip",
        "avg_paid_trip_valued",
    ]


def test_by_carrier_aggregates_sla_and_sorts_ranking(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "SLA_SMOOTHING",
        0,
    )

    trips = _ranking_trips()

    result = carrier_module._by_carrier(
        trips,
        global_sla_mean=0.5,
        weight_kg=1000,
    )

    assert result.index.tolist() == ["B", "A"]
    assert result.loc["A", "trips"] == 2
    assert result.loc["A", "sla"] == pytest.approx(0.5)
    assert result.loc["B", "trips"] == 2
    assert result.loc["B", "sla"] == pytest.approx(1.0)


def test_by_carrier_removes_duplicate_freight_carrier_pairs(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "SLA_SMOOTHING",
        0,
    )

    trips = pd.DataFrame({
        "freight_id": ["F1", "F1", "F2"],
        carrier_module.CARRIER_COL: ["A", "A", "A"],
        "peso_kg": [1000, 1000, 1000],
        "sla_ok": [True, False, True],
    })

    result = carrier_module._by_carrier(
        trips,
        global_sla_mean=0.5,
        weight_kg=1000,
    )

    assert result.loc["A", "trips"] == 2
    assert result.loc["A", "sla"] == pytest.approx(1.0)


def test_by_carrier_does_not_count_unknown_sla_as_failure(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "SLA_SMOOTHING",
        1,
    )

    trips = pd.DataFrame({
        "freight_id": ["F1", "F2"],
        carrier_module.CARRIER_COL: ["A", "A"],
        "peso_kg": [1000, 1000],
        "sla_ok": pd.Series(
            [True, pd.NA],
            dtype="boolean",
        ),
    })

    result = carrier_module._by_carrier(
        trips,
        global_sla_mean=0.8,
        weight_kg=1000,
    )

    assert result.loc["A", "trips"] == 2
    assert result.loc["A", "sla"] == pytest.approx(1.0)
    assert result.loc["A", "effective_n"] == pytest.approx(1.0)


def test_by_carrier_uses_global_mean_when_it_is_missing(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "SLA_SMOOTHING",
        1,
    )

    trips = pd.DataFrame({
        "freight_id": ["F1"],
        carrier_module.CARRIER_COL: ["A"],
        "peso_kg": [1000],
        "sla_ok": [True],
    })

    result = carrier_module._by_carrier(
        trips,
        global_sla_mean=None,
        weight_kg=1000,
    )

    assert result.loc["A", "adjusted_sla"] == pytest.approx(0.5)


def test_by_carrier_does_not_use_economic_cost_to_rank(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "SLA_SMOOTHING",
        0,
    )

    trips = _ranking_trips()

    rows = pd.DataFrame({
        "freight_id": ["F1", "F2", "F3", "F4"],
        carrier_module.CARRIER_COL: ["A", "A", "B", "B"],
        "valor_pago": [100, 100, 10000, 10000],
        "peso_kg": [1000, 1000, 1000, 1000],
    })

    result = carrier_module._by_carrier(
        trips,
        global_sla_mean=0.5,
        weight_kg=1000,
        rows=rows,
    )

    assert result.index[0] == "B"
    assert result.loc["A", "brl_per_100kg"] < (
        result.loc["B", "brl_per_100kg"]
    )


def test_valid_keeps_only_minimum_sample_and_known_sla(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "MIN_CARRIER_TRIPS",
        3,
    )

    table = pd.DataFrame(
        {
            "trips": [3, 2, 5],
            "sla": [0.9, 1.0, np.nan],
        },
        index=["VALID", "FEW_TRIPS", "UNKNOWN_SLA"],
    )

    result = carrier_module._valid(table)

    assert result.index.tolist() == ["VALID"]
    assert result is not table


def test_valid_returns_empty_table_unchanged():
    table = pd.DataFrame(
        columns=["trips", "sla"],
    )

    result = carrier_module._valid(table)

    assert result.empty
    assert result is table


def test_all_corporate_carriers_filters_vbr6_and_sorts(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "GROUP_COL",
        "grupo",
    )
    monkeypatch.setattr(
        carrier_module,
        "CARRIER_COL",
        "transportadora",
    )
    monkeypatch.setattr(
        carrier_module,
        "CORPORATE_GROUP",
        "VBR6",
    )

    trips = pd.DataFrame({
        "transportadora": ["Z", "A", "B", "C", "D"],
        "grupo": ["VBR6", "VBR6 - X", "VBR7", None, " vbr6 "],
    })

    result = carrier_module._all_corporate_carriers(trips)

    assert result == ["A", "D", "Z"]


def test_all_corporate_carriers_falls_back_to_rows_when_trips_lack_group(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "GROUP_COL",
        "grupo",
    )
    monkeypatch.setattr(
        carrier_module,
        "CARRIER_COL",
        "transportadora",
    )
    monkeypatch.setattr(
        carrier_module,
        "CORPORATE_GROUP",
        "VBR6",
    )

    trips = pd.DataFrame({
        "transportadora": ["A"],
    })

    rows = pd.DataFrame({
        "transportadora": ["B", "C"],
        "grupo": ["VBR6", "VBR7"],
    })

    result = carrier_module._all_corporate_carriers(
        trips,
        rows,
    )

    assert result == ["B"]


def test_all_corporate_carriers_returns_empty_when_group_is_missing(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "GROUP_COL",
        "grupo",
    )

    result = carrier_module._all_corporate_carriers(
        pd.DataFrame({"transportadora": ["A"]}),
        pd.DataFrame({"transportadora": ["B"]}),
    )

    assert result == []


@pytest.mark.parametrize(
    "sla,trips,expected",
    [
        (None, 100, "Baixa"),
        (np.nan, 100, "Baixa"),
    ],
)
def test_classify_confidence_returns_low_for_unknown_sla(
    sla,
    trips,
    expected,
):
    assert carrier_module.classify_confidence(
        sla,
        trips,
    ) == expected


def test_classify_confidence_returns_high(
    monkeypatch,
):
    monkeypatch.setattr(carrier_module, "SLA_HIGH", 0.95)
    monkeypatch.setattr(carrier_module, "TRIPS_HIGH", 20)

    assert carrier_module.classify_confidence(
        0.95,
        20,
    ) == "Alta"


def test_classify_confidence_returns_medium(
    monkeypatch,
):
    monkeypatch.setattr(carrier_module, "SLA_HIGH", 0.95)
    monkeypatch.setattr(carrier_module, "SLA_MEDIUM", 0.80)
    monkeypatch.setattr(carrier_module, "TRIPS_HIGH", 20)
    monkeypatch.setattr(carrier_module, "MIN_CARRIER_TRIPS", 5)

    assert carrier_module.classify_confidence(
        0.80,
        5,
    ) == "Média"


def test_classify_confidence_returns_low_below_threshold(
    monkeypatch,
):
    monkeypatch.setattr(carrier_module, "SLA_MEDIUM", 0.80)
    monkeypatch.setattr(carrier_module, "MIN_CARRIER_TRIPS", 5)

    assert carrier_module.classify_confidence(
        0.79,
        10,
    ) == "Baixa"


def test_detect_tie_returns_empty_for_none_or_single_row():
    assert carrier_module._detect_tie(None) == []

    table = pd.DataFrame(
        {"adjusted_sla": [0.9]},
        index=["A"],
    )

    assert carrier_module._detect_tie(table) == []


def test_detect_tie_returns_carriers_within_threshold(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "TIE_THRESHOLD",
        0.03,
    )

    table = pd.DataFrame(
        {"adjusted_sla": [0.95, 0.93, 0.90, 0.80]},
        index=["A", "B", "C", "D"],
    )

    result = carrier_module._detect_tie(table)

    assert result == ["A", "B"]


def test_detect_tie_excludes_carrier_exactly_at_threshold(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "TIE_THRESHOLD",
        0.125,
    )

    table = pd.DataFrame(
        {"adjusted_sla": [0.75, 0.625]},
        index=["A", "B"],
    )

    assert carrier_module._detect_tie(table) == []


def test_build_alternatives_deduplicates_carriers_and_respects_limit(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "BASIS_LABELS",
        {"zip": "CEP", "state": "UF"},
    )

    table1 = _ranking_table()

    table2 = pd.DataFrame(
        {
            "trips": [8, 7, 6],
            "effective_n": [7.0, 6.0, 5.0],
            "sla": [0.8, 0.85, 0.9],
            "adjusted_sla": [0.82, 0.84, 0.86],
            "brl_per_100kg": [110.0, 120.0, 130.0],
            "avg_paid_trip": [1100.0, 1200.0, 1300.0],
            "avg_paid_trip_valued": [1100.0, 1200.0, 1300.0],
        },
        index=["B", "D", "E"],
    )

    result = carrier_module._build_alternatives(
        [
            ("zip", 5, table1),
            ("state", None, table2),
        ],
        exclude="A",
        limit=2,
    )

    names = [item["nome"] for item in result]

    assert names == ["B", "C"]
    assert len(names) == 2
    assert len(names) == len(set(names))


def test_build_alternatives_forces_low_confidence_for_state(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "BASIS_LABELS",
        {"state": "UF"},
    )

    table = pd.DataFrame(
        {
            "trips": [100],
            "adjusted_sla": [1.0],
            "brl_per_100kg": [100.0],
            "avg_paid_trip": [1000.0],
            "avg_paid_trip_valued": [1000.0],
            "sla": [1.0],
        },
        index=["A"],
    )

    result = carrier_module._build_alternatives(
        [("state", None, table)]
    )

    assert result[0]["confianca"] == "Baixa"
    assert result[0]["base"] == "UF"


def _scope_dataframe():
    return pd.DataFrame({
        "issuing_plant_code": [
            "1210",
            "1210",
            "1210",
            "1210",
            "9999",
        ],
        "cep_destino": [
            "13053050",
            "13054000",
            "13060000",
            "13053051",
            "13053052",
        ],
        "uf_destino": [
            "SP",
            "SP",
            "SP",
            "SP",
            "SP",
        ],
        "rota_multipla": [
            False,
            False,
            False,
            True,
            False,
        ],
    })


def test_scopes_generates_zip_levels_and_state_in_order(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "ZIP_LEVELS",
        [5, 4, 3],
    )
    monkeypatch.setattr(
        carrier_module,
        "DEST_STATE_COL",
        "uf_destino",
    )

    result = list(
        carrier_module._scopes(
            _scope_dataframe(),
            plant_code=1210,
            zip_code="13053050",
            state="SP",
        )
    )

    assert [(key, level) for key, level, _ in result] == [
        ("zip", 5),
        ("zip", 4),
        ("zip", 3),
        ("state", None),
    ]

    assert len(result[0][2]) == 1  # ZIP5
    assert len(result[1][2]) == 2  # ZIP4
    assert len(result[2][2]) == 3  # ZIP3
    assert len(result[3][2]) == 4  # Estado


def test_scopes_excludes_multiple_routes_from_zip_but_keeps_state(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "ZIP_LEVELS",
        [5],
    )
    monkeypatch.setattr(
        carrier_module,
        "DEST_STATE_COL",
        "uf_destino",
    )

    result = list(
        carrier_module._scopes(
            _scope_dataframe(),
            plant_code="1210",
            zip_code="13053050",
            state="SP",
        )
    )

    zip_scope = result[0][2]
    state_scope = result[1][2]

    assert not zip_scope["rota_multipla"].any()
    assert len(state_scope) == 4


def test_scopes_does_not_mix_plants(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "ZIP_LEVELS",
        [3],
    )
    monkeypatch.setattr(
        carrier_module,
        "DEST_STATE_COL",
        "uf_destino",
    )

    result = list(
        carrier_module._scopes(
            _scope_dataframe(),
            plant_code="1210",
            zip_code="13053050",
            state="SP",
        )
    )

    for _, _, scope in result:
        assert set(scope["issuing_plant_code"]) == {"1210"}


def test_scopes_can_work_without_multiple_route_column(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "ZIP_LEVELS",
        [5],
    )

    base = _scope_dataframe().drop(
        columns=["rota_multipla"]
    )

    result = list(
        carrier_module._scopes(
            base,
            plant_code="1210",
            zip_code="13053050",
            state=None,
        )
    )

    assert len(result) == 1
    assert len(result[0][2]) == 2


def test_scopes_omits_state_when_state_column_is_missing(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "ZIP_LEVELS",
        [5],
    )
    monkeypatch.setattr(
        carrier_module,
        "DEST_STATE_COL",
        "uf_destino",
    )

    base = _scope_dataframe().drop(
        columns=["uf_destino"]
    )

    result = list(
        carrier_module._scopes(
            base,
            plant_code="1210",
            zip_code="13053050",
            state="SP",
        )
    )

    assert len(result) == 1
    assert result[0][0] == "zip"


def test_select_scope_returns_first_scope_with_valid_carrier(
    monkeypatch,
):
    scopes = [
        ("zip", 5, pd.DataFrame({"x": [1]})),
        ("zip", 4, pd.DataFrame({"x": [2]})),
    ]

    monkeypatch.setattr(
        carrier_module,
        "_scopes",
        lambda *args: iter(scopes),
    )

    tables = [
        pd.DataFrame({"trips": [1], "sla": [0.9]}, index=["A"]),
        pd.DataFrame({"trips": [5], "sla": [0.9]}, index=["B"]),
    ]

    calls = []

    def fake_by_carrier(scope, *args):
        calls.append(scope["x"].iloc[0])
        return tables[len(calls) - 1]

    monkeypatch.setattr(
        carrier_module,
        "_by_carrier",
        fake_by_carrier,
    )
    monkeypatch.setattr(
        carrier_module,
        "MIN_CARRIER_TRIPS",
        3,
    )

    result = carrier_module._select_scope(
        pd.DataFrame(),
        "1210",
        "13053050",
        "SP",
        0.8,
    )

    assert result is not None
    assert result[0:2] == ("zip", 4)
    assert result[3].index.tolist() == ["B"]
    assert calls == [1, 2]


def test_select_scope_returns_none_when_no_scope_has_valid_carrier(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "_scopes",
        lambda *args: iter([
            ("zip", 5, pd.DataFrame({"x": [1]})),
        ]),
    )
    monkeypatch.setattr(
        carrier_module,
        "_by_carrier",
        lambda *args: pd.DataFrame({
            "trips": [1],
            "sla": [0.9],
        }, index=["A"]),
    )
    monkeypatch.setattr(
        carrier_module,
        "MIN_CARRIER_TRIPS",
        3,
    )

    result = carrier_module._select_scope(
        pd.DataFrame(),
        "1210",
        "13053050",
        "SP",
        0.8,
    )

    assert result is None


def test_broader_tables_returns_only_scopes_after_winner(
    monkeypatch,
):
    scopes = [
        ("zip", 5, pd.DataFrame({"x": [1]})),
        ("zip", 4, pd.DataFrame({"x": [2]})),
        ("zip", 3, pd.DataFrame({"x": [3]})),
        ("state", None, pd.DataFrame({"x": [4]})),
    ]

    monkeypatch.setattr(
        carrier_module,
        "_scopes",
        lambda *args: iter(scopes),
    )
    monkeypatch.setattr(
        carrier_module,
        "_by_carrier",
        lambda scope, *args: pd.DataFrame({
            "trips": [5],
            "sla": [0.9],
        }, index=[f"C{scope['x'].iloc[0]}"]),
    )
    monkeypatch.setattr(
        carrier_module,
        "MIN_CARRIER_TRIPS",
        3,
    )

    result = list(
        carrier_module._broader_tables(
            pd.DataFrame(),
            "1210",
            "13053050",
            "SP",
            0.8,
            1000,
            None,
            None,
            "zip",
            4,
        )
    )

    assert [(key, level) for key, level, _ in result] == [
        ("zip", 3),
        ("state", None),
    ]
    assert result[0][2].index.tolist() == ["C3"]
    assert result[1][2].index.tolist() == ["C4"]



# ============================================================
# DETAIL, WARNINGS, BASE OUTPUT AND SIMILARITY
# ============================================================


def test_type_and_max_confidence_for_zip5():
    result = carrier_module._type_and_max_confidence("zip", 5)

    assert result == ("Direta", None)


def test_type_and_max_confidence_for_zip4():
    result = carrier_module._type_and_max_confidence("zip", 4)

    assert result == ("Rota similar", None)


def test_type_and_max_confidence_for_zip3():
    result = carrier_module._type_and_max_confidence("zip", 3)

    assert result == ("Rota similar", None)


def test_type_and_max_confidence_for_state(monkeypatch):
    monkeypatch.setattr(
        carrier_module,
        "BROAD_SCOPES",
        {"state": ("Regional", "Baixa")},
    )

    result = carrier_module._type_and_max_confidence("state", None)

    assert result == ("Regional", "Baixa")


def test_build_detail_for_zip5():
    result = carrier_module._build_detail(
        key="zip",
        level=5,
        zip_code="13053050",
        plant={"codigo": "1210"},
        state="SP",
        scope_trip_count=12,
    )

    assert "12 viagens" in result
    assert "mesma região de CEP" in result
    assert "peso" in result


def test_build_detail_for_zip4():
    result = carrier_module._build_detail(
        key="zip",
        level=4,
        zip_code="13053050",
        plant={"codigo": "1210"},
        state="SP",
        scope_trip_count=8,
    )

    assert "8 viagens" in result
    assert "1305" in result
    assert "…" in result


def test_build_detail_for_state():
    result = carrier_module._build_detail(
        key="state",
        level=None,
        zip_code="13053050",
        plant={"codigo": "1210"},
        state="SP",
        scope_trip_count=25,
    )

    assert "25 viagens" in result
    assert "1210" in result
    assert "SP" in result
    assert "histórico suficiente" in result


def test_build_detail_for_unknown_scope():
    result = carrier_module._build_detail(
        key="unknown",
        level=None,
        zip_code="13053050",
        plant={"codigo": "1210"},
        state="SP",
        scope_trip_count=0,
    )

    assert result == "Não foi encontrada uma base geográfica compatível."


def test_scope_warning_for_state():
    result = carrier_module._scope_warning("state")

    assert result is not None
    assert "histórico suficiente" in result
    assert "confiança baixa" in result


def test_scope_warning_for_zip_returns_none():
    assert carrier_module._scope_warning("zip") is None


def test_reference_warning_returns_none_without_ratio():
    result = carrier_module._reference_warning(
        estimate=1000,
        ratio=None,
        reference_costs={"antt": 900},
    )

    assert result is None


@pytest.mark.parametrize("ratio", [0.8, 1.0, 1.2])
def test_reference_warning_returns_none_inside_alert_range(
    monkeypatch,
    ratio,
):
    monkeypatch.setattr(carrier_module, "RATIO_ALERT_MIN", 0.8)
    monkeypatch.setattr(carrier_module, "RATIO_ALERT_MAX", 1.2)

    result = carrier_module._reference_warning(
        estimate=1000,
        ratio=ratio,
        reference_costs={"antt": 1000},
    )

    assert result is None


def test_reference_warning_returns_message_below_alert_range(
    monkeypatch,
):
    monkeypatch.setattr(carrier_module, "RATIO_ALERT_MIN", 0.8)
    monkeypatch.setattr(carrier_module, "RATIO_ALERT_MAX", 1.2)

    result = carrier_module._reference_warning(
        estimate=500,
        ratio=0.5,
        reference_costs={"antt": 1000},
    )

    assert result is not None
    assert "estimativa histórica" in result
    assert "referência ANTT" in result


def test_reference_warning_returns_message_above_alert_range(
    monkeypatch,
):
    monkeypatch.setattr(carrier_module, "RATIO_ALERT_MIN", 0.8)
    monkeypatch.setattr(carrier_module, "RATIO_ALERT_MAX", 1.2)

    result = carrier_module._reference_warning(
        estimate=2000,
        ratio=2.0,
        reference_costs={"antt": 1000},
    )

    assert result is not None
    assert "2,0x" in result
    assert "ANTT" in result


def test_atypical_weight_warning_returns_none_without_reference():
    assert carrier_module._atypical_weight_warning(
        1000,
        None,
    ) is None


@pytest.mark.parametrize("ratio", [0.5, 1.0, 2.0])
def test_atypical_weight_warning_returns_none_inside_range(
    monkeypatch,
    ratio,
):
    monkeypatch.setattr(
        carrier_module,
        "WEIGHT_RATIO_ALERT_MIN",
        0.5,
    )
    monkeypatch.setattr(
        carrier_module,
        "WEIGHT_RATIO_ALERT_MAX",
        2.0,
    )

    result = carrier_module._atypical_weight_warning(
        1000,
        {
            "razao_peso_vs_tipico": ratio,
            "peso_tipico_kg": 1000,
        },
    )

    assert result is None


def test_atypical_weight_warning_returns_message_for_low_weight(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "WEIGHT_RATIO_ALERT_MIN",
        0.5,
    )
    monkeypatch.setattr(
        carrier_module,
        "WEIGHT_RATIO_ALERT_MAX",
        2.0,
    )

    result = carrier_module._atypical_weight_warning(
        200,
        {
            "razao_peso_vs_tipico": 0.2,
            "peso_tipico_kg": 1000,
        },
    )

    assert result is not None
    assert "peso deste frete" in result
    assert "peso típico desta rota" in result
    assert "custo é fixa" in result


def test_atypical_weight_warning_returns_message_for_high_weight(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "WEIGHT_RATIO_ALERT_MIN",
        0.5,
    )
    monkeypatch.setattr(
        carrier_module,
        "WEIGHT_RATIO_ALERT_MAX",
        2.0,
    )

    result = carrier_module._atypical_weight_warning(
        5000,
        {
            "razao_peso_vs_tipico": 5.0,
            "peso_tipico_kg": 1000,
        },
    )

    assert result is not None
    assert "5,0x" in result


def test_concentration_warning_returns_none_for_zero_scope():
    assert carrier_module._concentration_warning(
        "Transportadora A",
        5,
        0,
    ) is None


def test_concentration_warning_returns_none_below_threshold(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "CONCENTRATION_ALERT",
        0.5,
    )

    result = carrier_module._concentration_warning(
        "Transportadora A",
        4,
        10,
    )

    assert result is None


def test_concentration_warning_returns_message_at_threshold(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "CONCENTRATION_ALERT",
        0.5,
    )

    result = carrier_module._concentration_warning(
        "Transportadora A",
        5,
        10,
    )

    assert result is not None
    assert "Transportadora A" in result
    assert "50%" in result
    assert "não uma comparação" in result


def test_concentration_warning_returns_message_above_threshold(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "CONCENTRATION_ALERT",
        0.5,
    )

    result = carrier_module._concentration_warning(
        "Transportadora B",
        8,
        10,
    )

    assert result is not None
    assert "80%" in result


def test_tie_warning_returns_none_for_empty_list():
    assert carrier_module._tie_warning([]) is None


def test_tie_warning_lists_at_most_three_carriers():
    result = carrier_module._tie_warning(
        ["Transportadora A", "Transportadora B",
         "Transportadora C", "Transportadora D",
         "Transportadora E"],
    )

    assert result is not None
    assert (
        "(Transportadora A, Transportadora B, Transportadora C)"
        in result
    )
    assert "Transportadora D" not in result
    assert "Transportadora E" not in result


def test_base_output_builds_destination_from_city_and_state(
    monkeypatch,
):
    monkeypatch.setattr(
        carrier_module,
        "_truck",
        lambda weight: "Truck test",
    )
    monkeypatch.setattr(
        carrier_module,
        "_calculate_distance",
        lambda plant, zip_code: 250,
    )
    monkeypatch.setattr(
        carrier_module,
        "HISTORY_MONTHS",
        12,
    )

    calculation = {"antt": 1000}

    result = carrier_module._base_output(
        freight={"pedido": "P123", "trechos": [1, 2]},
        id_="F123",
        calculation=calculation,
        plant={"cidade": "Campinas", "codigo": "1210"},
        zip_code="13053050",
        weight=1500,
        dest_city="São Paulo",
        dest_state="SP",
    )

    assert result["id"] == "F123"
    assert result["pedido"] == "P123"
    assert result["destino"] == "São Paulo, SP"
    assert result["origem"] == "Campinas (1210)"
    assert result["paradas"] == 2
    assert result["peso"] == "1.500 kg"
    assert result["caminhao"] == "Truck test"
    assert result["distancia_km"] == 250
    assert result["custos_ref"] is calculation
    assert result["periodo_historico_meses"] == 12
    assert result["alternativas"] == []
    assert result["referencia_economica_disponivel"] is False
    assert result["similarity"] is None
    assert result["similarRoutes"] is None


def test_base_output_uses_zip_when_city_is_missing(
    monkeypatch,
):
    monkeypatch.setattr(carrier_module, "_truck", lambda weight: None)
    monkeypatch.setattr(
        carrier_module,
        "_calculate_distance",
        lambda plant, zip_code: None,
    )
    monkeypatch.setattr(
        carrier_module,
        "_reference_costs",
        lambda freight: {"antt": 500},
    )

    result = carrier_module._base_output(
        freight={"trechos": []},
        id_="F1",
        calculation=None,
        plant={"cidade": "Campinas", "codigo": "1210"},
        zip_code="13053050",
        weight=1000,
        dest_city=None,
        dest_state="SP",
    )

    assert result["destino"] == "CEP 13053050"
    assert result["custos_ref"] == {"antt": 500}
    assert result["pedido"] == "—"


def test_base_output_uses_unknown_destination_when_city_and_zip_missing(
    monkeypatch,
):
    monkeypatch.setattr(carrier_module, "_truck", lambda weight: None)
    monkeypatch.setattr(
        carrier_module,
        "_calculate_distance",
        lambda plant, zip_code: None,
    )
    monkeypatch.setattr(
        carrier_module,
        "_reference_costs",
        lambda freight: None,
    )

    result = carrier_module._base_output(
        freight={},
        id_="F2",
        calculation=None,
        plant={"cidade": "Campinas", "codigo": "1210"},
        zip_code=None,
        weight=500,
        dest_city=None,
        dest_state=None,
    )

    assert result["destino"] == "Destino não informado"
    assert result["custos_ref"] is None
    assert result["paradas"] == 0


def test_no_recommendation_fills_expected_fields():
    output = {
        "alternativas": ["old"],
        "aviso": "old warning",
    }

    alternatives = [{"nome": "Transportadora A"}]

    result = carrier_module._no_recommendation(
        output,
        kind="Sem histórico",
        detail="Não há dados suficientes.",
        alternatives=alternatives,
    )

    assert result is output
    assert result["tipo"] == "Sem histórico"
    assert result["transportadora"] == "—"
    assert result["custo"] == "—"
    assert result["sla"] == "—"
    assert result["confianca"] == "Baixa"
    assert result["detalhe"] == "Não há dados suficientes."
    assert result["aviso"] is not None
    assert result["alternativas"] is alternatives


def test_no_recommendation_uses_empty_alternatives_when_none():
    output = {}

    result = carrier_module._no_recommendation(
        output,
        kind="Sem histórico",
        detail="Sem dados.",
        alternatives=None,
    )

    assert result["alternativas"] == []


def _similarity_scope():
    return pd.DataFrame({
        "freight_id": [
            "F1", "F2", "F3", "F4", "F5", "F6",
        ],
        "cidade_destino": [
            "Campinas",
            "Campinas",
            "Jundiaí",
            "Sorocaba",
            "Santos",
            "Ribeirão Preto",
        ],
    })


def test_fill_similarity_does_nothing_for_state_scope():
    output = {
        "similarity": None,
        "similarRoutes": None,
    }

    carrier_module._fill_similarity(
        output,
        key="state",
        level=None,
        zip_code="13053050",
        plant={"cidade": "Campinas"},
        dest_city="São Paulo",
        scope_trips=_similarity_scope(),
        scope_trip_count=10,
        raw_sla=0.9,
    )

    assert output["similarity"] is None
    assert output["similarRoutes"] is None


def test_fill_similarity_builds_direct_zip5_route():
    output = {}

    carrier_module._fill_similarity(
        output,
        key="zip",
        level=5,
        zip_code="13053050",
        plant={"cidade": "Campinas"},
        dest_city="Campinas",
        scope_trips=_similarity_scope(),
        scope_trip_count=6,
        raw_sla=0.9,
    )

    assert output["similarity"]["viagens"] == 6
    assert output["similarity"]["distanciaOrigem"] == "mesma planta"
    assert output["similarity"]["distanciaDestino"] == "CEP 13053"
    assert output["similarity"]["sla"] == carrier_module._pct(0.9)

    assert len(output["similarRoutes"]) == 1
    assert output["similarRoutes"][0]["rota"] == "Campinas → Campinas"
    assert output["similarRoutes"][0]["viagens"] == "6 viagens"
    assert output["similarRoutes"][0]["detalhe"] == "Mesmo CEP de destino"


def test_fill_similarity_groups_zip4_routes_by_city():
    output = {}

    carrier_module._fill_similarity(
        output,
        key="zip",
        level=4,
        zip_code="13053050",
        plant={"cidade": "Campinas"},
        dest_city="Campinas",
        scope_trips=_similarity_scope(),
        scope_trip_count=6,
        raw_sla=0.8,
    )

    assert output["similarity"]["distanciaDestino"] == "CEP 1305…"

    routes = output["similarRoutes"]

    assert len(routes) == 4
    assert routes[0]["rota"] == "Campinas → Campinas"
    assert routes[0]["viagens"] == "2 viagens"
    assert routes[1]["rota"] == "Campinas → Jundiaí"


def test_fill_similarity_limits_routes_to_four_cities():
    output = {}

    carrier_module._fill_similarity(
        output,
        key="zip",
        level=3,
        zip_code="13053050",
        plant={"cidade": "Campinas"},
        dest_city="Campinas",
        scope_trips=_similarity_scope(),
        scope_trip_count=6,
        raw_sla=0.8,
    )

    assert len(output["similarRoutes"]) == 4


def test_fill_similarity_counts_distinct_freights_per_city():
    output = {}

    trips = pd.DataFrame({
        "freight_id": ["F1", "F1", "F2"],
        "cidade_destino": ["Campinas", "Campinas", "Jundiaí"],
    })

    carrier_module._fill_similarity(
        output,
        key="zip",
        level=4,
        zip_code="13053050",
        plant={"cidade": "Campinas"},
        dest_city="Campinas",
        scope_trips=trips,
        scope_trip_count=2,
        raw_sla=0.8,
    )

    routes = {
        item["rota"]: item["viagens"]
        for item in output["similarRoutes"]
    }

    assert routes["Campinas → Campinas"] == "1 viagens"
    assert routes["Campinas → Jundiaí"] == "1 viagens"



def test_recommend_returns_no_recommendation_when_period_history_is_empty(
    monkeypatch,
):
    freight = {
        "planta": {"codigo": "BR01"},
        "cep": "01310100",
        "peso_kg": 1000,
        "destino": "São Paulo",
        "uf": "SP",
    }

    output_base = {"custos_ref": 1500}

    monkeypatch.setattr(
        carrier_module,
        "_base_output",
        lambda *args: output_base.copy(),
    )
    monkeypatch.setattr(
        carrier_module,
        "_trip_history",
        lambda: pd.DataFrame({"freight_id": ["F1"]}),
    )
    monkeypatch.setattr(
        carrier_module,
        "_row_history",
        lambda: pd.DataFrame(),
    )
    monkeypatch.setattr(
        carrier_module,
        "_all_corporate_carriers",
        lambda history, rows: ["Transportadora Corporativa"],
    )
    monkeypatch.setattr(
        carrier_module,
        "_filter_period",
        lambda history, months: pd.DataFrame(),
    )

    no_recommendation_calls = []

    def fake_no_recommendation(output, status, message):
        no_recommendation_calls.append((status, message))
        output["status_teste"] = status
        return output

    monkeypatch.setattr(
        carrier_module,
        "_no_recommendation",
        fake_no_recommendation,
    )

    result = carrier_module.recommend(freight, "FRETE-001")

    assert result["status_teste"] == "Sem histórico"
    assert result["outras_transportadoras"] == [
        "Transportadora Corporativa"
    ]
    assert len(no_recommendation_calls) == 1


def test_recommend_returns_no_recommendation_when_scope_is_not_found(
    monkeypatch,
):
    freight = {
        "planta": {"codigo": "BR01"},
        "cep": "01310100",
        "peso_kg": 1000,
        "destino": "São Paulo",
        "uf": "SP",
    }

    history = pd.DataFrame({
        "freight_id": ["F1"],
        "data_fim": [pd.Timestamp("2026-01-01")],
        "sla_ok": [True],
    })

    output_base = {"custos_ref": 1500}

    monkeypatch.setattr(
        carrier_module,
        "_base_output",
        lambda *args: output_base.copy(),
    )
    monkeypatch.setattr(
        carrier_module,
        "_trip_history",
        lambda: history,
    )
    monkeypatch.setattr(
        carrier_module,
        "_row_history",
        lambda: pd.DataFrame(),
    )
    monkeypatch.setattr(
        carrier_module,
        "_all_corporate_carriers",
        lambda history, rows: [],
    )
    monkeypatch.setattr(
        carrier_module,
        "_filter_period",
        lambda history, months: history.copy(),
    )
    monkeypatch.setattr(
        carrier_module,
        "_select_scope",
        lambda **kwargs: None,
    )

    def fake_no_recommendation(output, status, message):
        output["status_teste"] = status
        output["mensagem_teste"] = message
        return output

    monkeypatch.setattr(
        carrier_module,
        "_no_recommendation",
        fake_no_recommendation,
    )

    result = carrier_module.recommend(freight, "FRETE-002")

    assert result["status_teste"] == "Sem histórico"
    assert "histórico suficiente" in result["mensagem_teste"]
    assert result["outras_transportadoras"] == []



def test_recommend_builds_complete_result_for_zip5_scope(monkeypatch):
    freight = {
        "planta": {"codigo": "BR01", "nome": "Planta Campinas", "cep": "13000000"},
        "cep": "01310100",
        "peso_kg": 1000,
        "destino": "São Paulo",
        "uf": "SP",
    }

    history = pd.DataFrame({
        "freight_id": ["F1", "F2"],
        "data_fim": [
            pd.Timestamp("2026-01-01"),
            pd.Timestamp("2026-02-01"),
        ],
        "sla_ok": [True, False],
    })

    scope_trips = pd.DataFrame({
        "freight_id": ["F1", "F2", "F3", "F4"],
    })

    valid = pd.DataFrame(
        {
            "trips": [10],
            "sla": [0.95],
            "adjusted_sla": [0.99],
            "avg_paid_trip": [1700.0],
            "brl_per_100kg": [100.0],
        },
        index=["Transportadora A"],
    )

    reference = {
        "estimativa_frete": 1800.0,
        "media_pago": 1750.0,
        "rs_por_kg": 2.5,
    }

    monkeypatch.setattr(
        carrier_module,
        "_base_output",
        lambda *args: {"custos_ref": {"antt": 1500.0}},
    )
    monkeypatch.setattr(
        carrier_module,
        "_trip_history",
        lambda: history,
    )
    monkeypatch.setattr(
        carrier_module,
        "_row_history",
        lambda: pd.DataFrame(),
    )
    monkeypatch.setattr(
        carrier_module,
        "_all_corporate_carriers",
        lambda history, rows: ["Transportadora B"],
    )
    monkeypatch.setattr(
        carrier_module,
        "_filter_period",
        lambda history, months: history.copy(),
    )
    monkeypatch.setattr(
        carrier_module,
        "_select_scope",
        lambda **kwargs: (
            "zip",
            5,
            scope_trips,
            valid,
        ),
    )

    economic_calls = []

    def fake_economic_reference(trips, rows, carrier, weight):
        economic_calls.append((trips, rows, carrier, weight))
        return reference.copy()

    monkeypatch.setattr(
        carrier_module,
        "_economic_reference",
        fake_economic_reference,
    )
    monkeypatch.setattr(
        carrier_module,
        "_broader_tables",
        lambda *args: [],
    )
    monkeypatch.setattr(
        carrier_module,
        "_build_alternatives",
        lambda tables, excluded: ["Transportadora B"],
    )
    monkeypatch.setattr(
        carrier_module,
        "_build_detail",
        lambda *args: "Detalhe do escopo ZIP5",
    )

    monkeypatch.setattr(
        carrier_module,
        "_scope_warning",
        lambda key: "Aviso de escopo",
    )
    monkeypatch.setattr(
        carrier_module,
        "_tie_warning",
        lambda tied: None,
    )
    monkeypatch.setattr(
        carrier_module,
        "_concentration_warning",
        lambda *args: "Aviso de concentração",
    )
    monkeypatch.setattr(
        carrier_module,
        "_atypical_weight_warning",
        lambda *args: None,
    )
    monkeypatch.setattr(
        carrier_module,
        "_reference_warning",
        lambda *args: "Aviso de referência",
    )

    similarity_calls = []

    def fake_fill_similarity(*args):
        similarity_calls.append(args)
        args[0]["similaridade_teste"] = True

    monkeypatch.setattr(
        carrier_module,
        "_fill_similarity",
        fake_fill_similarity,
    )

    result = carrier_module.recommend(freight, "FRETE-003")

    # Transportadora recomendada e dados do ranking.
    assert result["transportadora"] == "Transportadora A"
    assert result["sla"] == "95%"
    assert result["confianca"] == "Alta"
    assert result["empate"] is False
    assert result["empatadas"] == []

    # Escopo e volume histórico.
    assert result["escopo"] == "CEP5"
    assert result["viagens_similares"] == 4
    assert result["viagens_transportadora"] == 10

    # Referência econômica.
    assert result["referencia_economica_disponivel"] is True
    assert result["referencia_economica"]["razao_vs_antt"] == 1.2
    assert result["custo_medio_frete"] == 1750.0
    assert result["rs_por_kg"] == 2.5
    assert result["media_paga_viagem"] == 1700.0
    assert result["media_paga_viagem_valorada"] == 1700.0

    # Alternativas e transportadoras corporativas.
    assert result["alternativas"] == ["Transportadora B"]
    assert result["outras_transportadoras"] == ["Transportadora B"]

    # Alertas.
    assert result["avisos"] == [
        "Aviso de escopo",
        "Aviso de concentração",
        "Aviso de referência",
    ]
    assert result["aviso"] == (
        "Aviso de escopo Aviso de concentração Aviso de referência"
    )

    # Outros campos.
    assert result["detalhe"] == "Detalhe do escopo ZIP5"
    assert result["rota_multipla_historico"] is False
    assert result["similaridade_teste"] is True

    # Confirma que a referência econômica só foi calculada para o
    # escopo ZIP5, usando a transportadora vencedora e o peso da carga.
    assert len(economic_calls) == 1
    assert economic_calls[0][0] is scope_trips
    assert economic_calls[0][2:] == ("Transportadora A", 1000)

    # Confirma que a similaridade foi preenchida ao final.
    assert len(similarity_calls) == 1
    assert similarity_calls[0][1:4] == (
        "zip",
        5,
        "01310100",
    )



def test_zip_info_returns_and_caches_successful_lookup(monkeypatch):
    cache = {}
    expected = {"logradouro": "Avenida Paulista"}

    monkeypatch.setattr(carrier_module, "_zip_cache", cache)
    monkeypatch.setattr(
        carrier_module,
        "validar_cep",
        lambda cep: expected,
    )

    result = carrier_module._zip_info("01310-100")

    assert result == expected
    assert cache == {"01310100": expected}


def test_zip_info_uses_cached_value_without_new_lookup(monkeypatch):
    expected = {"logradouro": "Avenida Paulista"}

    monkeypatch.setattr(
        carrier_module,
        "_zip_cache",
        {"01310100": expected},
    )

    def unexpected_lookup(cep):
        pytest.fail("A consulta não deveria ocorrer para um CEP em cache")

    monkeypatch.setattr(
        carrier_module,
        "validar_cep",
        unexpected_lookup,
    )

    result = carrier_module._zip_info("01310100")

    assert result is expected


def test_zip_info_does_not_cache_empty_result(monkeypatch):
    cache = {}
    calls = []

    def lookup(cep):
        calls.append(cep)
        return None

    monkeypatch.setattr(carrier_module, "_zip_cache", cache)
    monkeypatch.setattr(carrier_module, "validar_cep", lookup)

    assert carrier_module._zip_info("01310100") is None
    assert carrier_module._zip_info("01310100") is None

    assert calls == ["01310100", "01310100"]
    assert cache == {}


def test_zip_info_handles_lookup_exception_without_caching(monkeypatch):
    cache = {}

    def lookup(cep):
        raise RuntimeError("Falha simulada na consulta")

    monkeypatch.setattr(carrier_module, "_zip_cache", cache)
    monkeypatch.setattr(carrier_module, "validar_cep", lookup)

    result = carrier_module._zip_info("01310100")

    assert result is None
    assert cache == {}




def test_prepare_trips_creates_missing_weight_when_both_columns_are_absent():
    source = pd.DataFrame({
        "freight_id": ["F1"],
        "service_agent_description": ["Transportadora A"],
        "issuing_plant_code": ["BR01"],
        "cep_destino": ["01310100"],
        "sla_frete": [1],
        "valor_pago": [1500.0],
    })

    result = carrier_module._prepare_trips(source)

    assert "peso_kg" in result.columns
    assert pd.isna(result.loc[0, "peso_kg"])
    assert "peso_kg" not in source.columns



def test_scopes_without_zip_code_returns_state_scope():
    state_col = carrier_module.DEST_STATE_COL

    base = pd.DataFrame({
        "issuing_plant_code": ["BR01", "BR01", "BR02"],
        "cep_destino": ["01310100", "04538132", "01310100"],
        state_col: ["SP", "SP", "SP"],
    })

    scopes = list(
        carrier_module._scopes(
            base=base,
            plant_code="BR01",
            zip_code="",
            state="SP",
        )
    )

    assert len(scopes) == 1

    key, level, trips = scopes[0]

    assert key == "state"
    assert level is None
    assert len(trips) == 2
    assert set(trips["issuing_plant_code"]) == {"BR01"}



def test_select_scope_skips_empty_scope_and_returns_next_valid_scope(monkeypatch):
    empty_scope = pd.DataFrame()
    valid_scope = pd.DataFrame({
        "issuing_plant_code": ["BR01"],
        "cep_destino": ["01310100"],
    })
    valid_table = pd.DataFrame({
        "carrier": ["Transportadora A"],
        "sla": [0.95],
    })

    calls = []

    def fake_scopes(*args):
        yield "zip", 5, empty_scope
        yield "zip", 4, valid_scope

    def fake_by_carrier(scope_trips, *args):
        calls.append(scope_trips)
        return valid_table

    monkeypatch.setattr(
        carrier_module,
        "_scopes",
        fake_scopes,
    )
    monkeypatch.setattr(
        carrier_module,
        "_by_carrier",
        fake_by_carrier,
    )
    monkeypatch.setattr(
        carrier_module,
        "_valid",
        lambda table: table,
    )

    result = carrier_module._select_scope(
        base=pd.DataFrame(),
        plant_code="BR01",
        zip_code="01310100",
        state="SP",
        global_sla_mean=0.8,
    )

    assert result is not None
    key, level, scope_trips, valid = result

    assert key == "zip"
    assert level == 4
    assert scope_trips is valid_scope
    assert valid is valid_table

    # O escopo vazio foi ignorado antes de chamar _by_carrier.
    assert len(calls) == 1
    assert calls[0] is valid_scope



def test_broader_tables_skips_empty_and_invalid_scopes(monkeypatch):
    winner_scope = pd.DataFrame({"carrier": ["Vencedora"]})
    empty_scope = pd.DataFrame()
    invalid_scope = pd.DataFrame({"carrier": ["Sem dados válidos"]})
    valid_scope = pd.DataFrame({"carrier": ["Alternativa"]})

    scopes = [
        ("zip", 5, winner_scope),
        ("zip", 4, empty_scope),
        ("zip", 3, invalid_scope),
        ("state", None, valid_scope),
    ]

    calls = []

    def fake_scopes(*args):
        yield from scopes

    def fake_by_carrier(scope_trips, *args):
        calls.append(scope_trips)
        if scope_trips is invalid_scope:
            return pd.DataFrame({"carrier": ["Inválida"]})
        return pd.DataFrame({"carrier": ["Alternativa"]})

    def fake_valid(table):
        if table.iloc[0]["carrier"] == "Inválida":
            return pd.DataFrame()
        return table

    monkeypatch.setattr(carrier_module, "_scopes", fake_scopes)
    monkeypatch.setattr(carrier_module, "_by_carrier", fake_by_carrier)
    monkeypatch.setattr(carrier_module, "_valid", fake_valid)

    result = list(
        carrier_module._broader_tables(
            base=pd.DataFrame(),
            plant_code="BR01",
            zip_code="01310100",
            state="SP",
            global_sla_mean=0.8,
            weight_kg=1000,
            ref_date=None,
            rows=None,
            winning_key="zip",
            winning_level=5,
        )
    )

    assert len(result) == 1
    assert result[0][0] == "state"
    assert result[0][1] is None
    assert result[0][2]["carrier"].tolist() == ["Alternativa"]

    # O vencedor não é processado; o escopo vazio também é ignorado.
    assert len(calls) == 2
    assert calls[0] is invalid_scope
    assert calls[1] is valid_scope



def test_broader_tables_returns_nothing_when_winner_is_last_scope(monkeypatch):
    scopes = [
        ("zip", 5, pd.DataFrame({"carrier": ["A"]})),
        ("zip", 4, pd.DataFrame({"carrier": ["B"]})),
    ]

    def fake_scopes(*args):
        yield from scopes

    def unexpected_call(*args):
        pytest.fail("Não deveria processar escopos anteriores ao vencedor")

    monkeypatch.setattr(carrier_module, "_scopes", fake_scopes)
    monkeypatch.setattr(carrier_module, "_by_carrier", unexpected_call)

    result = list(
        carrier_module._broader_tables(
            base=pd.DataFrame(),
            plant_code="BR01",
            zip_code="01310100",
            state="SP",
            global_sla_mean=0.8,
            weight_kg=1000,
            ref_date=None,
            rows=None,
            winning_key="zip",
            winning_level=4,
        )
    )

    assert result == []



def test_clean_zip_continues_when_isna_raises():
    class InvalidIsNa:
        def __str__(self):
            return "01310100"

    value = InvalidIsNa()

    # Faz pd.isna(value) lançar uma exceção.
    original_isna = pd.isna

    def fake_isna(item):
        if item is value:
            raise RuntimeError("Falha simulada")
        return original_isna(item)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(carrier_module.pd, "isna", fake_isna)
        result = carrier_module._clean_zip(value)

    assert result == "01310100"


def test_clean_zip_continues_when_float_to_int_raises():
    result = carrier_module._clean_zip(float("inf"))

    assert result == ""


def test_to_float_continues_when_isna_raises():
    class InvalidIsNa:
        def __float__(self):
            return 12.5

    value = InvalidIsNa()
    original_isna = pd.isna

    def fake_isna(item):
        if item is value:
            raise RuntimeError("Falha simulada")
        return original_isna(item)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(carrier_module.pd, "isna", fake_isna)
        result = carrier_module._to_float(value)

    assert result == 12.5


def test_to_float_returns_none_when_float_conversion_is_invalid():
    assert carrier_module._to_float("valor inválido") is None


def test_prepare_trips_keeps_existing_weight_without_quantity():
    source = pd.DataFrame({
        "freight_id": ["F1"],
        "service_agent_description": ["Transportadora A"],
        "issuing_plant_code": ["BR01"],
        "cep_destino": ["01310100"],
        "sla_frete": [1],
        "valor_pago": [1500.0],
        "peso_kg": [1250.0],
    })

    result = carrier_module._prepare_trips(source)

    assert result["peso_kg"].tolist() == [1250.0]



def test_zip_info_returns_none_when_zip_is_invalid(monkeypatch):
    def unexpected_lookup(cep):
        pytest.fail("Não deveria consultar CEP inválido")

    monkeypatch.setattr(
        carrier_module,
        "validar_cep",
        unexpected_lookup,
    )

    result = carrier_module._zip_info("CEP inválido")

    assert result is None
