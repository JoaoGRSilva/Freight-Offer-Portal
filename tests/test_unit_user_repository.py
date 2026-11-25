
import sqlite3

import pytest

from services import user_repository
from services.db import connect
from werkzeug.security import check_password_hash


@pytest.fixture
def user_database(isolated_databases):
    user_repository.initialize_users()
    return isolated_databases


def criar_admin():
    return user_repository.save_user(
        name="Administrador",
        email="admin@teste.com",
        password="senha-segura-123",
        profile="admin",
        carrier="",
        plants=[],
        active=True,
    )


def criar_operador():
    with connect("users") as conn:
        conn.execute(
            """
            INSERT INTO plants (code, name)
            VALUES (?, ?)
            """,
            ("SP01", "Planta São Paulo"),
        )

    return user_repository.save_user(
        name="Operador",
        email="operador@teste.com",
        password="senha-segura-123",
        profile="operator",
        carrier="",
        plants=["SP01"],
        active=True,
    )


def buscar_usuario(user_id):
    with connect("users") as conn:
        return conn.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()


# AUTENTICAÇÃO E CONSULTA


def test_authenticate_user_with_correct_credentials(user_database):
    user_id = criar_admin()

    user = user_repository.authenticate_user(
        " ADMIN@TESTE.COM ",
        "senha-segura-123",
    )

    assert user is not None
    assert user.id == user_id
    assert user.email == "admin@teste.com"
    assert user.is_admin is True


def test_authenticate_user_rejects_wrong_password(user_database):
    criar_admin()

    user = user_repository.authenticate_user(
        "admin@teste.com",
        "senha-incorreta",
    )

    assert user is None


def test_inactive_user_cannot_authenticate_or_be_loaded(user_database):
    user_id = criar_admin()

    with connect("users") as conn:
        conn.execute(
            "UPDATE users SET active = 0 WHERE id = ?",
            (user_id,),
        )

    assert user_repository.get_user(user_id) is None

    assert user_repository.authenticate_user(
        "admin@teste.com",
        "senha-segura-123",
    ) is None


# SEGURANÇA DOS ADMINISTRADORES


def test_system_rejects_deactivation_of_last_active_admin(user_database):
    admin_id = criar_admin()

    with pytest.raises(
        ValueError,
        match="Mantenha pelo menos um administrador ativo",
    ):
        user_repository.save_user(
            name="Administrador",
            email="admin@teste.com",
            password="",
            profile="admin",
            carrier="",
            plants=[],
            active=False,
            user_id=admin_id,
        )

    admin = buscar_usuario(admin_id)

    assert admin["active"] == 1
    assert admin["is_admin"] == 1
    assert admin["role"] == "internal"


def test_system_allows_deactivation_when_another_admin_exists(
    user_database,
):
    first_admin = criar_admin()

    second_admin = user_repository.save_user(
        name="Segundo administrador",
        email="admin2@teste.com",
        password="senha-segura-456",
        profile="admin",
        carrier="",
        plants=[],
        active=True,
    )

    user_repository.save_user(
        name="Administrador",
        email="admin@teste.com",
        password="",
        profile="admin",
        carrier="",
        plants=[],
        active=False,
        user_id=first_admin,
    )

    assert buscar_usuario(first_admin)["active"] == 0
    assert buscar_usuario(second_admin)["active"] == 1


# INTEGRIDADE DO CADASTRO


def test_operator_cannot_be_assigned_to_nonexistent_plant(user_database):
    with pytest.raises(
        ValueError,
        match="Selecione plantas válidas",
    ):
        user_repository.save_user(
            name="Operador",
            email="operador@teste.com",
            password="senha-segura-123",
            profile="operator",
            carrier="",
            plants=["PLANTA_INEXISTENTE"],
            active=True,
        )

    with connect("users") as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

    assert total == 0


def test_duplicate_email_is_rejected_even_with_different_case(
    user_database,
):
    criar_admin()

    with pytest.raises(
        ValueError,
        match="Já existe um usuário com este e-mail",
    ):
        user_repository.save_user(
            name="Outro administrador",
            email="ADMIN@TESTE.COM",
            password="outra-senha-segura",
            profile="admin",
            carrier="",
            plants=[],
            active=True,
        )

    with connect("users") as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0]

    assert total == 1


