"""Utilitários de serialização JSON (salvar em services/json_utils.py)."""

import math
from datetime import date, datetime
from decimal import Decimal

import numpy as np
import pandas as pd


def json_safe(o):
    """
    Converte NaN, numpy, Timestamp, Decimal e NA para tipos que o tojson aceita.

    Sem isso, um NaN vira "NaN" no JSON (inválido) e o JSON.parse do
    navegador falha, deixando a página inteira vazia.
    """
    if isinstance(o, dict):
        return {k: json_safe(v) for k, v in o.items()}

    if isinstance(o, (list, tuple, set)):
        return [json_safe(v) for v in o]

    if o is None or o is pd.NA or o is pd.NaT:
        return None

    if isinstance(o, (bool, np.bool_)):
        return bool(o)

    if isinstance(o, np.integer):
        return int(o)

    if isinstance(o, (np.floating, float, Decimal)):
        o = float(o)
        return None if math.isnan(o) or math.isinf(o) else o

    if isinstance(o, pd.Timestamp):
        return o.strftime("%Y-%m-%d")

    if isinstance(o, (datetime, date)):
        return o.isoformat()

    return o