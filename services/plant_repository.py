"""Cadastro de plantas (tabela `plants` em data/users.db).

Fonte única das plantas do portal. O dicionário `PLANTS` de analytics/config.py
só é usado para popular o banco na primeira execução (seed) e como fallback
caso a tabela ainda não exista (ex.: scripts de teste).
"""
import re
import sqlite3
import time
from datetime import datetime

from services.db import connect


STATUS_VALIDATED = "VALIDADO"
STATUS_PENDING = "PENDENTE"
VALID_STATUSES = (STATUS_VALIDATED, STATUS_PENDING)
VALIDATION_VALIDATED = STATUS_VALIDATED  # compatibilidade com o nome antigo

UFS = (
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC",
    "SP", "SE", "TO",
)

_CACHE_TTL_SEC = 30
_cache = {"at": 0.0, "rows": None}


def _now() -> str:
    """Timestamp único (ISO, horário local) usado em todas as escritas."""
    return datetime.now().isoformat(timespec="seconds")


def format_zip(value) -> str:
    """Devolve o CEP no formato 00000-000 ('' se vazio). Levanta ValueError se inválido."""
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return ""
    if len(digits) != 8:
        raise ValueError("CEP deve ter 8 dígitos.")
    return f"{digits[:5]}-{digits[5:]}"


def _invalidate_cache() -> None:
    _cache["at"] = 0.0
    _cache["rows"] = None


# ---------------------------------------------------------------------------
# Seed a partir de analytics/config.py
# ---------------------------------------------------------------------------
def _describe(base) -> str:
    name, zip_code, city, _state = base
    return f"{name} · CEP {zip_code or '—'} · {city or '—'}"


def _config_rows() -> list[dict]:
    """Converte o PLANTS de analytics/config.py em linhas da tabela `plants`."""
    from analytics.config import PLANTS

    rows = []
    for code, entry in PLANTS.items():
        if isinstance(entry, tuple):
            name, zip_code, city, state = entry
            rows.append({
                "code": str(code), "name": name, "zip_code": zip_code,
                "city": city, "state": state, "active": 1,
                "validation_status": STATUS_VALIDATED,
                "notes": "Importada de analytics/config.py.",
            })
        else:
            base1, base2 = entry["base1"], entry["base2"]
            rows.append({
                "code": str(code), "name": base1[0], "zip_code": None,
                "city": None, "state": None, "active": 1,
                "validation_status": STATUS_PENDING,
                "notes": (
                    f"Divergência entre bases ({entry['status']}). "
                    f"Base 1: {_describe(base1)}. Base 2: {_describe(base2)}. "
                    "Confirme CEP, cidade e UF corretos e marque como validada."
                ),
            })
    return rows


def seed_plants_from_config() -> int:
    """Popula `plants` a partir do config, apenas se a tabela estiver vazia.

    Retorna quantas plantas foram inseridas. É seguro chamar a cada start.
    """
    with connect("users") as conn:
        if conn.execute("SELECT COUNT(*) FROM plants").fetchone()[0]:
            return 0
        now = _now()
        rows = _config_rows()
        conn.executemany(
            """
            INSERT OR IGNORE INTO plants
                (code, name, zip_code, city, state, active,
                 validation_status, notes, updated_at)
            VALUES (:code, :name, :zip_code, :city, :state, :active,
                    :validation_status, :notes, :now)
            """,
            [{**r, "now": now} for r in rows],
        )
    _invalidate_cache()
    return len(rows)


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------
def list_plants(only_active: bool = False) -> list[dict]:
    query = "SELECT * FROM plants"
    if only_active:
        query += " WHERE active = 1"
    query += " ORDER BY code"

    with connect("users") as conn:
        return [dict(r) for r in conn.execute(query)]


def get_plant(code) -> dict | None:
    with connect("users") as conn:
        row = conn.execute(
            "SELECT * FROM plants WHERE code = ?",
            (str(code).strip(),),
        ).fetchone()

    return dict(row) if row else None


