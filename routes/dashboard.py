from flask import Blueprint, render_template

from analytics.kpis import (
    obter_kpis,
    obter_evolucao_mensal,
    obter_top_transportadoras,
    obter_performance_estado
)

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
def dashboard():

    kpis = obter_kpis()

    evolucao = obter_evolucao_mensal()

    top_transportadoras = obter_top_transportadoras()

    performance_estado = obter_performance_estado()



    return render_template(
        "dashboard.html",
        kpis=kpis,
        evolucao=evolucao,
        top_transportadoras=top_transportadoras,
        performance_estado=performance_estado
    )