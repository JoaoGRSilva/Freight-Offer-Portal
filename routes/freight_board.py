from services.access_control import authorized_plants, plant_code
from flask_login import current_user
"""
Rotas de /fretes: mesa de fretes, página de detalhe e todo o fluxo
operacional do frete (oferta, negociação, propostas, SAP e conclusão).

As rotas que antes ficavam na Nova Carga foram movidas para cá com as
MESMAS URLs. Assim, o JS não precisa mudar de endereço agora; os prefixos
podem ser trocados depois, com tudo funcionando.

IMPORTANTE: remova essas rotas do nova_carga.py ao instalar este arquivo.
Duas rotas com a mesma URL em blueprints diferentes causam confusão.
"""

import logging
import math

from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from analytics.truck import recomendar_caminhao
from services.freight_view import get_freight_view_data
from services.carrier_recommendation import (
    recommend,
    _all_corporate_carriers,
    _trip_history,
)
from services.json_utils import json_safe
from services.freight_repository import (
    listar_fretes,
    atualizar_status,
    obter_frete,
    obter_fechamento,
    registrar_proposta,
    aceitar_proposta,
    confirmar_sap,
    iniciar_negociacao,
    contrapropor,
    publicar_oferta,
    retirar_oferta,
    atualizar_dados_carga,
    concluir_frete,
    listar_transportadoras_negociacao,
)

log = logging.getLogger(__name__)

fretes_bp = Blueprint("fretes", __name__)


# ==========================================
# HELPERS
# ==========================================
def _eh_ajax():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _resposta_operacao(frete_id, sucesso, mensagem, status=200):
    """
    AJAX  -> JSON {sucesso, mensagem}
    Form  -> flash + redirect para a página de detalhe do frete
    """
    if _eh_ajax():
        return jsonify({"sucesso": sucesso, "mensagem": mensagem}), status

    flash(mensagem)
    return redirect(url_for("fretes.detalhe_frete", frete_id=frete_id))


def ensure_freight_recommendation(freight: dict, freight_id: int) -> dict:
    """
    Ensure recommendation data is available for the freight details page.

    Reuse the existing recommendation engine without changing its
    historical ranking or carrier eligibility rules.
    """
    recommendation = freight.get("recomendacao")

    if not isinstance(recommendation, dict):
        recommendation = {}

    # A truck-only fallback is not a complete recommendation.
    has_recommendation_result = (
        "transportadora" in recommendation
        or "tipo" in recommendation
        or "detalhe" in recommendation
    )

    if not has_recommendation_result:
        try:
            recommendation = recommend(
                freight,
                freight_id,
                calculation=freight.get("calculo"),
            )

            if not isinstance(recommendation, dict):
                raise TypeError(
                    "Recommendation engine returned an invalid result."
                )

            log.info(
                "Recommendation completed for freight %s: carrier=%s, type=%s",
                freight_id,
                recommendation.get("transportadora"),
                recommendation.get("tipo"),
            )

        except Exception:
            log.exception(
                "Recommendation engine failed for freight %s",
                freight_id,
            )
            recommendation = {
                **recommendation,
                "transportadora": None,
                "detalhe": (
                    "Não foi possível carregar a recomendação automática."
                ),
            }

    # Preserve an existing truck recommendation if the engine omits it.
    if not recommendation.get("caminhao"):
        try:
            weight = float(freight.get("peso_kg") or 0)

            if weight > 0:
                recommendation["caminhao"] = recomendar_caminhao(weight)

        except (TypeError, ValueError):
            log.warning(
                "Invalid freight weight for truck recommendation: %s",
                freight_id,
            )

    freight["recomendacao"] = recommendation
    return freight

# ==========================================
# MESA DE FRETES
# ==========================================
@fretes_bp.route("/fretes")
def fretes():
    registros = listar_fretes(authorized_plants())

    log.info(f"[MESA] Fretes encontrados: {len(registros)}")

    if registros:
        log.info("[MESA] Primeiro registro:", registros[0])

    return render_template(
        "freight-board.html",
        fretes=registros,
    )


