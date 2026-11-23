
import logging

from flask import render_template, Blueprint
from flask_login import login_required, current_user
from services.freight_repository import list_propose_send

log = logging.getLogger(__name__)

carrier_bp = Blueprint("carrier", __name__)


@carrier_bp.route("/meus-fretes", methods=["GET"])
@login_required
def meus_fretes():

    fretes = list_propose_send(current_user.carrier_name)

    print(fretes)

    return render_template(
        "my-freights.html",
        fretes=fretes
    )
