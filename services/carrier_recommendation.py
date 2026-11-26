"""
Carrier recommendation engine.

Two datasets, two granularities (do not mix):

    TRIPS  (1 row per freight_id)
        -> RANKING: SLA, trip count, cargo weight, recency.

    ROWS   (1 row per original parquet record)
        -> AMOUNT PAID: average = sum of amounts / number of rows.

Flow:

 1. Receive a new freight.
 2. Load the trip history and the row history.
 3. Filter by the history period.
 4. Look for trips from the same plant: ZIP5 -> ZIP4 -> ZIP3 -> state.
 5. Pick the first scope that has a carrier with the minimum sample
    and a known SLA (no fallback by plant or overall history).
 6. Rank by smoothed SLA, weighted by cargo weight and recency;
    break ties by trip count.
 7. Return the recommendation, alternatives and a technical-tie warning.

Amount paid (economic reference):

 - Does NOT enter the ranking.
 - Only shown for ZIP5.
 - Selects TRIPS: same plant, same ZIP5, carrier (or all carriers,
   as a fallback) and weight within the order's weight band.
 - Then takes the rows of those trips and computes:

        BRL per 100 kg = sum(amount) / sum(weight) * 100
        BRL per kg     = BRL per 100 kg / 100
        estimate       = BRL per 100 kg * new freight weight / 100

 - It is a ratio of sums (each kg weighs the same), not a mean of ratios.
 - Rows without amount or weight are left out (missing data).
 - Per-order apportioning is proportional to weight (median CV ~0.7%),
   so the result is the same per row, per order or per whole freight.

Manual choice:

 - The "outras_transportadoras" list holds ALL corporate carriers
   (service_agent_group = VBR6), with no minimum trips and no period
   filter. VBR7 (individuals) is ignored.

Compatibility:

    The old Portuguese names (recomendar, classificar_confianca,
    recarregar_historico, cep_para_uf) are kept at the bottom of this
    file as deprecated aliases. Remove them once all callers use the
    new names.
"""

import logging
import time

import numpy as np
import pandas as pd

from analytics import config as C
from analytics.truck import recomendar_caminhao
from services.postal_code import validar_cep, distancia_km
from services.freight_cost import calcular_custos
from analytics.history import (
    obter_historico_consolidado,
    obter_historico_detalhado,
)


log = logging.getLogger(__name__)


# ============================================================
# SETTINGS — CENTRALIZED CONFIGURATION
# ============================================================

# History
MIN_CARRIER_TRIPS = C.MIN_CARRIER_TRIPS
HISTORY_MONTHS = C.HISTORY_MONTHS
ZIP_LEVELS = C.ZIP_LEVELS
HISTORY_TTL_SEC = C.HISTORY_TTL_SEC

# SLA ranking
SLA_SMOOTHING = C.SLA_SMOOTHING
HALF_LIFE_DAYS = C.HALF_LIFE_DAYS
MISSING_WEIGHT_FACTOR = C.MISSING_WEIGHT_FACTOR
TIE_THRESHOLD = C.TIE_THRESHOLD

# Confidence
SLA_HIGH = C.SLA_HIGH
SLA_MEDIUM = C.SLA_MEDIUM
TRIPS_HIGH = C.TRIPS_HIGH

# Economic reference
WEIGHT_BAND_MIN = C.WEIGHT_BAND_MIN
WEIGHT_BAND_MAX = C.WEIGHT_BAND_MAX
MIN_REFERENCE_TRIPS = C.MIN_REFERENCE_TRIPS
MIN_BRL_PER_100KG = C.MIN_BRL_PER_100KG

# Alerts
RATIO_ALERT_MAX = C.RATIO_ALERT_MAX
RATIO_ALERT_MIN = C.RATIO_ALERT_MIN
WEIGHT_RATIO_ALERT_MAX = C.WEIGHT_RATIO_ALERT_MAX
WEIGHT_RATIO_ALERT_MIN = C.WEIGHT_RATIO_ALERT_MIN
CONCENTRATION_ALERT = C.CONCENTRATION_ALERT

# Output
MAX_ALTERNATIVES = C.MAX_ALTERNATIVES
CARRIER_ALIASES = C.CARRIER_ALIASES
DEST_STATE_COL = C.DEST_STATE_COL
CARRIER_COL = C.CARRIER_COL

# Corporate carriers
GROUP_COL = C.GROUP_COL
CORPORATE_GROUP = C.CORPORATE_GROUP


# ============================================================
# LABELS (shown to the user, kept in pt-BR)
# ============================================================

BASIS_LABELS = {
    "zip": "região",
    "state": "UF",
    "plant": "planta",
}

BROAD_SCOPES = {
    "state": ("Região ampla", "Baixa"),
}


# ============================================================
# UTILITIES
# ============================================================

def _clean_zip(value):
    """Return only the digits, padded to 8 positions ('' if empty)."""

    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    if isinstance(value, float):
        try:
            value = int(value)
        except Exception:
            pass

    digits = "".join(ch for ch in str(value) if ch.isdigit())

    return digits.zfill(8) if digits else ""


def zip_to_state(zip_code):
    z = _clean_zip(zip_code)
    if not z:
        return None
    prefix = int(z[:5])
    for start, end, state in _STATE_ZIP_RANGES:
        if start <= prefix <= end:
            return state
    return None