def test_failed_email_update_rolls_back_all_user_changes(user_database):
    admin_id = criar_admin()

    user_repository.save_user(
        name="Segundo administrador",
        email="admin2@teste.com",
        password="senha-segura-456",
        profile="admin",
        carrier="",
        plants=[],
        active=True,
    )

    original = buscar_usuario(admin_id)
    original_hash = original["password_hash"]

    with pytest.raises(
        ValueError,
        match="Já existe um usuário com este e-mail",
    ):
        user_repository.save_user(
            name="Nome que não deve ser salvo",
            email="admin2@teste.com",
            password="nova-senha-segura",
            profile="admin",
            carrier="",
            plants=[],
            active=False,
            user_id=admin_id,
        )

    updated = buscar_usuario(admin_id)

    assert updated["name"] == "Administrador"
    assert updated["email"] == "admin@teste.com"
    assert updated["active"] == 1
    assert updated["password_hash"] == original_hash


# ATUALIZAÇÃO DE USUÁRIO


def test_editing_user_without_new_password_preserves_old_password(
    user_database,
):
    user_id = criar_admin()
    original_hash = buscar_usuario(user_id)["password_hash"]

    user_repository.save_user(
        name="Administrador Atualizado",
        email="admin@teste.com",
        password="",
        profile="admin",
        carrier="",
        plants=[],
        active=True,
        user_id=user_id,
    )

    updated = buscar_usuario(user_id)

    assert updated["name"] == "Administrador Atualizado"
    assert updated["password_hash"] == original_hash
    assert check_password_hash(
        updated["password_hash"],
        "senha-segura-123",
    )


def test_editing_operator_updates_plant_associations(user_database):
    operator_id = criar_operador()

    with connect("users") as conn:
        conn.execute(
            """
            INSERT INTO plants (code, name)
            VALUES (?, ?)
            """,
            ("RJ01", "Planta Rio de Janeiro"),
        )

    user_repository.save_user(
        name="Operador",
        email="operador@teste.com",
        password="",
        profile="operator",
        carrier="",
        plants=["RJ01"],
        active=True,
        user_id=operator_id,
    )

    user = user_repository.get_user(operator_id)

    assert user.plants == ("RJ01",)
    assert user.can_access_plant("RJ01") is True
    assert user.can_access_plant("SP01") is False



# CONSULTAS E PERMISSÕES ADMINISTRATIVAS

def test_get_user_returns_none_for_nonexistent_user(user_database):
    assert user_repository.get_user(9999) is None


def test_authenticate_user_returns_none_for_unknown_email(user_database):
    assert user_repository.authenticate_user(
        "inexistente@teste.com",
        "senha-segura-123",
    ) is None


def test_set_user_admin_promotes_internal_user(user_database):
    user_id = criar_admin()

    assert user_repository.set_user_admin(
        "admin@teste.com",
        False,
    ) is True

    assert buscar_usuario(user_id)["is_admin"] == 0

    assert user_repository.set_user_admin(
        "admin@teste.com",
        True,
    ) is True

    assert buscar_usuario(user_id)["is_admin"] == 1


def test_set_user_admin_rejects_carrier_and_unknown_email(user_database):
    user_repository.create_user(
        name="Transportadora",
        email="carrier@teste.com",
        password="senha-segura-123",
        role="carrier",
        carrier_name="Transportadora Teste",
    )

    assert user_repository.set_user_admin(
        "carrier@teste.com",
    ) is False

    assert user_repository.set_user_admin(
        "inexistente@teste.com",
    ) is False


def test_list_users_returns_users_ordered_by_name(user_database):
    user_repository.save_user(
        name="Zuleica",
        email="zuleica@teste.com",
        password="senha-segura-123",
        profile="admin",
        carrier="",
        plants=[],
        active=True,
    )

    user_repository.save_user(
        name="Amanda",
        email="amanda@teste.com",
        password="senha-segura-123",
        profile="admin",
        carrier="",
        plants=[],
        active=True,
    )

    users = user_repository.list_users()

    assert [user.name for user in users] == ["Amanda", "Zuleica"]


def test_list_users_includes_operator_plant_associations(user_database):
    criar_operador()

    users = user_repository.list_users()

    operator = next(
        user for user in users
        if user.email == "operador@teste.com"
    )

    assert operator.plants == ("SP01",)
    assert operator.can_access_plant("SP01") is True


# CRIAÇÃO DIRETA DE USUÁRIOS

def test_create_user_saves_internal_user(user_database):
    user_id = user_repository.create_user(
        name="  Operador  ",
        email="  OPERADOR@TESTE.COM  ",
        password="senha-segura-123",
        role="internal",
    )

    user = user_repository.get_user(user_id)

    assert user is not None
    assert user.name == "Operador"
    assert user.email == "operador@teste.com"
    assert user.role == "internal"
    assert user.is_admin is False


