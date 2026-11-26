from flask_login import current_user

import math
from flask import (
    Blueprint,
    jsonify,
    render_template,
    request,
)
from services.freight_repository import (
    listar_fretes_em_oferta,
    registrar_proposta,
)

import logging
log = logging.getLogger(__name__)

from services.weather import weather


home_bp = Blueprint("home", __name__)

@home_bp.route("/")
def home():
    shipments = listar_fretes_em_oferta(None if current_user.role == "carrier" or current_user.is_admin else current_user.plants)

    weather_cache = {}

    for shipment in shipments:
        destination = shipment.get("destino") or ""

        # Destino armazenado como dicionário
        if isinstance(destination, dict):
            city = destination.get("cidade")
            state = destination.get("uf")

            if city and state:
                location = f"{city}, {state}, Brazil"
            else:
                location = city

        # Destino armazenado como texto
        elif isinstance(destination, str):
            location = destination.strip()

        else:
            location = None

        # Valor padrão caso não seja possível consultar
        shipment["clima"] = None

        if not location:
            continue

        # Evita consultar a mesma cidade várias vezes
        if location not in weather_cache:
            weather_cache[location] = (
                weather.get_current_weather(location)
            )

        shipment["clima"] = weather_cache[location]

        log.info(
            f"CLIMA [{location}]:",
            shipment["clima"]
        )

    return render_template(
        "carrier-portal.html",
        cargas=shipments,
        transportadoras_teste=(
            []
        )
    )




from flask_login import current_user, login_required

@home_bp.route("/api/ofertas/<int:frete_id>/propostas", methods=["POST"])
@login_required
def enviar_proposta(frete_id):

    # Somente transportadoras autenticadas podem enviar propostas.
    if current_user.role != "carrier":
        return jsonify({
            "ok": False,
            "erro": "Apenas transportadoras podem enviar propostas."
        }), 403

    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return jsonify({
            "ok": False,
            "erro": "Dados da proposta inválidos."
        }), 400

    # Identificação obtida da sessão, nunca do JavaScript.
    transportadora = str(
        current_user.carrier_name or ""
    ).strip()

    if not transportadora:
        return jsonify({
            "ok": False,
            "erro": "Transportadora não identificada na conta."
        }), 400

    try:
        valor = float(dados.get("valor"))

        if not math.isfinite(valor) or valor <= 0:
            raise ValueError()

    except (TypeError, ValueError, OverflowError):
        return jsonify({
            "ok": False,
            "erro": "Informe um valor proposto maior que zero."
        }), 400

    try:
        prazo_original = dados.get("prazo_dias")

        if isinstance(prazo_original, bool):
            raise ValueError()

        if isinstance(prazo_original, float) and not prazo_original.is_integer():
            raise ValueError()

        prazo_dias = int(prazo_original)

        if not 1 <= prazo_dias <= 365:
            raise ValueError()

    except (TypeError, ValueError, OverflowError):
        return jsonify({
            "ok": False,
            "erro": "Informe um prazo válido entre 1 e 365 dias."
        }), 400

    observacoes = str(
        dados.get("observacoes") or ""
    ).strip()

    if len(observacoes) > 2000:
        return jsonify({
            "ok": False,
            "erro": "Observações excedem 2000 caracteres."
        }), 400

    try:
        proposta_id = registrar_proposta(
            frete_id=frete_id,
            transportadora=transportadora,
            valor=valor,
            prazo_dias=prazo_dias,
            observacoes=observacoes,
        )

    except ValueError as erro:
        return jsonify({
            "ok": False,
            "erro": str(erro)
        }), 400

    except Exception:
        log.exception(
            "Erro ao registrar proposta do frete %s pela transportadora %s",
            frete_id,
            transportadora
        )

        return jsonify({
            "ok": False,
            "erro": "Erro interno ao registrar a proposta."
        }), 500

    return jsonify({
        "ok": True,
        "mensagem": "Proposta enviada com sucesso!",
        "proposta_id": proposta_id
    }), 201