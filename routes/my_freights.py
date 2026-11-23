import logging

from flask import render_template, Blueprint
from flask_login import login_required, current_user

log = logging.getLogger(__name__)

carrier_bp = Blueprint("carrier", __name__)

@carrier_bp.route("/meus-fretes", methods=["GET"])
@login_required
def meus_fretes():
    return render_template("my-freights.html")