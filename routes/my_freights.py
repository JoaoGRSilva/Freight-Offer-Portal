import logging

from flask import (
    render_template,
    Blueprint,
    request,
    jsonify,
)

from flask_login import login_required, current_user

from services.freight_repository import (
    list_propose_send,
    responder_negociacao_transportadora,
)

log = logging.getLogger(__name__)

carrier_bp = Blueprint("carrier", __name__)


# ==========================================
# MEUS FRETES
# ==========================================

@carrier_bp.route("/meus-fretes", methods=["GET"])
@login_required
def meus_fretes():

    fretes = list_propose_send(current_user.carrier_name)

    return render_template(
        "my-freights.html",
        fretes=fretes
    )


# ==========================================
# RESPONDER NEGOCIAÇÃO
# ==========================================

@carrier_bp.route(
    "/api/meus-fretes/<int:frete_id>/propostas/<int:proposta_id>/responder",
    methods=["POST"],
)
@login_required
def responder_proposta(frete_id, proposta_id):

    dados = request.get_json(silent=True) or {}

    acao = dados.get("acao")

    valor = dados.get("valor")
    prazo_dias = dados.get("prazo_dias")
    observacoes = dados.get("observacoes", "")

    try:

        resultado = responder_negociacao_transportadora(
            frete_id=frete_id,
            proposta_id=proposta_id,
            transportadora=current_user.carrier_name,
            acao=acao,
            valor=valor,
            prazo_dias=prazo_dias,
            observacoes=observacoes,
        )

        return jsonify({
            "sucesso": True,
            **resultado,
        }), 200

    except ValueError as erro:

        return jsonify({
            "sucesso": False,
            "mensagem": str(erro),
        }), 400

    except Exception:

        log.exception(
            "Erro ao responder negociação. "
            "Frete=%s Proposta=%s",
            frete_id,
            proposta_id,
        )

        return jsonify({
            "sucesso": False,
            "mensagem": "Erro interno ao processar a negociação.",
        }), 500