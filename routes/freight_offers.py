from flask_login import current_user

import math
from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
)
from services.db import connect

from services.freight_repository import (
    listar_fretes_em_oferta,
    registrar_proposta,
)

import logging
log = logging.getLogger(__name__)

from services.weather import weather


home_bp = Blueprint("home", __name__)


def listar_transportadoras_teste():
    """Busca transportadoras conhecidas no banco para simular o login."""

    with connect(fretes) as conn:
        registros = conn.execute("""
            SELECT transportadora AS nome
            FROM fretes_propostas
            WHERE transportadora IS NOT NULL

            UNION

            SELECT transportadora_recomendada AS nome
            FROM fretes
            WHERE transportadora_recomendada IS NOT NULL

            UNION

            SELECT transportadora_escolhida AS nome
            FROM fretes
            WHERE transportadora_escolhida IS NOT NULL

            ORDER BY nome
        """).fetchall()

    transportadoras = [
        registro["nome"].strip()
        for registro in registros
        if registro["nome"] and registro["nome"].strip()
    ]

    if not transportadoras:
        transportadoras = [
            "Transportadora Teste A",
            "Transportadora Teste B",
            "Transportadora Teste C",
        ]

    return transportadoras





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




@home_bp.route("/api/ofertas/<int:frete_id>/propostas", methods=["POST"])
def enviar_proposta(frete_id):
    # Até existir autenticação, não permitir propostas em produção.
    if not current_app.debug:
        return jsonify({
            "ok": False,
            "erro": "É necessário autenticar a transportadora.",
        }), 403

    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return jsonify({
            "ok": False,
            "erro": "Dados da proposta inválidos.",
        }), 400

    transportadora = str(
        dados.get("transportadora") or ""
    ).strip()

    if transportadora not in listar_transportadoras_teste():
        return jsonify({
            "ok": False,
            "erro": "Selecione uma transportadora válida.",
        }), 400

    try:
        valor = float(dados.get("valor"))

        if not math.isfinite(valor) or valor <= 0:
            raise ValueError()

    except (TypeError, ValueError, OverflowError):
        return jsonify({
            "ok": False,
            "erro": "Informe um valor proposto maior que zero.",
        }), 400

    try:
        prazo_dias = int(dados.get("prazo_dias"))

        if not 0 <= prazo_dias <= 365:
            raise ValueError()

    except (TypeError, ValueError, OverflowError):
        return jsonify({
            "ok": False,
            "erro": "Informe um prazo válido em dias.",
        }), 400

    observacoes = str(
        dados.get("observacoes") or ""
    ).strip()

    if len(observacoes) > 2000:
        return jsonify({
            "ok": False,
            "erro": "Observações excedem 2000 caracteres.",
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
            "erro": str(erro),
        }), 400

    return jsonify({
        "ok": True,
        "mensagem": "Proposta enviada com sucesso!",
        "proposta_id": proposta_id,
    }), 201
