"""Recommendation engine parameters. Tune them here, without touching the logic."""
from pathlib import Path

# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
PARQUET_PATH = BASE_DIR / "data" / "processed" / "baseEA.parquet"
DB_PATH = BASE_DIR / "data"

DATABASES = {
    "fretes": DB_PATH / "fretes.db",
    "users": DB_PATH / "users.db",
    "settings": DB_PATH / "settings.db"
}


# ============================================================
# HISTORY: SAMPLE AND PERIOD
# ============================================================

HISTORY_MONTHS = 12

# Minimum trips required for a carrier to be eligible
MIN_CARRIER_TRIPS = 3

# Minimum trips required in a geographic scope
# Reserved for scope-level validation
MIN_LEVEL_TRIPS = 3

# Geographic search: ZIP5 -> ZIP4 -> ZIP3 -> State
ZIP_LEVELS = (5, 4, 3)

# Enable state-level fallback
ENABLE_STATE_FALLBACK = True

# In-memory history cache: 15 minutes
HISTORY_TTL_SEC = 15 * 60


# ============================================================
# CONFIDENCE
# ============================================================

SLA_HIGH = 0.80
TRIPS_HIGH = 10

SLA_MEDIUM = 0.65

# Ranking weights (reserved for future cost-based ranking)
SLA_WEIGHT = 0.60
COST_WEIGHT = 0.40


# ============================================================
# SLA RANKING
# ============================================================

SLA_SMOOTHING = 10
HALF_LIFE_DAYS = 180
MISSING_WEIGHT_FACTOR = 0.5
TIE_THRESHOLD = 0.02

# ============================================================
# RANKING BEHAVIOR
# ============================================================

# Ranking currently prioritizes adjusted SLA and trip count
RANKING_METHOD = "sla"

# Cost is informational and does not affect carrier ranking
USE_COST_IN_RANKING = False

# Historical economic reference is available only for ZIP5
ECONOMIC_REFERENCE_ZIP_LEVEL = 5

# Maximum number of similar routes displayed
MAX_SIMILAR_ROUTES = 4


# ============================================================
# ECONOMIC REFERENCE
# ============================================================

WEIGHT_BAND_MIN = 0.6
WEIGHT_BAND_MAX = 1.6
MIN_REFERENCE_TRIPS = 3

# Trips with BRL/100 kg below this are treated as invalid values
# (e.g. a BRL 0.01 placeholder) and ignored in the reference.
MIN_BRL_PER_100KG = 10


# ============================================================
# ALERTS
# ============================================================

# Historical estimate / ANTT outside this band raises a warning.
RATIO_ALERT_MAX = 2.5
RATIO_ALERT_MIN = 0.4

# Freight weight / typical route weight outside this band raises a warning.
WEIGHT_RATIO_ALERT_MAX = 1.25
WEIGHT_RATIO_ALERT_MIN = 0.8

# A carrier with this share of the route's trips raises a warning.
CONCENTRATION_ALERT = 0.9


# ============================================================
# OUTPUT AND DATA COLUMNS
# ============================================================

MAX_ALTERNATIVES = 5
CARRIER_ALIASES = {}   # {"raw name": "canonical name"}

CARRIER_COL = "service_agent_description"
DEST_STATE_COL = "uf_destino"

# Manual choice: corporate carriers only
# VBR6 = Domestic Vendor - corporate (included) | VBR7 = individual (ignored)
GROUP_COL = "service_agent_group"
CORPORATE_GROUP = "VBR6"

# ============================================================
# MANUAL CARRIER SELECTION
# ============================================================

# Show corporate carriers regardless of historical period
MANUAL_SELECTION_ALL_HISTORY = True

# Do not require a minimum number of trips for manual selection
MANUAL_SELECTION_MIN_TRIPS = 0

# Ignore individual carriers (VBR7)
MANUAL_SELECTION_CORPORATE_ONLY = True


# ============================================================
# CATEGORIES
# ============================================================

DEFAULT_CATEGORY = "medio"
DEFAULT_PAVEMENT = "r"


# ============================================================
# PLANTS
# code -> (name, zip code, city, state)
# ============================================================

PLANTS = {
    # OK: no discrepancies, or present in only one dataset
    "1210": ("DSM DNP Jaguare", "05323-020", "Jaguare", "SP"),
    "1211": ("DSM DNP Parana", "87065-170", "Maringa", "PR"), 
    "1248": ("DSM DNP Campinas", "13053-050", "Campinas", "SP"),
    "1301": ("DNP MAIRINQUE", "18120-000", "Mairinque", "SP"),
    "1312": ("MAIRINQUE - GRANJA", "18120-000", "Mairinque", "SP"),
    "1313": ("DNP SÃO ROQUE", "18132-680", "São Roque", "SP"),
    "1314": ("DNP JK", "04538-133", "São Paulo", "SP"),
    "1315": ("DNP BRASIL VINHEDO", "13280-000", "Vinhedo", "SP"),
    "1325": ("DNP VILA OLIMPIA", "04543-907", "São Paulo", "SP"),
    "1326": ("DNP TECHNO PARK", "13069-380", "Campinas", "SP"),
    "1327": ("DNP BROTAS", "17380-000", "Brotas", "SP"),
    "1304": ("DNP CAMPO GRANDE", "79018-800", "Campo Grande", "MS"),
    "1306": ("DNP CUIABA", "78098-282", "Cuiaba", "MT"),
    "1307": ("DNP GOIANIA", "74465-140", "Goiania", "GO"),
    "1308": ("DNP MARABA", "68507-765", "Marabá", "PA"),
    "1309": ("DNP VILHENA", "76980-753", "Vilhena", "RO"),
    "1310": ("DNP SÃO VICENTE", "11346-300", "São Vicente", "SP"),
    "1351": ("DNP LDC MAIRINQUE", "18120-000", "Mairinque", "SP"),
    "1352": ("DNP HORTOLANDIA", "13186-549", "Hortolândia", "SP"),

    # NOK: discrepancies between datasets; validate before use
    "1302": {
        "base1": ("DNP PECEM", "62670-000", "Pecem", None),
        "base2": ("DNP PECEM", "62670-000", "São Gonçalo do Amarante", None),
        "status": "VALIDAR_LOCALIDADE",
    },
    "1303": {
        "base1": ("DNP CACHOEIRINHA", "4622-4746", "Cachoeirinha", None),
        "base2": ("DNP CARAZINHO", "99500-000", "Carazinho", None),
        "status": "CONFLITO_TOTAL",
    },
    "1305": {
        "base1": ("DNP CHAPECO", "89810-460", "Chapeco", None),
        "base2": ("DNP XANXERE", "89820-000", "Xanxerê", None),
        "status": "CONFLITO_CIDADE_CEP",
    },
    "1311": {
        "base1": ("DNP PRATA", "38140-000", "Prata", None),
        "base2": ("DNP SETE LAGOAS", "35703-135", "Sete Lagoas", None),
        "status": "CONFLITO_TOTAL",
    },
    "1350": {
        "base1": ("DNP LDC Rondonopolis", None, None, None),
        "base2": ("DNP BARRA DO GARÇAS", "78605-772", "Barra do Garças", None),
        "status": "CONFLITO_TOTAL",
    },
}
