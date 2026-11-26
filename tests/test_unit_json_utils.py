
import math
from datetime import date, datetime
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from services.json_utils import json_safe


# ============================================================
# DICIONÁRIOS E ESTRUTURAS
# ============================================================

def test_json_safe_converte_valores_de_dicionario():
    resultado = json_safe({
        "nome": "Frete",
        "valor": 150.5,
        "ausente": None,
    })

    assert resultado == {
        "nome": "Frete",
        "valor": 150.5,
        "ausente": None,
    }


def test_json_safe_converte_estruturas_aninhadas():
    entrada = {
        "lista": [
            10,
            {
                "valor": np.int64(20),
                "ausente": np.nan,
            },
        ],
        "tupla": (1, 2),
    }

    resultado = json_safe(entrada)

    assert resultado == {
        "lista": [
            10,
            {
                "valor": 20,
                "ausente": None,
            },
        ],
        "tupla": [1, 2],
    }


def test_json_safe_converte_lista():
    assert json_safe([1, 2, 3]) == [1, 2, 3]


def test_json_safe_converte_tupla_para_lista():
    assert json_safe((1, 2, 3)) == [1, 2, 3]


def test_json_safe_converte_set_para_lista():
    resultado = json_safe({1, 2, 3})

    assert isinstance(resultado, list)
    assert set(resultado) == {1, 2, 3}


def test_json_safe_converte_set_com_valores_invalidos():
    resultado = json_safe({1.0, float("nan")})

    assert isinstance(resultado, list)
    assert 1.0 in resultado
    assert None in resultado


def test_json_safe_preserva_chaves_do_dicionario():
    entrada = {
        1: "um",
        "2": "dois",
    }

    resultado = json_safe(entrada)

    assert resultado == entrada
    assert 1 in resultado
    assert "2" in resultado


# ============================================================
# VALORES AUSENTES
# ============================================================

@pytest.mark.parametrize(
    "valor",
    [
        None,
        pd.NA,
        pd.NaT,
    ],
)
def test_json_safe_converte_valores_ausentes(valor):
    assert json_safe(valor) is None


def test_json_safe_converte_pd_na_dentro_de_estrutura():
    resultado = json_safe({
        "a": pd.NA,
        "b": [pd.NaT, None],
    })

    assert resultado == {
        "a": None,
        "b": [None, None],
    }


# ============================================================
# BOOLEANOS
# ============================================================

@pytest.mark.parametrize(
    "valor",
    [
        True,
        False,
        np.bool_(True),
        np.bool_(False),
    ],
)
def test_json_safe_converte_booleanos(valor):
    resultado = json_safe(valor)

    assert type(resultado) is bool
    assert resultado is bool(valor)


# ============================================================
# INTEIROS NUMPY
# ============================================================

@pytest.mark.parametrize(
    "valor",
    [
        np.int8(10),
        np.int16(100),
        np.int32(1000),
        np.int64(10000),
        np.uint8(10),
        np.uint16(100),
        np.uint32(1000),
        np.uint64(10000),
    ],
)
def test_json_safe_converte_inteiros_numpy(valor):
    resultado = json_safe(valor)

    assert type(resultado) is int
    assert resultado == int(valor)


# ============================================================
# FLOATS, DECIMAL E VALORES NÃO FINITOS
# ============================================================

@pytest.mark.parametrize(
    "valor",
    [
        10.5,
        np.float16(1.5),
        np.float32(2.5),
        np.float64(3.5),
        Decimal("12.75"),
        Decimal("0"),
    ],
)
def test_json_safe_converte_numeros_reais(valor):
    resultado = json_safe(valor)

    assert type(resultado) is float
    assert resultado == float(valor)


@pytest.mark.parametrize(
    "valor",
    [
        float("nan"),
        np.float64("nan"),
        Decimal("NaN"),
        float("inf"),
        float("-inf"),
        np.float64("inf"),
        np.float64("-inf"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_json_safe_converte_nan_e_infinito_para_none(valor):
    assert json_safe(valor) is None


def test_json_safe_preserva_float_zero():
    resultado = json_safe(0.0)

    assert resultado == 0.0
    assert type(resultado) is float


def test_json_safe_preserva_float_negativo():
    assert json_safe(-12.5) == -12.5


def test_json_safe_preserva_float_muito_pequeno():
    valor = 1e-300

    assert json_safe(valor) == valor


# ============================================================
# DATAS E HORÁRIOS
# ============================================================

def test_json_safe_converte_pandas_timestamp():
    valor = pd.Timestamp("2026-11-25 14:30:45")

    assert json_safe(valor) == "2026-11-25"


def test_json_safe_converte_timestamp_sem_horario():
    valor = pd.Timestamp("2026-01-15")

    assert json_safe(valor) == "2026-01-15"


def test_json_safe_converte_datetime():
    valor = datetime(2026, 11, 25, 14, 30, 45)

    assert json_safe(valor) == "2026-11-25T14:30:45"


def test_json_safe_converte_date():
    valor = date(2026, 11, 25)

    assert json_safe(valor) == "2026-11-25"


def test_json_safe_converte_datetime_com_microsegundos():
    valor = datetime(
        2026,
        11,
        25,
        14,
        30,
        45,
        123456,
    )

    assert json_safe(valor) == "2026-11-25T14:30:45.123456"


def test_json_safe_converte_datetime_com_fuso_horario():
    from datetime import timezone, timedelta

    fuso = timezone(timedelta(hours=-3))
    valor = datetime(
        2026,
        11,
        25,
        14,
        30,
        tzinfo=fuso,
    )

    assert json_safe(valor) == "2026-11-25T14:30:00-03:00"


# ============================================================
# TIPOS NÃO TRATADOS
# ============================================================

def test_json_safe_preserva_string():
    assert json_safe("frete") == "frete"


def test_json_safe_preserva_inteiro_python():
    resultado = json_safe(123)

    assert resultado == 123
    assert type(resultado) is int


def test_json_safe_preserva_objeto_nao_reconhecido():
    class ObjetoPersonalizado:
        pass

    valor = ObjetoPersonalizado()

    assert json_safe(valor) is valor


def test_json_safe_preserva_bytes():
    valor = b"frete"

    assert json_safe(valor) is valor


def test_json_safe_preserva_string_vazia():
    assert json_safe("") == ""


def test_json_safe_preserva_lista_vazia():
    assert json_safe([]) == []


def test_json_safe_preserva_dicionario_vazio():
    assert json_safe({}) == {}
