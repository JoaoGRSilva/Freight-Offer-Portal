
"""
Prepare persisted freight data for frontend rendering.

This service provides a consistent data structure for freight
details without modifying the database or recalculating costs.
"""

from services.freight_repository import (
    obter_frete as get_freight,
    listar_propostas as list_proposals,
    obter_fechamento as get_freight_closure,
)


def get_freight_view_data(freight_id: int) -> dict | None:
    """
    Retrieve and prepare freight details for the frontend.

    Args:
        freight_id: Freight primary key in SQLite.

    Returns:
        A dictionary containing freight, record, proposals,
        and closure data, or None if the freight does not exist.
    """

    freight_record = get_freight(freight_id)

    if freight_record is None:
        return None

    # Copy persisted freight data to avoid mutating the original record.
    freight = dict(freight_record.get("detalhes") or {})

    # Attach persistent identifiers and operational information.
    freight["db_id"] = freight_record["id"]
    freight["status_db"] = freight_record["status"]
    freight["transportadora_escolhida"] = (
        freight_record.get("transportadora_escolhida")
    )

    # Preserve compatibility with the existing frontend schema.
    freight["num"] = (
        freight_record.get("numero_frete")
        or freight.get("num")
    )

    freight["origem"] = (
        freight.get("origem")
        or freight_record.get("origem")
    )

    freight["destino"] = (
        freight.get("destino")
        or freight_record.get("destino")
    )

    # Preserve the recommendation generated during freight processing.
    recommendation = freight.get("recomendacao")

    if not isinstance(recommendation, dict):
        recommendation = {}

    freight["recomendacao"] = recommendation

    # Retrieve current operational data.
    proposals = list_proposals(freight_id)
    closure = get_freight_closure(freight_id)

    # Exclude duplicated raw JSON from the frontend payload.
    frontend_record = {
        key: value
        for key, value in freight_record.items()
        if key not in ("dados_json", "detalhes")
    }

    return {
        "frete": freight,
        "registro": frontend_record,
        "propostas": proposals,
        "fechamento": closure,
    }
