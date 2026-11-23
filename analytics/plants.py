"""Plantas (origens) e seus CEPs.

Os dados vêm do cadastro dinâmico (services/plant_repository.py), editável
em Administração > Plantas. Não é mais preciso alterar o código Python
quando uma planta muda.
"""

import re

from services.plant_repository import get_usable_plant, known_codes

_CODIGO_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")


def extrair_codigo(valor) -> str | None:
    """Aceita 1313, '1313', 'fretes_1313.xlsx' ou '1313-DNP SÃO ROQUE'.

    Devolve o primeiro número de 4 dígitos que seja um código cadastrado
    (em qualquer status); ignora outros números, como anos em nomes de arquivo.
    """
    cadastradas = known_codes()
    for m in _CODIGO_RE.finditer(str(valor)):
        if m.group(1) in cadastradas:
            return m.group(1)
    return None


def get_planta(valor) -> dict | None:
    """Devolve a planta, ou None se não existir, estiver inativa, pendente de
    validação ou com cadastro incompleto (sem CEP, cidade ou UF)."""
    codigo = extrair_codigo(valor)
    if not codigo:
        return None
    return get_usable_plant(codigo)
