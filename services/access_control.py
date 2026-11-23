from flask import abort
from flask_login import current_user
from services.freight_repository import obter_frete


def authorized_plants():
    return None if current_user.is_admin else current_user.plants


def plant_code(freight):
    plant = freight.get('planta') or {}
    return str(plant.get('codigo') or '') if isinstance(plant, dict) else str(plant)


def require_freight_access(freight_id):
    freight = obter_frete(freight_id)
    if not freight:
        abort(404)
    if not current_user.can_access_plant(plant_code(freight['detalhes'])):
        abort(403)