def _to_float(value):
    """float, or None if empty/NaN/invalid."""

    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(value):
    number = _to_float(value)
    return "—" if number is None else f"{number * 100:.0f}%"


def _brl(value):
    number = _to_float(value)

    if number is None:
        return "—"

    return (
        f"R$ {number:,.2f}"
        .replace(",", "X").replace(".", ",").replace("X", ".")
    )


def _per_kg(brl_per_100kg):
    """BRL/100 kg -> BRL/kg (None if empty)."""
    number = _to_float(brl_per_100kg)
    return None if number is None else number / 100


def _thousands(value):
    """1234.5 -> '1.235' (Brazilian format, no decimal places)."""
    return f"{value:,.0f}".replace(",", ".")


def _times(ratio):
    """4.43 -> '4,4x'."""
    return f"{ratio:.1f}".replace(".", ",") + "x"


def _scope_name(key, level):
    # "uf" is the value consumed by the frontend (contract).
    return f"CEP{level}" if key == "zip" else "uf"


# ============================================================
# ZIP CODE
# ============================================================

_zip_cache = {}

_STATE_ZIP_RANGES = [
    (1000, 19999, "SP"), (20000, 28999, "RJ"), (29000, 29999, "ES"),
    (30000, 39999, "MG"), (40000, 48999, "BA"), (49000, 49999, "SE"),
    (50000, 56999, "PE"), (57000, 57999, "AL"), (58000, 58999, "PB"),
    (59000, 59999, "RN"), (60000, 63999, "CE"), (64000, 64999, "PI"),
    (65000, 65999, "MA"), (66000, 68899, "PA"), (68900, 68999, "AP"),
    (69000, 69299, "AM"), (69300, 69399, "RR"), (69400, 69899, "AM"),
    (69900, 69999, "AC"), (70000, 72799, "DF"), (72800, 72999, "GO"),
    (73000, 73699, "DF"), (73700, 76799, "GO"), (76800, 76999, "RO"),
    (77000, 77999, "TO"), (78000, 78899, "MT"), (78900, 78999, "RO"),
    (79000, 79999, "MS"), (80000, 87999, "PR"), (88000, 89999, "SC"),
    (90000, 99999, "RS"),
]


def _zip_info(zip_code):

    zip_code = _clean_zip(zip_code)

    if not zip_code:
        return None

    if zip_code in _zip_cache:
        return _zip_cache[zip_code]

    try:
        info = validar_cep(zip_code)
    except Exception:
        log.warning("Failed to look up ZIP code %s", zip_code, exc_info=True)
        return None

    # Failures are not cached.
    if info:
        _zip_cache[zip_code] = info

    return info


# ============================================================
# HISTORY (TRIPS AND ROWS)
# ============================================================