def test_create_user_saves_carrier_with_company(user_database):
    user_id = user_repository.create_user(
        name="Transportadora",
        email="carrier@teste.com",
        password="senha-segura-123",
        role="carrier",
        carrier_name="Transportadora Teste",
    )

    user = user_repository.get_user(user_id)

    assert user is not None
    assert user.role == "carrier"
    assert user.carrier_name == "Transportadora Teste"
    assert user.can_access_plant("SP01") is False


@pytest.mark.parametrize("role", ["admin", "operator", "invalid", ""])
def test_create_user_rejects_invalid_role(user_database, role):
    with pytest.raises(ValueError, match="Perfil inválido"):
        user_repository.create_user(
            name="Usuário",
            email="usuario@teste.com",
            password="senha-segura-123",
            role=role,
        )


def test_create_user_rejects_carrier_without_company(user_database):
    with pytest.raises(
        ValueError,
        match="Informe a transportadora vinculada",
    ):
        user_repository.create_user(
            name="Transportadora",
            email="carrier@teste.com",
            password="senha-segura-123",
            role="carrier",
        )


def test_create_user_rejects_short_password(user_database):
    with pytest.raises(
        ValueError,
        match="A senha deve possuir pelo menos 12 caracteres",
    ):
        user_repository.create_user(
            name="Usuário",
            email="usuario@teste.com",
            password="curta",
            role="internal",
        )


# VALIDAÇÕES ADICIONAIS DE SAVE_USER

@pytest.mark.parametrize(
    "name,email,profile",
    [
        ("", "usuario@teste.com", "admin"),
        ("Usuário", "", "admin"),
        ("Usuário", "usuario@teste.com", "invalid"),
    ],
)
def test_save_user_rejects_invalid_basic_data(
    user_database,
    name,
    email,
    profile,
):
    with pytest.raises(
        ValueError,
        match="Informe nome, e-mail e perfil válidos",
    ):
        user_repository.save_user(
            name=name,
            email=email,
            password="senha-segura-123",
            profile=profile,
            carrier="",
            plants=[],
            active=True,
        )


def test_save_user_rejects_carrier_without_company(user_database):
    with pytest.raises(
        ValueError,
        match="Informe a transportadora",
    ):
        user_repository.save_user(
            name="Transportadora",
            email="carrier@teste.com",
            password="senha-segura-123",
            profile="carrier",
            carrier="",
            plants=[],
            active=True,
        )


def test_save_user_rejects_operator_without_plants(user_database):
    with pytest.raises(
        ValueError,
        match="Selecione plantas válidas",
    ):
        user_repository.save_user(
            name="Operador",
            email="operador@teste.com",
            password="senha-segura-123",
            profile="operator",
            carrier="",
            plants=[],
            active=True,
        )


def test_save_user_rejects_short_password(user_database):
    with pytest.raises(
        ValueError,
        match="Senha deve ter pelo menos 12 caracteres",
    ):
        user_repository.save_user(
            name="Administrador",
            email="admin@teste.com",
            password="curta",
            profile="admin",
            carrier="",
            plants=[],
            active=True,
        )


def test_save_user_rejects_nonexistent_user_update(user_database):
    with pytest.raises(
        ValueError,
        match="Usuário não encontrado",
    ):
        user_repository.save_user(
            name="Administrador",
            email="admin@teste.com",
            password="",
            profile="admin",
            carrier="",
            plants=[],
            active=True,
            user_id=9999,
        )



def test_user_is_active_reflects_database_status(user_database):
    user_id = criar_admin()

    active_user = user_repository.get_user(user_id)
    assert active_user.is_active is True

    with connect("users") as conn:
        conn.execute(
            "UPDATE users SET active = 0 WHERE id = ?",
            (user_id,),
        )

    inactive_user = next(
        user for user in user_repository.list_users()
        if user.id == user_id
    )

    assert inactive_user.is_active is False



def test_editing_user_with_new_password_updates_credentials(user_database):
    user_id = criar_admin()

    user_repository.save_user(
        name="Administrador",
        email="admin@teste.com",
        password="nova-senha-segura-456",
        profile="admin",
        carrier="",
        plants=[],
        active=True,
        user_id=user_id,
    )

    assert user_repository.authenticate_user(
        "admin@teste.com",
        "senha-segura-123",
    ) is None

    user = user_repository.authenticate_user(
        "admin@teste.com",
        "nova-senha-segura-456",
    )

    assert user is not None
    assert user.id == user_id