def _rows_cached() -> dict[str, dict]:
    """Todas as plantas indexadas por código, com cache curto.

    O cache evita uma consulta por linha ao processar arquivos grandes.
    As escritas deste módulo invalidam o cache; outros processos o veem
    em no máximo _CACHE_TTL_SEC segundos.
    """
    now = time.monotonic()
    if _cache["rows"] is not None and now - _cache["at"] < _CACHE_TTL_SEC:
        return _cache["rows"]

    try:
        with connect("users") as conn:
            rows = [dict(r) for r in conn.execute("SELECT * FROM plants")]
    except sqlite3.OperationalError:  # tabela ainda não criada
        rows = []

    if not rows:  # banco vazio: usa o config como fallback (não grava)
        rows = _config_rows()

    _cache["rows"] = {r["code"]: r for r in rows}
    _cache["at"] = now
    return _cache["rows"]


def known_codes() -> set[str]:
    """Códigos cadastrados, em qualquer status."""
    return set(_rows_cached())


def get_usable_plant(code) -> dict | None:
    """Planta apta para cálculo: ativa, validada e com CEP/cidade/UF completos.

    Formato igual ao antigo analytics.plants.get_planta().
    """
    row = _rows_cached().get(str(code).strip())
    if not row:
        return None
    if not row["active"] or row["validation_status"] != STATUS_VALIDATED:
        return None
    if not all((row["zip_code"], row["city"], row["state"])):
        return None
    return {
        "codigo": row["code"],
        "nome": row["name"],
        "cep": row["zip_code"],
        "cidade": row["city"],
        "uf": row["state"],
    }


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------
def save_plant(
    code,
    name,
    zip_code,
    city,
    state,
    active: bool = True,
    validation_status: str = STATUS_VALIDATED,
    notes: str = "",
    allow_update: bool = True,
) -> str:
    """Insere ou atualiza uma planta (upsert) e retorna o código.

    Com allow_update=False, recusa um código que já exista (usado no "novo").
    """
    code = str(code or "").strip()
    if not re.fullmatch(r"\d{4}", code):
        raise ValueError("Código da planta deve ter 4 dígitos (ex.: 1313).")

    name = (name or "").strip()
    if not name:
        raise ValueError("Nome da planta é obrigatório.")

    zip_code = format_zip(zip_code)
    city = (city or "").strip()

    state = (state or "").strip().upper()
    if state and state not in UFS:
        raise ValueError("UF inválida.")

    validation_status = (validation_status or "").strip().upper()
    if validation_status not in VALID_STATUSES:
        raise ValueError("Status de validação inválido.")
    if validation_status == STATUS_VALIDATED and not (zip_code and city and state):
        raise ValueError(
            "Para marcar a planta como validada, informe CEP, cidade e UF."
        )

    notes = (notes or "").strip()
    if len(notes) > 1000:
        raise ValueError("Observações excedem 1000 caracteres.")

    with connect("users") as conn:
        if not allow_update and conn.execute(
            "SELECT 1 FROM plants WHERE code = ?", (code,)
        ).fetchone():
            raise ValueError("Já existe uma planta com este código.")

        conn.execute(
            """
            INSERT INTO plants (
                code, name, zip_code, city, state,
                active, validation_status, notes, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                name              = excluded.name,
                zip_code          = excluded.zip_code,
                city              = excluded.city,
                state             = excluded.state,
                active            = excluded.active,
                validation_status = excluded.validation_status,
                notes             = excluded.notes,
                updated_at        = excluded.updated_at
            """,
            (code, name, zip_code, city, state, int(bool(active)),
             validation_status, notes, _now()),
        )

    _invalidate_cache()
    return code


def delete_plant(code) -> bool:
    """Remove a planta e seus vínculos com operadores (preferir inativar)."""
    code = str(code).strip()
    with connect("users") as conn:
        conn.execute("DELETE FROM user_plants WHERE plant_code = ?", (code,))
        cur = conn.execute("DELETE FROM plants WHERE code = ?", (code,))
        deleted = cur.rowcount > 0

    _invalidate_cache()
    return deleted


def toggle_plant(code, active: bool) -> bool:
    """Ativa/desativa a planta. Retorna True se a planta existia."""
    with connect("users") as conn:
        cur = conn.execute(
            """
            UPDATE plants
               SET active = ?,
                   updated_at = ?
             WHERE code = ?
            """,
            (int(bool(active)), _now(), str(code).strip()),
        )
        changed = cur.rowcount > 0

    _invalidate_cache()
    return changed
