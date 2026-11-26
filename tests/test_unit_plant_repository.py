
import sqlite3
from datetime import datetime

import pytest

from analytics import config
from services import plant_repository as repo


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def plant_db(monkeypatch):
    """
    Banco SQLite isolado em memória.
    Todas as operações do repositório usam a mesma conexão.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    conn.executescript(
        """
        CREATE TABLE plants (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            zip_code TEXT,
            city TEXT,
            state TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            validation_status TEXT NOT NULL,
            notes TEXT,
            updated_at TEXT
        );

        CREATE TABLE user_plants (
            user_id INTEGER NOT NULL,
            plant_code TEXT NOT NULL
        );
        """
    )

    monkeypatch.setattr(repo, "connect", lambda _database: conn)
    monkeypatch.setattr(
        repo,
        "_cache",
        {"at": 0.0, "rows": None},
    )

    yield conn

    conn.close()


@pytest.fixture
def fake_clock(monkeypatch):
    """
    Relógio controlável para testar a expiração do cache.
    """
    clock = {"now": 100.0}

    monkeypatch.setattr(
        repo.time,
        "monotonic",
        lambda: clock["now"],
    )

    return clock


@pytest.fixture
def sample_plant(plant_db):
    repo.save_plant(
        code="1313",
        name="DNP SAO ROQUE",
        zip_code="18130000",
        city="Sao Roque",
        state="SP",
    )
    return repo.get_plant("1313")


@pytest.fixture
def fake_config(monkeypatch):
    plants = {
        "1313": (
            "DNP SAO ROQUE",
            "18130000",
            "Sao Roque",
            "SP",
        ),
        "2424": {
            "base1": (
                "PLANTA A",
                "01001000",
                "Sao Paulo",
                "SP",
            ),
            "base2": (
                "PLANTA B",
                "02002000",
                "Campinas",
                "SP",
            ),
            "status": "DIVERGENTE",
        },
    }

    monkeypatch.setattr(config, "PLANTS", plants)
    return plants


# ============================================================
# CONSTANTES E DATA
# ============================================================

def test_constantes_de_status():
    assert repo.STATUS_VALIDATED == "VALIDADO"
    assert repo.STATUS_PENDING == "PENDENTE"
    assert repo.VALID_STATUSES == ("VALIDADO", "PENDENTE")
    assert repo.VALIDATION_VALIDATED == "VALIDADO"


def test_ufs_contem_ufs_brasileiras():
    assert "SP" in repo.UFS
    assert "RJ" in repo.UFS
    assert "MG" in repo.UFS
    assert "DF" in repo.UFS
    assert len(repo.UFS) == 27


def test_now_retorna_timestamp_iso():
    resultado = repo._now()

    datetime.fromisoformat(resultado)

    assert len(resultado) == 19


# ============================================================
# FORMAT_ZIP
# ============================================================

@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("18130000", "18130-000"),
        ("18130-000", "18130-000"),
        (18130000, "18130-000"),
        ("18.130-000", "18130-000"),
        (" 18130 000 ", "18130-000"),
        ("", ""),
        (None, ""),
        (0, ""),
        (False, ""),
    ],
)
def test_format_zip_converte_cep(valor, esperado):
    assert repo.format_zip(valor) == esperado


@pytest.mark.parametrize(
    "valor",
    [
        "1234567",
        "123456789",
        "ABC123",
        "1234-567",
        "1234567890",
    ],
)
def test_format_zip_rejeita_cep_invalido(valor):
    with pytest.raises(ValueError, match="CEP deve ter 8"):
        repo.format_zip(valor)


# ============================================================
# DESCRIBE E CONFIG_ROWS
# ============================================================

def test_describe_formata_dados_da_planta():
    resultado = repo._describe(
        ("DNP SAO ROQUE", "18130000", "Sao Roque", "SP")
    )

    assert resultado == "DNP SAO ROQUE · CEP 18130000 · Sao Roque"


def test_describe_utiliza_fallback_para_campos_vazios():
    resultado = repo._describe(
        ("PLANTA TESTE", None, None, "SP")
    )

    assert resultado == "PLANTA TESTE · CEP — · —"


def test_config_rows_converte_planta_em_formato_tuple(
    fake_config,
):
    rows = repo._config_rows()

    planta = next(row for row in rows if row["code"] == "1313")

    assert planta == {
        "code": "1313",
        "name": "DNP SAO ROQUE",
        "zip_code": "18130000",
        "city": "Sao Roque",
        "state": "SP",
        "active": 1,
        "validation_status": repo.STATUS_VALIDATED,
        "notes": "Importada de analytics/config.py.",
    }


def test_config_rows_converte_planta_com_divergencia(
    fake_config,
):
    rows = repo._config_rows()

    planta = next(row for row in rows if row["code"] == "2424")

    assert planta["code"] == "2424"
    assert planta["name"] == "PLANTA A"
    assert planta["zip_code"] is None
    assert planta["city"] is None
    assert planta["state"] is None
    assert planta["active"] == 1
    assert planta["validation_status"] == repo.STATUS_PENDING

    assert "DIVERGENTE" in planta["notes"]
    assert "PLANTA A" in planta["notes"]
    assert "PLANTA B" in planta["notes"]
    assert "18130000" not in planta["notes"]


def test_config_rows_retorna_lista_vazia_quando_config_vazio(
    monkeypatch,
):
    monkeypatch.setattr(config, "PLANTS", {})

    assert repo._config_rows() == []


# ============================================================
# INVALIDAÇÃO DE CACHE
# ============================================================

def test_invalidate_cache_limpa_timestamp_e_rows():
    repo._cache["at"] = 123.0
    repo._cache["rows"] = {"1313": {"code": "1313"}}

    repo._invalidate_cache()

    assert repo._cache["at"] == 0.0
    assert repo._cache["rows"] is None


# ============================================================
# SEED
# ============================================================

def test_seed_insere_plantas_quando_banco_vazio(
    plant_db,
    fake_config,
):
    quantidade = repo.seed_plants_from_config()

    assert quantidade == 2

    rows = plant_db.execute(
        "SELECT * FROM plants ORDER BY code"
    ).fetchall()

    assert len(rows) == 2

    planta = repo.get_plant("1313")

    assert planta["name"] == "DNP SAO ROQUE"
    assert planta["validation_status"] == repo.STATUS_VALIDATED
    assert planta["updated_at"] is not None


def test_seed_nao_insere_quando_banco_ja_tem_plantas(
    plant_db,
    fake_config,
):
    repo.save_plant(
        "9999",
        "PLANTA EXISTENTE",
        "18130000",
        "Sao Roque",
        "SP",
    )

    quantidade = repo.seed_plants_from_config()

    assert quantidade == 0
    assert repo.get_plant("9999") is not None
    assert repo.get_plant("1313") is None


def test_seed_invalida_cache_apos_insercao(
    plant_db,
    fake_config,
):
    repo._cache["at"] = 100.0
    repo._cache["rows"] = {"antigo": {}}

    repo.seed_plants_from_config()

    assert repo._cache["at"] == 0.0
    assert repo._cache["rows"] is None


def test_seed_com_config_vazio_retorna_zero(
    plant_db,
    monkeypatch,
):
    monkeypatch.setattr(config, "PLANTS", {})

    assert repo.seed_plants_from_config() == 0


# ============================================================
# LEITURA
# ============================================================

def test_list_plants_retorna_todas_as_plantas(
    plant_db,
):
    repo.save_plant(
        "2424", "PLANTA B", "18130000", "Sao Roque", "SP"
    )
    repo.save_plant(
        "1313", "PLANTA A", "18130000", "Sao Roque", "SP"
    )

    resultado = repo.list_plants()

    assert len(resultado) == 2
    assert [row["code"] for row in resultado] == ["1313", "2424"]


def test_list_plants_filtra_plantas_ativas(
    plant_db,
):
    repo.save_plant(
        "1313", "ATIVA", "18130000", "Sao Roque", "SP"
    )
    repo.save_plant(
        "2424", "INATIVA", "18130000", "Sao Roque", "SP",
        active=False,
    )

    resultado = repo.list_plants(only_active=True)

    assert len(resultado) == 1
    assert resultado[0]["code"] == "1313"


def test_list_plants_retorna_lista_vazia(plant_db):
    assert repo.list_plants() == []


def test_get_plant_retorna_planta_existente(
    plant_db,
    sample_plant,
):
    resultado = repo.get_plant("1313")

    assert resultado["code"] == "1313"
    assert resultado["name"] == "DNP SAO ROQUE"


def test_get_plant_normaliza_codigo(
    plant_db,
    sample_plant,
):
    resultado = repo.get_plant(" 1313 ")

    assert resultado["code"] == "1313"


def test_get_plant_retorna_none_quando_nao_existe(
    plant_db,
):
    assert repo.get_plant("9999") is None


# ============================================================
# CACHE E FALLBACK
# ============================================================

def test_rows_cached_carrega_dados_do_banco(
    plant_db,
    sample_plant,
    fake_clock,
):
    resultado = repo._rows_cached()

    assert "1313" in resultado
    assert resultado["1313"]["name"] == "DNP SAO ROQUE"
    assert repo._cache["at"] == 100.0


def test_rows_cached_reutiliza_cache_antes_da_expiracao(
    plant_db,
    sample_plant,
    fake_clock,
    monkeypatch,
):
    primeira = repo._rows_cached()

    def erro_se_consultar_novamente(_database):
        raise AssertionError("O banco não deveria ser consultado.")

    monkeypatch.setattr(repo, "connect", erro_se_consultar_novamente)

    fake_clock["now"] = 110.0

    segunda = repo._rows_cached()

    assert segunda is primeira


def test_rows_cached_atualiza_cache_apos_expiracao(
    plant_db,
    sample_plant,
    fake_clock,
):
    primeira = repo._rows_cached()

    fake_clock["now"] = 100.0 + repo._CACHE_TTL_SEC + 1

    repo.save_plant(
        "2424",
        "PLANTA NOVA",
        "18130000",
        "Sao Roque",
        "SP",
    )

    segunda = repo._rows_cached()

    assert primeira is not segunda
    assert "2424" in segunda


def test_rows_cached_usa_config_quando_tabela_nao_existe(
    monkeypatch,
    fake_config,
    fake_clock,
):
    def connect_sem_tabela(_database):
        raise sqlite3.OperationalError("no such table: plants")

    monkeypatch.setattr(repo, "connect", connect_sem_tabela)

    resultado = repo._rows_cached()

    assert "1313" in resultado
    assert "2424" in resultado
    assert resultado["1313"]["name"] == "DNP SAO ROQUE"


def test_rows_cached_usa_config_quando_banco_vazio(
    plant_db,
    fake_config,
    fake_clock,
):
    resultado = repo._rows_cached()

    assert "1313" in resultado
    assert "2424" in resultado


def test_rows_cached_nao_grava_fallback_no_banco(
    plant_db,
    fake_config,
    fake_clock,
):
    repo._rows_cached()

    quantidade = plant_db.execute(
        "SELECT COUNT(*) FROM plants"
    ).fetchone()[0]

    assert quantidade == 0


def test_known_codes_retorna_codigos_do_cache(
    plant_db,
    fake_config,
):
    repo.save_plant(
        "1313",
        "PLANTA",
        "18130000",
        "Sao Roque",
        "SP",
    )

    assert repo.known_codes() == {"1313"}


def test_known_codes_retorna_codigos_do_fallback(
    monkeypatch,
    fake_config,
    fake_clock,
):
    monkeypatch.setattr(
        repo,
        "connect",
        lambda _database: (_ for _ in ()).throw(
            sqlite3.OperationalError("no such table: plants")
        ),
    )

    assert repo.known_codes() == {"1313", "2424"}


# ============================================================
# GET_USABLE_PLANT
# ============================================================

def test_get_usable_plant_retorna_planta_valida(
    plant_db,
    sample_plant,
):
    resultado = repo.get_usable_plant("1313")

    assert resultado == {
        "codigo": "1313",
        "nome": "DNP SAO ROQUE",
        "cep": "18130-000",
        "cidade": "Sao Roque",
        "uf": "SP",
    }


def test_get_usable_plant_normaliza_codigo(
    plant_db,
    sample_plant,
):
    resultado = repo.get_usable_plant(" 1313 ")

    assert resultado["codigo"] == "1313"


def test_get_usable_plant_retorna_none_quando_nao_existe(
    plant_db,
):
    assert repo.get_usable_plant("9999") is None


def test_get_usable_plant_rejeita_planta_inativa(
    plant_db,
):
    repo.save_plant(
        "1313",
        "INATIVA",
        "18130000",
        "Sao Roque",
        "SP",
        active=False,
    )

    assert repo.get_usable_plant("1313") is None


def test_get_usable_plant_rejeita_planta_pendente(
    plant_db,
):
    repo.save_plant(
        "1313",
        "PENDENTE",
        "",
        "",
        "",
        validation_status=repo.STATUS_PENDING,
    )

    assert repo.get_usable_plant("1313") is None


@pytest.mark.parametrize(
    ("zip_code", "city", "state"),
    [
        ("", "Sao Roque", "SP"),
        ("18130000", "", "SP"),
        ("18130000", "Sao Roque", ""),
    ],
)
def test_get_usable_plant_rejeita_cadastro_incompleto(
    plant_db,
    zip_code,
    city,
    state,
):
    repo.save_plant(
        "1313",
        "INCOMPLETA",
        zip_code,
        city,
        state,
        validation_status=repo.STATUS_PENDING,
    )

    assert repo.get_usable_plant("1313") is None


# ============================================================
# SAVE_PLANT - VALIDAÇÕES
# ============================================================

@pytest.mark.parametrize(
    "code",
    [
        "",
        None,
        "123",
        "12345",
        "ABCD",
        "12A4",
        " 123 ",
    ],
)
def test_save_plant_rejeita_codigo_invalido(
    plant_db,
    code,
):
    with pytest.raises(ValueError, match="Código da planta"):
        repo.save_plant(
            code,
            "PLANTA",
            "18130000",
            "Sao Roque",
            "SP",
        )


@pytest.mark.parametrize(
    "name",
    [
        "",
        None,
        "   ",
    ],
)
def test_save_plant_rejeita_nome_vazio(
    plant_db,
    name,
):
    with pytest.raises(ValueError, match="Nome da planta"):
        repo.save_plant(
            "1313",
            name,
            "18130000",
            "Sao Roque",
            "SP",
        )


def test_save_plant_rejeita_cep_invalido(plant_db):
    with pytest.raises(ValueError, match="CEP deve ter 8"):
        repo.save_plant(
            "1313",
            "PLANTA",
            "123",
            "Sao Roque",
            "SP",
        )


def test_save_plant_rejeita_uf_invalida(plant_db):
    with pytest.raises(ValueError, match="UF inválida"):
        repo.save_plant(
            "1313",
            "PLANTA",
            "18130000",
            "Sao Roque",
            "XX",
        )


def test_save_plant_normaliza_uf_minuscula(plant_db):
    repo.save_plant(
        "1313",
        "PLANTA",
        "18130000",
        "Sao Roque",
        "sp",
    )

    assert repo.get_plant("1313")["state"] == "SP"


def test_save_plant_permite_uf_vazia_para_pendente(
    plant_db,
):
    repo.save_plant(
        "1313",
        "PLANTA",
        "",
        "",
        "",
        validation_status=repo.STATUS_PENDING,
    )

    planta = repo.get_plant("1313")

    assert planta["state"] == ""
    assert planta["validation_status"] == repo.STATUS_PENDING


def test_save_plant_rejeita_status_invalido(plant_db):
    with pytest.raises(ValueError, match="Status de validação"):
        repo.save_plant(
            "1313",
            "PLANTA",
            "18130000",
            "Sao Roque",
            "SP",
            validation_status="INVALIDO",
        )


def test_save_plant_normaliza_status_minusculo(plant_db):
    repo.save_plant(
        "1313",
        "PLANTA",
        "18130000",
        "Sao Roque",
        "SP",
        validation_status="validado",
    )

    assert repo.get_plant("1313")["validation_status"] == "VALIDADO"


def test_save_plant_rejeita_status_vazio(plant_db):
    with pytest.raises(ValueError, match="Status de validação"):
        repo.save_plant(
            "1313",
            "PLANTA",
            "18130000",
            "Sao Roque",
            "SP",
            validation_status="",
        )


def test_save_plant_rejeita_validacao_sem_cep(
    plant_db,
):
    with pytest.raises(ValueError, match="CEP, cidade e UF"):
        repo.save_plant(
            "1313",
            "PLANTA",
            "",
            "Sao Roque",
            "SP",
        )


def test_save_plant_rejeita_validacao_sem_cidade(
    plant_db,
):
    with pytest.raises(ValueError, match="CEP, cidade e UF"):
        repo.save_plant(
            "1313",
            "PLANTA",
            "18130000",
            "",
            "SP",
        )


def test_save_plant_rejeita_validacao_sem_uf(
    plant_db,
):
    with pytest.raises(ValueError, match="CEP, cidade e UF"):
        repo.save_plant(
            "1313",
            "PLANTA",
            "18130000",
            "Sao Roque",
            "",
        )


def test_save_plant_rejeita_observacoes_acima_de_1000_caracteres(
    plant_db,
):
    with pytest.raises(ValueError, match="1000 caracteres"):
        repo.save_plant(
            "1313",
            "PLANTA",
            "18130000",
            "Sao Roque",
            "SP",
            notes="x" * 1001,
        )


def test_save_plant_aceita_observacoes_com_1000_caracteres(
    plant_db,
):
    notes = "x" * 1000

    repo.save_plant(
        "1313",
        "PLANTA",
        "18130000",
        "Sao Roque",
        "SP",
        notes=notes,
    )

    assert repo.get_plant("1313")["notes"] == notes


# ============================================================
# SAVE_PLANT - INSERÇÃO E ATUALIZAÇÃO
# ============================================================

def test_save_plant_insere_planta(
    plant_db,
):
    resultado = repo.save_plant(
        "1313",
        "DNP SAO ROQUE",
        "18130000",
        "Sao Roque",
        "SP",
    )

    planta = repo.get_plant("1313")

    assert resultado == "1313"
    assert planta["name"] == "DNP SAO ROQUE"
    assert planta["zip_code"] == "18130-000"
    assert planta["city"] == "Sao Roque"
    assert planta["state"] == "SP"
    assert planta["active"] == 1
    assert planta["validation_status"] == repo.STATUS_VALIDATED
    assert planta["updated_at"] is not None


def test_save_plant_normaliza_nome_e_observacoes(
    plant_db,
):
    repo.save_plant(
        "1313",
        "  PLANTA TESTE  ",
        "18130000",
        " Sao Roque ",
        "SP",
        notes="  observacao  ",
    )

    planta = repo.get_plant("1313")

    assert planta["name"] == "PLANTA TESTE"
    assert planta["city"] == "Sao Roque"
    assert planta["notes"] == "observacao"


def test_save_plant_converte_active_para_inteiro(
    plant_db,
):
    repo.save_plant(
        "1313",
        "PLANTA",
        "18130000",
        "Sao Roque",
        "SP",
        active=False,
    )

    assert repo.get_plant("1313")["active"] == 0


def test_save_plant_atualiza_planta_existente(
    plant_db,
):
    repo.save_plant(
        "1313",
        "NOME ANTIGO",
        "18130000",
        "Sao Roque",
        "SP",
    )

    repo.save_plant(
        "1313",
        "NOME NOVO",
        "01001000",
        "Sao Paulo",
        "SP",
        active=False,
        validation_status=repo.STATUS_PENDING,
        notes="Atualizada",
    )

    planta = repo.get_plant("1313")

    assert planta["name"] == "NOME NOVO"
    assert planta["zip_code"] == "01001-000"
    assert planta["city"] == "Sao Paulo"
    assert planta["active"] == 0
    assert planta["validation_status"] == repo.STATUS_PENDING
    assert planta["notes"] == "Atualizada"


def test_save_plant_recusa_codigo_existente_quando_allow_update_false(
    plant_db,
    sample_plant,
):
    with pytest.raises(ValueError, match="Já existe"):
        repo.save_plant(
            "1313",
            "OUTRO NOME",
            "18130000",
            "Sao Roque",
            "SP",
            allow_update=False,
        )


def test_save_plant_insere_codigo_novo_com_allow_update_false(
    plant_db,
):
    resultado = repo.save_plant(
        "2424",
        "NOVA PLANTA",
        "18130000",
        "Sao Roque",
        "SP",
        allow_update=False,
    )

    assert resultado == "2424"
    assert repo.get_plant("2424") is not None


def test_save_plant_invalida_cache(
    plant_db,
    fake_clock,
):
    repo._rows_cached()

    assert repo._cache["rows"] is not None

    repo.save_plant(
        "1313",
        "PLANTA",
        "18130000",
        "Sao Roque",
        "SP",
    )

    assert repo._cache["rows"] is None
    assert repo._cache["at"] == 0.0


# ============================================================
# DELETE_PLANT
# ============================================================

def test_delete_plant_remove_planta_e_vinculos(
    plant_db,
    sample_plant,
):
    plant_db.execute(
        "INSERT INTO user_plants (user_id, plant_code) VALUES (?, ?)",
        (1, "1313"),
    )

    resultado = repo.delete_plant("1313")

    assert resultado is True
    assert repo.get_plant("1313") is None

    vinculos = plant_db.execute(
        "SELECT * FROM user_plants WHERE plant_code = ?",
        ("1313",),
    ).fetchall()

    assert vinculos == []


def test_delete_plant_retorna_false_quando_nao_existe(
    plant_db,
):
    assert repo.delete_plant("9999") is False


def test_delete_plant_normaliza_codigo(
    plant_db,
    sample_plant,
):
    assert repo.delete_plant(" 1313 ") is True


def test_delete_plant_invalida_cache(
    plant_db,
    sample_plant,
    fake_clock,
):
    repo._rows_cached()

    repo.delete_plant("1313")

    assert repo._cache["rows"] is None
    assert repo._cache["at"] == 0.0


# ============================================================
# TOGGLE_PLANT
# ============================================================

def test_toggle_plant_desativa_planta(
    plant_db,
    sample_plant,
):
    resultado = repo.toggle_plant("1313", False)

    assert resultado is True
    assert repo.get_plant("1313")["active"] == 0


def test_toggle_plant_ativa_planta(
    plant_db,
):
    repo.save_plant(
        "1313",
        "PLANTA",
        "18130000",
        "Sao Roque",
        "SP",
        active=False,
    )

    resultado = repo.toggle_plant("1313", True)

    assert resultado is True
    assert repo.get_plant("1313")["active"] == 1


def test_toggle_plant_retorna_false_quando_nao_existe(
    plant_db,
):
    assert repo.toggle_plant("9999", True) is False


def test_toggle_plant_normaliza_codigo(
    plant_db,
    sample_plant,
):
    assert repo.toggle_plant(" 1313 ", False) is True


def test_toggle_plant_invalida_cache(
    plant_db,
    sample_plant,
    fake_clock,
):
    repo._rows_cached()

    repo.toggle_plant("1313", False)

    assert repo._cache["rows"] is None
    assert repo._cache["at"] == 0.0



@pytest.mark.parametrize(
    ("zip_code", "city", "state"),
    [
        ("", "Sao Roque", "SP"),
        ("18130-000", "", "SP"),
        ("18130-000", "Sao Roque", ""),
    ],
)
def test_get_usable_plant_rejeita_campos_ausentes_com_status_validado(
    plant_db,
    zip_code,
    city,
    state,
):
    plant_db.execute(
        """
        INSERT INTO plants (
            code, name, zip_code, city, state,
            active, validation_status, notes, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "1313",
            "PLANTA INCOMPLETA",
            zip_code,
            city,
            state,
            1,
            repo.STATUS_VALIDATED,
            "",
            "2026-11-26T10:00:00",
        ),
    )

    repo._invalidate_cache()

    resultado = repo.get_usable_plant("1313")

    assert resultado is None
