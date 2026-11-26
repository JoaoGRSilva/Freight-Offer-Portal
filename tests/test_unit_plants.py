
import pytest

from analytics import plants


# ============================================================
# extrair_codigo
# ============================================================

@pytest.mark.parametrize(
    "valor",
    [
        1313,
        "1313",
        "fretes_1313.xlsx",
        "1313-DNP SAO ROQUE",
        "arquivo_1313_final.xlsx",
    ],
)
def test_extrair_codigo_reconhece_formatos_validos(
    monkeypatch,
    valor,
):
    monkeypatch.setattr(
        plants,
        "known_codes",
        lambda: {"1313"},
    )

    assert plants.extrair_codigo(valor) == "1313"


def test_extrair_codigo_ignora_ano_e_encontra_codigo_cadastrado(
    monkeypatch,
):
    monkeypatch.setattr(
        plants,
        "known_codes",
        lambda: {"1313"},
    )

    assert plants.extrair_codigo("2026_fretes_1313.xlsx") == "1313"


def test_extrair_codigo_retorna_primeiro_codigo_cadastrado(
    monkeypatch,
):
    monkeypatch.setattr(
        plants,
        "known_codes",
        lambda: {"1313", "2424", "3535"},
    )

    assert plants.extrair_codigo(
        "arquivo_1313_2424_3535.xlsx"
    ) == "1313"


def test_extrair_codigo_ignora_codigo_nao_cadastrado(
    monkeypatch,
):
    monkeypatch.setattr(
        plants,
        "known_codes",
        lambda: {"2424"},
    )

    assert plants.extrair_codigo("fretes_1313.xlsx") is None


def test_extrair_codigo_procura_proximo_codigo_cadastrado(
    monkeypatch,
):
    monkeypatch.setattr(
        plants,
        "known_codes",
        lambda: {"2424"},
    )

    assert plants.extrair_codigo(
        "arquivo_1313_2424.xlsx"
    ) == "2424"


@pytest.mark.parametrize(
    "valor",
    [
        None,
        "",
        "arquivo_sem_codigo.xlsx",
        "123",
        "12345",
        "123456",
        "A12345B",
    ],
)
def test_extrair_codigo_retorna_none_sem_codigo_valido(
    monkeypatch,
    valor,
):
    monkeypatch.setattr(
        plants,
        "known_codes",
        lambda: {"1234", "12345", "123456"},
    )

    assert plants.extrair_codigo(valor) is None


def test_extrair_codigo_rejeita_numero_de_quatro_digitos_nao_cadastrado(
    monkeypatch,
):
    monkeypatch.setattr(
        plants,
        "known_codes",
        lambda: set(),
    )

    assert plants.extrair_codigo("1313") is None


def test_extrair_codigo_ignora_numero_embutido_em_numero_maior(
    monkeypatch,
):
    monkeypatch.setattr(
        plants,
        "known_codes",
        lambda: {"1313"},
    )

    assert plants.extrair_codigo("12313134") is None


def test_extrair_codigo_aceita_codigo_delimitado_por_letras(
    monkeypatch,
):
    monkeypatch.setattr(
        plants,
        "known_codes",
        lambda: {"1313"},
    )

    assert plants.extrair_codigo("PLANTA1313DNP") == "1313"


def test_extrair_codigo_converte_valor_para_string(
    monkeypatch,
):
    monkeypatch.setattr(
        plants,
        "known_codes",
        lambda: {"1313"},
    )

    class Codigo:
        def __str__(self):
            return "arquivo_1313.xlsx"

    assert plants.extrair_codigo(Codigo()) == "1313"


def test_extrair_codigo_consulta_cadastro_dinamico(
    monkeypatch,
):
    chamadas = []

    def fake_known_codes():
        chamadas.append(True)
        return {"1313"}

    monkeypatch.setattr(
        plants,
        "known_codes",
        fake_known_codes,
    )

    assert plants.extrair_codigo("1313") == "1313"
    assert len(chamadas) == 1


# ============================================================
# get_planta
# ============================================================

def test_get_planta_retorna_planta_cadastrada(
    monkeypatch,
):
    planta_esperada = {
        "codigo": "1313",
        "nome": "DNP SAO ROQUE",
        "cep": "18130-000",
        "cidade": "Sao Roque",
        "uf": "SP",
    }

    chamadas = []

    monkeypatch.setattr(
        plants,
        "known_codes",
        lambda: {"1313"},
    )

    def fake_get_usable_plant(codigo):
        chamadas.append(codigo)
        return planta_esperada

    monkeypatch.setattr(
        plants,
        "get_usable_plant",
        fake_get_usable_plant,
    )

    resultado = plants.get_planta("fretes_1313.xlsx")

    assert resultado == planta_esperada
    assert chamadas == ["1313"]


def test_get_planta_retorna_none_quando_codigo_nao_existe(
    monkeypatch,
):
    chamadas = []

    monkeypatch.setattr(
        plants,
        "known_codes",
        lambda: {"2424"},
    )

    monkeypatch.setattr(
        plants,
        "get_usable_plant",
        lambda codigo: chamadas.append(codigo),
    )

    resultado = plants.get_planta("fretes_1313.xlsx")

    assert resultado is None
    assert chamadas == []


def test_get_planta_retorna_none_quando_planta_nao_esta_utilizavel(
    monkeypatch,
):
    chamadas = []

    monkeypatch.setattr(
        plants,
        "known_codes",
        lambda: {"1313"},
    )

    def fake_get_usable_plant(codigo):
        chamadas.append(codigo)
        return None

    monkeypatch.setattr(
        plants,
        "get_usable_plant",
        fake_get_usable_plant,
    )

    resultado = plants.get_planta("1313")

    assert resultado is None
    assert chamadas == ["1313"]


@pytest.mark.parametrize(
    "valor",
    [
        None,
        "",
        "sem_codigo",
        "12345",
    ],
)
def test_get_planta_nao_consulta_repositorio_sem_codigo_valido(
    monkeypatch,
    valor,
):
    chamadas = []

    monkeypatch.setattr(
        plants,
        "known_codes",
        lambda: {"1313"},
    )

    monkeypatch.setattr(
        plants,
        "get_usable_plant",
        lambda codigo: chamadas.append(codigo),
    )

    assert plants.get_planta(valor) is None
    assert chamadas == []


def test_get_planta_aceita_codigo_cadastrado_mas_retorna_none_se_inativo(
    monkeypatch,
):
    chamadas = []

    monkeypatch.setattr(
        plants,
        "known_codes",
        lambda: {"1313"},
    )

    def fake_get_usable_plant(codigo):
        chamadas.append(codigo)
        # Simula planta inativa, pendente ou incompleta.
        return None

    monkeypatch.setattr(
        plants,
        "get_usable_plant",
        fake_get_usable_plant,
    )

    assert plants.get_planta("1313") is None
    assert chamadas == ["1313"]
