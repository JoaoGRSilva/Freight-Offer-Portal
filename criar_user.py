
from getpass import getpass

from services.user_repository import initialize_users, create_user


def main():
    print("=" * 45)
    print("       CRIAÇÃO DE USUÁRIO - PORTAL")
    print("=" * 45)

    initialize_users()

    nome = input("Nome: ").strip()
    email = input("E-mail: ").strip()

    print("\nTipo de usuário:")
    print("1 - Interno")
    print("2 - Transportadora")

    tipo = input("Escolha (1/2): ").strip()

    if tipo == "1":
        role = "internal"
        carrier_name = None

    elif tipo == "2":
        role = "carrier"
        carrier_name = input("Nome da transportadora: ").strip()

    else:
        print("\nOpção inválida.")
        return

    senha = getpass("Senha: ")
    confirmar_senha = getpass("Confirmar senha: ")

    if senha != confirmar_senha:
        print("\nAs senhas não coincidem.")
        return

    try:
        usuario = create_user(
            name=nome,
            email=email,
            password=senha,
            role=role,
            carrier_name=carrier_name
        )

        print("\n" + "=" * 45)
        print("USUÁRIO CRIADO COM SUCESSO!")
        print("=" * 45)
        print(f"Nome: {nome}")
        print(f"E-mail: {email}")
        print(f"Perfil: {role}")
        if carrier_name:
            print(f"Transportadora: {carrier_name}")

    except Exception as e:
        print(f"\nErro ao criar usuário: {e}")


if __name__ == "__main__":
    main()
