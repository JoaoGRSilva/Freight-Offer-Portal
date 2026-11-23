"""Recomendação de tipo de caminhão pelo peso da carga."""

VEICULOS = {
    2: {
        "tipo": "Toco",
        "capacidade_kg": 7_500,
    },
    3: {
        "tipo": "Truck",
        "capacidade_kg": 15_000,
    },
    4: {
        "tipo": "Bi-truck",
        "capacidade_kg": 19_500,
    },
    5: {
        "tipo": "Carreta Sider",
        "capacidade_kg": 25_000,
    },
    6: {
        "tipo": "Carreta",
        "capacidade_kg": 38_000,
    },
    7: {
        "tipo": "Bi-trem",
        "capacidade_kg": 48_000,
    },
    9: {
        "tipo": "Rodo-trem",
        "capacidade_kg": 57_000,
    },
}

preco_gasolina_max = {
    "AC": 7.99,
    "AL": 7.96,
    "AM": 7.29,
    "BA": 8.89,
    "CE": 7.89,
    "DF": 7.32,
    "ES": 7.39,
    "GO": 7.95,
    "MA": 8.39,
    "MT": 7.89,
    "MS": 7.58,
    "MG": 7.49,
    "PA": 8.75,
    "PB": 7.80,
    "PR": 7.89,
    "PE": 8.19,
    "PI": 7.98,
    "RJ": 7.89,
    "RN": 8.29,
    "RS": 8.09,
    "RO": 7.88,
    "RR": 7.20,
    "SC": 7.44,
    "SP": 8.69,
    "SE": 8.35,
    "TO": 7.49,
}

antt = {
    2 : {'ccd':2.98, 'cc': 250.78},
    3 : {'ccd':3.84, 'cc': 297.19},
    4 : {'ccd':4.38, 'cc': 306.52},
    5 : {'ccd':5.03, 'cc': 340.76},
    6 : {'ccd':5.75, 'cc': 381.28},
    7 : {'ccd':6.21, 'cc': 442.42},
    9 : {'ccd':7.14, 'cc': 482.47},
}

consumo_tabela = {
    ('baixo', 2, 'r'): 4.5,
    ('baixo', 2, 'c'): 4.0,
    ('baixo', 3, 'r'): 5.0,
    ('baixo', 3, 'c'): 4.0,
    ('baixo', 4, 'r'): 3.2,
    ('baixo', 4, 'c'): 2.7,
    ('baixo', 5, 'r'): 2.2,
    ('baixo', 5, 'c'): 1.7,
    ('baixo', 6, 'r'): 2.0,
    ('baixo', 6, 'c'): 1.9,
    ('baixo', 7, 'r'): 1.9,
    ('baixo', 7, 'c'): 1.9,
    ('baixo', 9, 'r'): 1.8,
    ('baixo', 9, 'c'): 1.8,

    ('medio', 2, 'r'): 3.5,
    ('medio', 2, 'c'): 3.0,
    ('medio', 3, 'r'): 3.3,
    ('medio', 3, 'c'): 2.8,
    ('medio', 4, 'r'): 3.2,
    ('medio', 4, 'c'): 2.1,
    ('medio', 5, 'r'): 2.0,
    ('medio', 5, 'c'): 1.5,
    ('medio', 6, 'r'): 2.0,
    ('medio', 6, 'c'): 1.6,
    ('medio', 7, 'r'): 1.9,
    ('medio', 7, 'c'): 1.6,
    ('medio', 9, 'r'): 1.8,
    ('medio', 9, 'c'): 1.6,

    ('alto', 2, 'r'): 2.5,
    ('alto', 2, 'c'): 2.0,
    ('alto', 3, 'r'): 2.2,
    ('alto', 3, 'c'): 1.5,
    ('alto', 4, 'r'): 3.2,
    ('alto', 4, 'c'): 1.5,
    ('alto', 5, 'r'): 1.7,
    ('alto', 5, 'c'): 1.9,
    ('alto', 6, 'r'): 1.9,
    ('alto', 6, 'c'): 1.2,
    ('alto', 7, 'r'): 1.9,
    ('alto', 7, 'c'): 1.2,
    ('alto', 9, 'r'): 1.8,
    ('alto', 9, 'c'): 1.3,
}



def recomendar_caminhao(peso_kg: float) -> dict:

    peso = float(peso_kg)

    for eixos, dados in VEICULOS.items():

        if peso <= dados["capacidade_kg"]:

            return {
                "eixos": eixos,
                "tipo": dados["tipo"],
                "capacidade_kg": dados["capacidade_kg"],
                "excede": False,
            }

    return {
        "eixos": None,
        "tipo": None,
        "capacidade_kg": max(
            veiculo["capacidade_kg"]
            for veiculo in VEICULOS.values()
        ),
        "excede": True,
    }