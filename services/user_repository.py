
import sqlite3
from services.db import connect

from flask_login import UserMixin
from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)



class User(UserMixin):

    def __init__(self, row, plants=()):
        self.id = row["id"]
        self.name = row["name"]
        self.email = row["email"]
        self.role = row["role"]
        self.carrier_name = row["carrier_name"]
        self.active = bool(row["active"])
        self.is_admin = self.role == "internal" and bool(row["is_admin"])
        self.plants = tuple(plants)

    def can_access_plant(self, code):
        return self.role == "internal" and (self.is_admin or str(code) in self.plants)

    @property
    def is_active(self):
        return self.active


def initialize_users():
    with connect("users") as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,

                role TEXT NOT NULL
                    CHECK(role IN ('internal', 'carrier')),

                carrier_name TEXT,

                active INTEGER NOT NULL DEFAULT 1,

                created_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS plants (
                code TEXT PRIMARY KEY,

                name TEXT NOT NULL,

                zip_code TEXT,
                city TEXT,
                state TEXT,

                active INTEGER NOT NULL DEFAULT 1,

                validation_status TEXT
                    DEFAULT 'VALIDADO',

                notes TEXT,

                created_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,

                updated_at TEXT
            );
        """)

        if "is_admin" not in {r["name"] for r in conn.execute("PRAGMA table_info(users)")}:
            conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0 CHECK(is_admin IN (0,1))")
        conn.execute("""CREATE TABLE IF NOT EXISTS user_plants (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            plant_code TEXT NOT NULL, PRIMARY KEY(user_id, plant_code))""")


def _user(conn, row):
    if not row:
        return None
    plants = [r[0] for r in conn.execute("SELECT plant_code FROM user_plants WHERE user_id=?", (row["id"],))]
    return User(row, plants)


def set_user_admin(email, is_admin=True):
    with connect("users") as conn:
        return conn.execute("UPDATE users SET is_admin=? WHERE email=? AND role='internal'", (int(is_admin), email)).rowcount == 1


def list_users():
    with connect("users") as conn:
        return [_user(conn, r) for r in conn.execute("SELECT * FROM users ORDER BY name")]


def save_user(name, email, password, profile, carrier, plants, active, user_id=None):
    name = (name or "").strip()
    email = (email or "").strip().lower()
    carrier = (carrier or "").strip()
    password = password or ""

    if not name or not email or profile not in ("admin", "operator", "carrier"):
        raise ValueError("Informe nome, e-mail e perfil válidos.")
    if profile == "carrier" and not carrier:
        raise ValueError("Informe a transportadora.")

    plants = {str(p).strip() for p in plants} if profile == "operator" else set()
    if profile == "operator" and not plants:
        raise ValueError("Selecione plantas válidas para o operador.")

    if (password or user_id is None) and len(password) < 12:
        raise ValueError("Senha deve ter pelo menos 12 caracteres.")

    role = "carrier" if profile == "carrier" else "internal"
    admin = int(profile == "admin")
    carrier_value = carrier if role == "carrier" else None

    try:
        with connect("users") as conn:
            conn.execute("BEGIN IMMEDIATE")

            # As plantas válidas vêm do cadastro (Administração > Plantas).
            if plants:
                cadastradas = {r[0] for r in conn.execute("SELECT code FROM plants")}
                if not plants.issubset(cadastradas):
                    raise ValueError("Selecione plantas válidas para o operador.")

            if user_id is not None:
                old = conn.execute(
                    "SELECT * FROM users WHERE id=?", (user_id,)
                ).fetchone()
                if not old:
                    raise ValueError("Usuário não encontrado.")

                if old["is_admin"] and old["active"] and not (admin and active):
                    total = conn.execute(
                        "SELECT COUNT(*) FROM users "
                        "WHERE role='internal' AND is_admin=1 AND active=1"
                    ).fetchone()[0]
                    if total <= 1:
                        raise ValueError("Mantenha pelo menos um administrador ativo.")

                conn.execute(
                    "UPDATE users SET name=?, email=?, role=?, carrier_name=?, "
                    "is_admin=?, active=? WHERE id=?",
                    (name, email, role, carrier_value, admin, int(active), user_id),
                )
                if password:
                    conn.execute(
                        "UPDATE users SET password_hash=? WHERE id=?",
                        (generate_password_hash(password), user_id),
                    )
            else:
                user_id = conn.execute(
                    "INSERT INTO users "
                    "(name, email, password_hash, role, carrier_name, is_admin, active) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (name, email, generate_password_hash(password),
                     role, carrier_value, admin, int(active)),
                ).lastrowid

            conn.execute("DELETE FROM user_plants WHERE user_id=?", (user_id,))
            conn.executemany(
                "INSERT INTO user_plants (user_id, plant_code) VALUES (?, ?)",
                [(user_id, p) for p in plants],
            )
            return user_id

    except sqlite3.IntegrityError:
        raise ValueError("Já existe um usuário com este e-mail.") from None


def create_user(
    name,
    email,
    password,
    role,
    carrier_name=None,
):
    if role not in ("internal", "carrier"):
        raise ValueError("Perfil inválido.")

    if role == "carrier" and not carrier_name:
        raise ValueError(
            "Informe a transportadora vinculada."
        )

    if len(password) < 12:
        raise ValueError(
            "A senha deve possuir pelo menos 12 caracteres."
        )

    with connect("users") as conn:
        cursor = conn.execute("""
            INSERT INTO users (
                name,
                email,
                password_hash,
                role,
                carrier_name
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            name.strip(),
            email.strip().lower(),
            generate_password_hash(password),
            role,
            carrier_name,
        ))

        return cursor.lastrowid


def get_user(user_id):
    with connect("users") as conn:
        row = conn.execute("""
            SELECT *
            FROM users
            WHERE id = ?
              AND active = 1
        """, (user_id,)).fetchone()

        return _user(conn, row)


def authenticate_user(email, password):
    with connect("users") as conn:
        row = conn.execute("""
            SELECT *
            FROM users
            WHERE email = ?
              AND active = 1
        """, (
            email.strip().lower(),
        )).fetchone()

    if not row:
        return None

    if not check_password_hash(
        row["password_hash"],
        password,
    ):
        return None

    return get_user(row["id"])