@fretes_bp.route(
    "/nova-carga/fretes/<int:frete_id>/propostas/<int:proposta_id>/contrapropor",
    methods=["POST"],
)
def contrapropor_frete(frete_id, proposta_id):
    try:
        valor = request.form.get("valor")
        prazo_dias = request.form.get("prazo_dias")
        observacoes = request.form.get("observacoes", "")

        contrapropor(
            frete_id=frete_id,
            proposta_id=proposta_id,
            valor=valor,
            prazo_dias=prazo_dias or None,
            observacoes=observacoes,
        )

        return jsonify({
            "sucesso": True,
            "mensagem": "Contraproposta enviada com sucesso.",
        })

    except ValueError as erro:
        return jsonify({
            "sucesso": False,
            "mensagem": str(erro),
        }), 400

    except Exception:
        log.exception(
            "Erro ao registrar contraproposta do frete %s",
            frete_id,
        )

        return jsonify({
            "sucesso": False,
            "mensagem": "Erro interno ao registrar contraproposta.",
        }), 500

@fretes_bp.route(
    "/api/nova-carga/fretes/<int:frete_id>/negociacao",
    methods=["POST"],
)
def iniciar_negociacao_frete(frete_id):
    dados = request.get_json(silent=True) or {}
    transportadora = dados.get("transportadora")

    try:
        iniciar_negociacao(frete_id, transportadora)

        return jsonify({
            "sucesso": True,
            "mensagem": "Negociação iniciada com sucesso.",
        })

    except ValueError as erro:
        return jsonify({
            "sucesso": False,
            "mensagem": str(erro),
        }), 400

    except Exception:
        log.exception(
            "Erro ao iniciar negociação do frete %s",
            frete_id,
        )

        return jsonify({
            "sucesso": False,
            "mensagem": "Erro interno ao iniciar negociação.",
        }), 500

@fretes_bp.route(
    "/api/fretes/<int:frete_id>/status",
    methods=["PATCH"],
)
def alterar_status(frete_id):
    dados = request.get_json(silent=True) or {}
    novo_status = dados.get("status")

    # Estes status só podem ser alcançados pelo fluxo operacional
    # (aceitar proposta, confirmar SAP, concluir).
    if novo_status in ("cotacao_aceita", "concluido"):
        return jsonify({
            "sucesso": False,
            "erro": "Este status exige confirmação no fluxo operacional.",
        }), 409

    try:
        atualizado = atualizar_status(frete_id, novo_status)
    except ValueError as erro:
        return jsonify({"sucesso": False, "erro": str(erro)}), 400

    if not atualizado:
        return jsonify({
            "sucesso": False,
            "erro": "Frete não encontrado",
        }), 404

    return jsonify({
        "sucesso": True,
        "frete_id": frete_id,
        "status": novo_status,
    })

# ==========================================
# FREIGHT DETAILS PAGE
# ==========================================
@fretes_bp.route("/fretes/<int:frete_id>")
def detalhe_frete(frete_id):
    view_data = get_freight_view_data(frete_id)

    if view_data is None:
        abort(404)

    freight = view_data["frete"]

    ensure_freight_recommendation(freight, frete_id)

    recommendation = freight.get("recomendacao") or {}

    log.info(
        "Freight %s | carrier=%s | alternatives=%s | corporate_carriers=%s",
        frete_id,
        recommendation.get("transportadora"),
        len(recommendation.get("alternativas") or []),
        len(recommendation.get("outras_transportadoras") or []),
    )

    view_data["transportadoras_negociacao"] = (
    listar_transportadoras_negociacao(frete_id)
    )

    safe_view_data = {
        key: json_safe(value)
        for key, value in view_data.items()
    }

    return render_template(
        "freight-details.html",
        **safe_view_data,
    )