def _normalize_carrier(df):
    """Clean the name, apply aliases and drop rows without a carrier."""

    names = (
        df[CARRIER_COL]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    if CARRIER_ALIASES:
        names = names.replace(CARRIER_ALIASES)

    df[CARRIER_COL] = names

    return df[names != ""].copy()


def _prepare_trips(df):
    """
    TRIPS dataset (1 row per freight_id).
    Used for the ranking: SLA, trip count, weight and recency.
    """

    if df is None or df.empty:
        return pd.DataFrame()

    df = _normalize_carrier(df.copy())

    df["issuing_plant_code"] = (
        df["issuing_plant_code"].astype(str).str.strip()
    )

    df["cep_destino"] = df["cep_destino"].map(_clean_zip)

    if DEST_STATE_COL not in df.columns:
        first_zip = (
            df["ceps_destino"].fillna("").astype(str).str.split("|").str[0].str.strip()
            if "ceps_destino" in df.columns else ""
        )
        base_zip = df["cep_destino"].where(df["cep_destino"] != "", first_zip)
        df[DEST_STATE_COL] = base_zip.map(zip_to_state)

    df["sla_ok"] = pd.to_numeric(
        df["sla_frete"], errors="coerce"
    ).astype("float64")

    df["valor_pago"] = pd.to_numeric(
        df["valor_pago"], errors="coerce"
    ).fillna(0)

    if "data_fim" in df.columns:
        df["data_fim"] = pd.to_datetime(df["data_fim"], errors="coerce")

    if "quantidade" in df.columns:
        df["peso_kg"] = pd.to_numeric(df["quantidade"], errors="coerce")
    elif "peso_kg" not in df.columns:
        df["peso_kg"] = np.nan

    return df


def _prepare_rows(df):
    """
    ROWS dataset (1 row per original record).
    Used to compute the amount paid and, if the trips dataset does not
    carry the group, to identify corporate carriers.
    """

    columns = ["freight_id", CARRIER_COL, "valor_pago", "peso_kg"]

    if df is None or df.empty:
        return pd.DataFrame(columns=columns)

    # Load the group too, if present (used only for the corporate list).
    if GROUP_COL in df.columns:
        columns = columns + [GROUP_COL]

    rows = df[columns].copy()

    rows["freight_id"] = rows["freight_id"].astype(str).str.strip()
    rows = _normalize_carrier(rows)

    rows["valor_pago"] = pd.to_numeric(
        rows["valor_pago"], errors="coerce"
    ).fillna(0)

    rows["peso_kg"] = pd.to_numeric(rows["peso_kg"], errors="coerce")

    return rows


# --- In-memory cache (with expiry) ---------------------------

_cache = {
    "trips": {"df": None, "loaded_at": 0.0},
    "rows": {"df": None, "loaded_at": 0.0},
}


def _get_cached(name, load):

    entry = _cache[name]

    expired = (
        time.monotonic() - entry["loaded_at"] > HISTORY_TTL_SEC
    )

    if entry["df"] is None or expired:
        entry["df"] = load()
        entry["loaded_at"] = time.monotonic()

    return entry["df"]


def _trip_history():
    return _get_cached(
        "trips",
        lambda: _prepare_trips(obter_historico_consolidado()),
    )


def _row_history():
    return _get_cached(
        "rows",
        lambda: _prepare_rows(obter_historico_detalhado()),
    )


def reload_history():
    for entry in _cache.values():
        entry["df"] = None
        entry["loaded_at"] = 0.0


def _filter_period(df, months):

    if df.empty or "data_fim" not in df.columns:
        return df

    dates = df["data_fim"].dropna()

    if dates.empty:
        return df

    start_date = dates.max() - pd.DateOffset(months=months)

    return df[df["data_fim"] >= start_date].copy()


# ============================================================
# DISTANCE / TRUCK / REFERENCE COSTS
# ============================================================

def _calculate_distance(plant, destination_zip):

    if not isinstance(plant, dict):
        log.warning("Invalid plant for distance calculation: %r", plant)
        return None

    origin_zip = _clean_zip(plant.get("cep"))
    destination_zip = _clean_zip(destination_zip)

    if not origin_zip or not destination_zip:
        return None

    origin = _zip_info(origin_zip)
    destination = _zip_info(destination_zip)

    if not origin or not destination:
        return None

    try:
        return distancia_km(origin, destination)
    except Exception:
        log.warning("Failed to calculate distance", exc_info=True)
        return None


def _truck(weight):

    try:
        return recomendar_caminhao(weight)
    except Exception:
        log.warning("Failed to recommend truck", exc_info=True)
        return None


def _reference_costs(freight):

    try:
        return calcular_custos(
            uf=freight["uf"],
            peso_kg=freight["peso_kg"],
            eixos=freight["eixos"],
            categoria=freight["categoria"],
            trechos=freight["trechos"],
        )

    except Exception:
        log.warning("Failed to calculate reference costs", exc_info=True)

        return {
            "antt": None,
            "mercado": None,
            "distancia_total_km": None,
            "litros_totais": None,
            "custo_combustivel": None,
        }


# ============================================================
# TRIP WEIGHTING (CARGO WEIGHT x RECENCY)
# ============================================================

def _weight_factor(historical_weights, new_weight):
    """
    How much each trip resembles the new freight in weight.

        1.00 -> same weight
        0.50 -> 2x difference
        0.04 -> 25x difference

    A missing weight gets MISSING_WEIGHT_FACTOR (neutral).
    """

    factor = pd.Series(1.0, index=historical_weights.index)

    try:
        new_weight = float(new_weight)
    except (TypeError, ValueError):
        return factor

    if not new_weight > 0:
        return factor

    weights = pd.to_numeric(historical_weights, errors="coerce")
    weights = weights.where(weights > 0)

    log_distance = np.log(weights / new_weight).abs()

    return np.exp(-log_distance).fillna(MISSING_WEIGHT_FACTOR)


def _recency_factor(dates, ref_date):
    """Loses half its weight every HALF_LIFE_DAYS."""

    if ref_date is None or pd.isna(ref_date):
        return pd.Series(1.0, index=dates.index)

    days = (ref_date - dates).dt.days.clip(lower=0)

    return (0.5 ** (days / HALF_LIFE_DAYS)).fillna(0.5)


def _weighting(trips, new_weight, ref_date=None):
    """Final weight of each trip = weight factor x recency factor."""

    weighting = _weight_factor(trips["peso_kg"], new_weight)

    if "data_fim" in trips.columns:

        if ref_date is None:
            ref_date = trips["data_fim"].max()

        weighting = weighting * _recency_factor(
            trips["data_fim"], ref_date
        )

    return weighting


# ============================================================
# AMOUNT PAID: BRL PER 100 KG (AND BRL PER KG)
# ============================================================

def _weight_as_float(weight_kg):
    """Weight as a positive float, or None."""

    try:
        weight = float(weight_kg)
    except (TypeError, ValueError):
        return None

    return weight if weight > 0 else None


def _trips_in_weight_band(trips, weight_kg):
    """
    Trips whose total weight is between WEIGHT_BAND_MIN x and
    WEIGHT_BAND_MAX x the order weight.

    Freight has a fixed cost per trip: BRL/100 kg is only comparable
    between loads of similar size.
    """

    weight = _weight_as_float(weight_kg)

    if weight is None:
        return trips.iloc[0:0]

    weights = pd.to_numeric(trips["peso_kg"], errors="coerce")

    return trips[
        (weights >= weight * WEIGHT_BAND_MIN)
        & (weights <= weight * WEIGHT_BAND_MAX)
    ]


def _rows_with_value_and_weight(rows, trips):
    """
    Rows of the given trips with a known amount AND weight.

    Requiring both avoids a row with an amount but no weight entering
    the sum of amounts but not the sum of weights (which would inflate
    BRL/100 kg).
    """

    if rows is None or rows.empty or trips.empty:
        return rows.iloc[0:0] if rows is not None else pd.DataFrame()

    return rows[
        rows["freight_id"].isin(trips["freight_id"])
        & (rows["valor_pago"] > 0)
        & (rows["peso_kg"] > 0)
    ]


def _brl_per_100kg_by_carrier(rows, scope_trips, weight_kg):
    """
    Series carrier -> BRL per 100 kg, using only trips within the
    order's weight band.

    Computes BRL/100 kg for each trip (sum(amount) / sum(weight) * 100)
    and uses the MEDIAN across the carrier's trips.
    """

    in_band = _trips_in_weight_band(scope_trips, weight_kg)
    selected = _rows_with_value_and_weight(rows, in_band)

    if selected.empty:
        return pd.Series(dtype="float64")

    sums = selected.groupby([CARRIER_COL, "freight_id"])[
        ["valor_pago", "peso_kg"]
    ].sum()

    per_trip = sums["valor_pago"] / sums["peso_kg"] * 100
    per_trip = per_trip[per_trip >= MIN_BRL_PER_100KG]

    # Median across trips: robust to trips with odd data.
    return per_trip.groupby(level=0).median()


def _summarize_by_trip(rows):
    """
    One row per trip: amount, weight and BRL/100 kg
    (sum(amount) / sum(weight) * 100).

    Drops trips with BRL/100 kg below MIN_BRL_PER_100KG.
    """

    sums = rows.groupby("freight_id")[["valor_pago", "peso_kg"]].sum()
    sums["rs_100kg"] = sums["valor_pago"] / sums["peso_kg"] * 100

    return sums[sums["rs_100kg"] >= MIN_BRL_PER_100KG]


def _economic_reference(scope_trips, rows, carrier, weight_kg):
    """
    Amount-paid reference for the new freight.

    1. Select the scope's TRIPS within the order's weight band.
    2. Compute BRL/100 kg for each trip (rows with amount and weight).
    3. Use the MEDIAN across trips (and P25/P75 as the typical range).
    4. BRL/kg = BRL/100 kg / 100.
    5. Estimate = BRL/100 kg x new freight weight / 100.

    Order of attempts:
        a) only the recommended carrier;
        b) all carriers on the same route.

    Without MIN_REFERENCE_TRIPS trips, returns None.
    """

    if rows is None or rows.empty:
        return None

    weight = _weight_as_float(weight_kg)

    if weight is None:
        return None

    in_band = _trips_in_weight_band(scope_trips, weight)

    if in_band.empty:
        return None

    rows_in_band = _rows_with_value_and_weight(rows, in_band)

    attempts = (
        (
            "transportadora",
            rows_in_band[rows_in_band[CARRIER_COL] == carrier],
        ),
        (
            "rota (todas as transportadoras)",
            rows_in_band,
        ),
    )

    for source, reference_rows in attempts:

        if reference_rows.empty:
            continue

        summary = _summarize_by_trip(reference_rows)
        trip_count = len(summary)

        if trip_count < MIN_REFERENCE_TRIPS:
            continue

        per_trip = summary["rs_100kg"]
        typical_weight = float(summary["peso_kg"].median())

        brl_median = per_trip.median()
        brl_p25, brl_p75 = per_trip.quantile([0.25, 0.75]).tolist()

        total_amount = summary["valor_pago"].sum()
        total_weight = summary["peso_kg"].sum()

        def for_freight(brl_per_100kg):
            return float(brl_per_100kg * weight / 100)

        estimate = for_freight(brl_median)

        log.debug(
            "Economic reference | carrier=%s | source=%s | weight=%s | "
            "trips=%s | rows=%s | BRL/100kg median=%.2f",
            carrier, source, weight,
            trip_count, len(reference_rows), brl_median,
        )

        return {
            "rs_por_100kg": float(brl_median),
            "rs_por_100kg_p25": float(brl_p25),
            "rs_por_100kg_p75": float(brl_p75),
            "rs_por_100kg_soma": float(total_amount / total_weight * 100),
            "rs_por_kg": float(brl_median / 100),
            "rs_por_kg_p25": float(brl_p25 / 100),
            "rs_por_kg_p75": float(brl_p75 / 100),
            "rs_por_kg_soma": float(total_amount / total_weight),
            "estimativa_frete": estimate,
            "estimativa_min": for_freight(brl_p25),
            "estimativa_max": for_freight(brl_p75),
            "media_pago": estimate,  # compatible with custo_medio_frete
            "soma_valor": float(total_amount),
            "soma_peso_kg": float(total_weight),
            "peso_tipico_kg": typical_weight,
            "razao_peso_vs_tipico": float(weight / typical_weight),
            "linhas": int(len(reference_rows)),
            "viagens": int(trip_count),
            "faixa_kg": (
                round(weight * WEIGHT_BAND_MIN),
                round(weight * WEIGHT_BAND_MAX),
            ),
            "origem": source,
        }

    return None


def _ratio_vs_antt(estimate, reference_costs):
    """Historical estimate / ANTT cost, or None if it cannot be computed."""

    if not isinstance(reference_costs, dict):
        return None

    antt = _to_float(reference_costs.get("antt"))
    estimate = _to_float(estimate)

    if estimate is None or not antt or antt <= 0:
        return None

    return estimate / antt


# ============================================================
# RANKING BY CARRIER
# ============================================================

def _by_carrier(
    scope_trips,
    global_sla_mean,
    weight_kg=None,
    ref_date=None,
    rows=None,
):
    """
    One row per carrier, sorted by:

        1. adjusted_sla (weighted and smoothed)
        2. trip count

    Columns:
        trips                 distinct trips (freight_id)
        effective_n           sample after weighting
        sla                   raw SLA
        adjusted_sla          SLA used in the ranking
        brl_per_100kg         BRL per 100 kg (trips within the weight band)
        avg_paid_trip         estimate for the order weight
                              (brl_per_100kg x weight / 100); not ranked
        avg_paid_trip_valued  same as above (legacy name)
    """

    columns = [
        "trips",
        "effective_n",
        "sla",
        "adjusted_sla",
        "brl_per_100kg",
        "avg_paid_trip",
        "avg_paid_trip_valued",
    ]

    if scope_trips.empty:
        return pd.DataFrame(columns=columns)

    if global_sla_mean is None or pd.isna(global_sla_mean):
        global_sla_mean = 0.0

    trips = scope_trips.drop_duplicates(
        subset=["freight_id", CARRIER_COL]
    ).copy()

    # --- Similarity weights ---
    trips["weighting"] = _weighting(trips, weight_kg, ref_date)

    has_sla = trips["sla_ok"].notna()

    trips["weight_with_sla"] = trips["weighting"].where(has_sla, 0.0)
    trips["weight_on_time"] = (
        trips["weighting"] * trips["sla_ok"]
    ).fillna(0.0)

    # --- Aggregation per carrier ---
    grouped = trips.groupby(CARRIER_COL)

    trip_count = grouped["freight_id"].nunique()
    trips_with_sla = grouped["sla_ok"].count()
    trips_on_time = grouped["sla_ok"].sum(min_count=1)

    effective_sample = grouped["weight_with_sla"].sum()
    weighted_on_time = grouped["weight_on_time"].sum()

    # SLA smoothed towards the global mean:
    # carriers with a small effective sample are pulled more to the mean.
    adjusted_sla = (
        weighted_on_time + SLA_SMOOTHING * global_sla_mean
    ) / (
        effective_sample + SLA_SMOOTHING
    )

    # --- Amount paid (BRL/100 kg and estimate for the order weight) ---
    brl_per_100kg = _brl_per_100kg_by_carrier(
        rows, trips, weight_kg
    ).reindex(trip_count.index)

    weight = _weight_as_float(weight_kg)
    avg_paid = (
        brl_per_100kg * weight / 100 if weight is not None
        else pd.Series(np.nan, index=trip_count.index)
    )

    table = pd.DataFrame({
        "trips": trip_count,
        "effective_n": effective_sample,
        "sla": trips_on_time / trips_with_sla,
        "adjusted_sla": adjusted_sla,
        "brl_per_100kg": brl_per_100kg,
        "avg_paid_trip": avg_paid,
        "avg_paid_trip_valued": avg_paid,
    })

    return table.sort_values(
        ["adjusted_sla", "trips"],
        ascending=[False, False],
    )


def _valid(table):
    """Carriers with the minimum sample and at least one known SLA."""

    if table.empty:
        return table

    return table[
        (table["trips"] >= MIN_CARRIER_TRIPS)
        & table["sla"].notna()
    ].copy()


def _all_corporate_carriers(trips, rows=None):
    """
    All corporate carriers (service_agent_group = VBR6), with no minimum
    trips. VBR7 (individuals) is left out.

    Looks for the group in the trips dataset; if it has no such column,
    tries the rows dataset.
    """

    for base in (trips, rows):

        if base is None or base.empty or GROUP_COL not in base.columns:
            continue

        group = (
            base[GROUP_COL].fillna("").astype(str).str.strip().str.upper()
        )

        corporate = base[group.str.startswith(CORPORATE_GROUP.upper())]

        return sorted(corporate[CARRIER_COL].unique().tolist())

    log.warning(
        "Column %s missing from history: corporate carrier list is empty",
        GROUP_COL,
    )

    return []


# ============================================================
# CONFIDENCE AND TIES
# ============================================================

def classify_confidence(sla, trips):

    if sla is None or pd.isna(sla):
        return "Baixa"

    if sla >= SLA_HIGH and trips >= TRIPS_HIGH:
        return "Alta"

    if sla >= SLA_MEDIUM and trips >= MIN_CARRIER_TRIPS:
        return "Média"

    return "Baixa"


def _detect_tie(valid):
    """
    Carriers within TIE_THRESHOLD of the first one (including the first).
    Empty list if there is no tie.
    """

    if valid is None or len(valid) < 2:
        return []

    top_sla = valid["adjusted_sla"].iloc[0]

    close = valid[
        (top_sla - valid["adjusted_sla"]) < TIE_THRESHOLD
    ]

    return close.index.tolist() if len(close) > 1 else []


# ============================================================
# ALTERNATIVES
# ============================================================

def _build_alternatives(tables, exclude=None, limit=MAX_ALTERNATIVES):
    """
    tables: list of (key, level, table), from the most specific scope
    to the broadest. The first occurrence of each carrier wins.
    """

    if exclude is None:
        exclude = []

    if isinstance(exclude, str):
        exclude = [exclude]

    already_listed = set(exclude)
    alternatives = []

    for key, level, table in tables:

        for name, row in table.iterrows():

            if name in already_listed:
                continue

            already_listed.add(name)

            adjusted_sla = _to_float(row["adjusted_sla"])
            trips = int(row["trips"])

            confidence = classify_confidence(adjusted_sla, trips)

            if key == "state":
                confidence = "Baixa"

            alternatives.append({
                "nome": name,
                "rs_por_100kg": _to_float(row["brl_per_100kg"]),
                "rs_por_kg": _per_kg(row["brl_per_100kg"]),
                "media_paga": _to_float(row["avg_paid_trip"]),
                "media_paga_valorada": _to_float(
                    row["avg_paid_trip_valued"]
                ),
                "sla": _pct(row["sla"]),
                "viagens": trips,
                "confianca": confidence,
                "base": BASIS_LABELS[key],
                "escopo": _scope_name(key, level),
            })

            if len(alternatives) >= limit:
                return alternatives

    return alternatives


# ============================================================
# GEOGRAPHIC SCOPES
# ============================================================

def _scopes(base, plant_code, zip_code, state):
    """
    Yield (key, level, trips) from the most specific to the broadest:

        ZIP5 -> ZIP4 -> ZIP3 -> state

    Only trips from the same plant. Trips with multiple destinations
    are excluded from the ZIP levels.
    """

    plant_base = base[base["issuing_plant_code"] == str(plant_code)]

    if "rota_multipla" in plant_base.columns:
        zip_base = plant_base[
            ~plant_base["rota_multipla"].fillna(False).astype(bool)
        ]
    else:
        zip_base = plant_base

    if zip_code:

        zips = zip_base["cep_destino"].astype(str)

        for level in ZIP_LEVELS:
            yield (
                "zip",
                level,
                zip_base[zips.str[:level] == zip_code[:level]],
            )

    if state and DEST_STATE_COL in plant_base.columns:

        same_state = (
            plant_base[DEST_STATE_COL].astype(str).str.upper()
            == str(state).upper()
        )

        yield "state", None, plant_base[same_state]


def _select_scope(
    base,
    plant_code,
    zip_code,
    state,
    global_sla_mean,
    weight_kg=None,
    ref_date=None,
    rows=None,
):
    """
    Return (key, level, scope_trips, valid) for the first scope that has
    at least one valid carrier, or None.
    """

    for key, level, scope_trips in _scopes(
        base, plant_code, zip_code, state
    ):

        if scope_trips.empty:
            continue

        table = _by_carrier(
            scope_trips, global_sla_mean, weight_kg, ref_date, rows
        )

        valid = _valid(table)

        if valid.empty:
            continue

        return key, level, scope_trips, valid

    return None


def _broader_tables(
    base,
    plant_code,
    zip_code,
    state,
    global_sla_mean,
    weight_kg,
    ref_date,
    rows,
    winning_key,
    winning_level,
):
    """
    Yield (key, level, valid) for the scopes BROADER than the winner.
    Only used to fill in the list of alternatives.
    """

    passed_winner = False

    for key, level, scope_trips in _scopes(
        base, plant_code, zip_code, state
    ):

        if not passed_winner:
            passed_winner = (
                key == winning_key and level == winning_level
            )
            continue

        if scope_trips.empty:
            continue

        valid = _valid(
            _by_carrier(
                scope_trips, global_sla_mean, weight_kg, ref_date, rows
            )
        )

        if not valid.empty:
            yield key, level, valid


# ============================================================
# TEXTS (shown to the user, kept in pt-BR)
# ============================================================

def _type_and_max_confidence(key, level):

    if key == "zip":
        return ("Direta" if level >= 5 else "Rota similar"), None

    return BROAD_SCOPES[key]


def _build_detail(key, level, zip_code, plant, state, scope_trip_count):

    criterion = (
        "com peso maior para cargas de porte e data mais próximos."
    )

    if key == "zip" and level >= 5:
        return (
            f"Baseada em {scope_trip_count} viagens "
            f"com destino na mesma região de CEP, {criterion}"
        )

    if key == "zip":
        return (
            f"Baseada em {scope_trip_count} viagens "
            f"com destino na região do CEP {zip_code[:level]}…, {criterion}"
        )

    if key == "state":
        return (
            "Sem histórico suficiente para esta rota específica. "
            f"Baseada em {scope_trip_count} viagens "
            f"da planta {plant['codigo']} para a UF {state}."
        )

    return "Não foi encontrada uma base geográfica compatível."


def _scope_warning(key):

    if key == "state":
        return (
            "Não há histórico suficiente para esta rota específica. "
            "A sugestão utiliza um critério regional mais amplo "
            "e tem confiança baixa."
        )

    return None


def _reference_warning(estimate, ratio, reference_costs):

    if ratio is None or RATIO_ALERT_MIN <= ratio <= RATIO_ALERT_MAX:
        return None

    return (
        f"A estimativa histórica ({_brl(estimate)}) está em "
        f"{_times(ratio)} a referência ANTT "
        f"({_brl(reference_costs.get('antt'))}). Confira se o valor "
        "histórico inclui outros custos ou se as cargas são comparáveis."
    )


def _atypical_weight_warning(weight, reference):

    if not reference:
        return None

    ratio = reference["razao_peso_vs_tipico"]

    if WEIGHT_RATIO_ALERT_MIN <= ratio <= WEIGHT_RATIO_ALERT_MAX:
        return None

    return (
        f"O peso deste frete ({_thousands(weight)} kg) é {_times(ratio)} o peso "
        f"típico desta rota ({_thousands(reference['peso_tipico_kg'])} kg). "
        "O preço é extrapolado de forma proporcional, mas parte do "
        "custo é fixa por viagem; trate a estimativa como aproximada."
    )


def _concentration_warning(carrier, carrier_trips, scope_trips):

    if not scope_trips:
        return None

    share = carrier_trips / scope_trips

    if share < CONCENTRATION_ALERT:
        return None

    return (
        f"{carrier} fez {share:.0%} das viagens desta rota: "
        "a sugestão reflete o histórico, não uma comparação "
        "entre transportadoras."
    )


def _tie_warning(tied):

    if not tied:
        return None

    names = ", ".join(tied[:3])

    return (
        "Diferença pequena de SLA entre as primeiras opções "
        f"({names}). A escolha entre elas é livre; "
        "considere outros critérios."
    )


# ============================================================
# BUILDING THE RESPONSE
# ============================================================

def _base_output(
    freight, id_, calculation, plant, zip_code, weight, dest_city, dest_state
):
    """Fields present in every response (with or without a suggestion)."""

    city = dest_city
    state = dest_state

    if city:
        destination_text = city + (f", {state}" if state else "")
    else:
        destination_text = (
            f"CEP {zip_code}" if zip_code else "Destino não informado"
        )

    return {
        "id": id_,
        "pedido": freight.get("pedido", "—"),
        "peso": f"{weight:,.0f} kg".replace(",", "."),
        "origem": f"{plant['cidade']} ({plant['codigo']})",
        "destino": destination_text,
        "paradas": len(freight.get("trechos", [])),
        "caminhao": _truck(weight),
        "distancia_km": _calculate_distance(plant, zip_code),
        "custos_ref": (
            calculation if calculation is not None
            else _reference_costs(freight)
        ),
        "alternativas": [],
        "outras_transportadoras": [],
        "custo_medio_frete": None,
        "rs_por_kg": None,
        "media_paga_viagem": None,
        "media_paga_viagem_valorada": None,
        "referencia_economica": None,
        "referencia_economica_disponivel": False,
        "periodo_historico_meses": HISTORY_MONTHS,
        "viagens_similares": 0,
        "viagens_transportadora": 0,
        "escopo": None,
        "aviso": None,
        "empate": False,
        "empatadas": [],
        "similarity": None,
        "similarRoutes": None,
    }


def _no_recommendation(output, kind, detail, alternatives=None):

    output.update({
        "tipo": kind,
        "transportadora": "—",
        "custo": "—",
        "sla": "—",
        "confianca": "Baixa",
        "detalhe": detail,
        "aviso": (
            "Sem sugestão automática. "
            "Escolha uma transportadora nas opções abaixo."
        ),
        "alternativas": alternatives or [],
    })

    return output


def _fill_similarity(
    output,
    key,
    level,
    zip_code,
    plant,
    dest_city,
    scope_trips,
    scope_trip_count,
    raw_sla,
):
    """Fill the 'similarity' and 'similarRoutes' blocks (ZIP scopes only)."""

    if key != "zip":
        return

    if level >= 5:
        region = f"CEP {zip_code[:level]}"

        routes = [{
            "rota": f"{plant['cidade']} → {dest_city}",
            "viagens": f"{scope_trip_count} viagens",
            "detalhe": "Mesmo CEP de destino",
        }]

    else:
        region = f"CEP {zip_code[:level]}…"

        trips_by_city = (
            scope_trips
            .groupby("cidade_destino")["freight_id"]
            .nunique()
            .sort_values(ascending=False)
            .head(4)
        )

        routes = [
            {
                "rota": f"{plant['cidade']} → {city}",
                "viagens": f"{count} viagens",
                "detalhe": region,
            }
            for city, count in trips_by_city.items()
        ]

    output["similarity"] = {
        "viagens": scope_trip_count,
        "distanciaOrigem": "mesma planta",
        "distanciaDestino": region,
        "sla": _pct(raw_sla),
    }

    output["similarRoutes"] = routes


# ============================================================
# RECOMMEND
# ============================================================

def recommend(freight, id_, calculation=None):
    """
    freight:     freight dictionary.
    id_:         freight ID.
    calculation: cost calculation already done (avoids redoing it).
    """

    # --- Freight data ---
    plant = freight["planta"]
    zip_code = _clean_zip(freight.get("cep"))
    weight = freight["peso_kg"]
    dest_city = freight["destino"]
    dest_state = freight["uf"]

    output = _base_output(
        freight, id_, calculation, plant, zip_code, weight,
        dest_city, dest_state,
    )

    # --- History ---
    history = _trip_history()
    rows = _row_history()

    # Manual-choice list: all corporate carriers (VBR6), before the period
    # filter and with no minimum trips. Present even without a recommendation.
    output["outras_transportadoras"] = _all_corporate_carriers(
        history, rows
    )

    base = _filter_period(history, HISTORY_MONTHS)

    if base.empty:
        return _no_recommendation(
            output,
            "Sem histórico",
            "Não existem dados históricos no período selecionado.",
        )

    # Global SLA mean: only for smoothing (not a fallback).
    global_sla_mean = base["sla_ok"].mean()

    if pd.isna(global_sla_mean):
        global_sla_mean = SLA_MEDIUM

    ref_date = (
        base["data_fim"].max() if "data_fim" in base.columns else None
    )

    # --- Scope choice ---
    selection = _select_scope(
        base=base,
        plant_code=plant["codigo"],
        zip_code=zip_code,
        state=dest_state,
        global_sla_mean=global_sla_mean,
        weight_kg=weight,
        ref_date=ref_date,
        rows=rows,
    )

    if selection is None:
        return _no_recommendation(
            output,
            "Sem histórico",
            "Não há histórico suficiente para esta rota ou região. "
            "Não foi possível gerar uma recomendação automática.",
        )

    key, level, scope_trips, valid = selection

    kind, max_confidence = _type_and_max_confidence(key, level)

    # --- Recommended carrier ---
    best = valid.iloc[0]
    carrier = valid.index[0]

    scope_trip_count = int(scope_trips["freight_id"].nunique())
    carrier_trip_count = int(best["trips"])

    raw_sla = _to_float(best["sla"])
    adjusted_sla = _to_float(best["adjusted_sla"])
    avg_paid = _to_float(best["avg_paid_trip"])

    confidence = classify_confidence(adjusted_sla, carrier_trip_count)

    if max_confidence == "Baixa":
        confidence = "Baixa"

    tied = _detect_tie(valid)

    # --- Economic reference (ZIP5 only) ---
    reference = None

    if key == "zip" and level >= 5:
        reference = _economic_reference(
            scope_trips, rows, carrier, weight
        )

    # --- Alternatives (winning scope + broader ones) ---
    tables = [(key, level, valid)]

    tables.extend(
        _broader_tables(
            base,
            plant["codigo"],
            zip_code,
            dest_state,
            global_sla_mean,
            weight,
            ref_date,
            rows,
            key,
            level,
        )
    )

    alternatives = _build_alternatives(tables, [carrier])

    # --- Warnings ---
    antt_ratio = (
        _ratio_vs_antt(reference["estimativa_frete"], output["custos_ref"])
        if reference else None
    )

    if reference:
        reference["razao_vs_antt"] = antt_ratio

    warnings = [
        warning
        for warning in (
            _scope_warning(key),
            _tie_warning(tied),
            _concentration_warning(
                carrier, carrier_trip_count, scope_trip_count
            ),
            _atypical_weight_warning(_weight_as_float(weight), reference),
            _reference_warning(
                reference["estimativa_frete"] if reference else None,
                antt_ratio,
                output["custos_ref"],
            ),
        )
        if warning
    ]

    # --- Result ---
    output.update({
        "tipo": kind,
        "escopo": _scope_name(key, level),
        "transportadora": carrier,
        "custo": "—",
        "sla": _pct(raw_sla),
        "confianca": confidence,
        "aviso": " ".join(warnings) if warnings else None,
        "avisos": warnings,  # list, so the UI can show one per line
        "empate": bool(tied),
        "empatadas": tied,
        "detalhe": _build_detail(
            key, level, zip_code, plant, dest_state, scope_trip_count
        ),
        "viagens_similares": scope_trip_count,
        "viagens_transportadora": carrier_trip_count,
        "custo_medio_frete": (
            reference["media_pago"] if reference else None
        ),
        # ZIP5: median of the economic reference.
        # Broader scopes: the carrier's own BRL/100 kg (from the table).
        "rs_por_kg": (
            reference["rs_por_kg"] if reference
            else _per_kg(best["brl_per_100kg"])
        ),
        "referencia_economica": reference,
        "referencia_economica_disponivel": reference is not None,
        "media_paga_viagem": avg_paid,
        "media_paga_viagem_valorada": avg_paid,
        "alternativas": alternatives,
        "rota_multipla_historico": False,
    })

    _fill_similarity(
        output,
        key,
        level,
        zip_code,
        plant,
        dest_city,
        scope_trips,
        scope_trip_count,
        raw_sla,
    )

    return output


# ============================================================
# DEPRECATED ALIASES (old Portuguese names)
# Remove once every caller uses the new names.
# ============================================================

def recomendar(frete, id_, calculo=None):
    return recommend(frete, id_, calculation=calculo)


classificar_confianca = classify_confidence
recarregar_historico = reload_history
cep_para_uf = zip_to_state
_historico = _trip_history  # kept for diagnostic scripts


