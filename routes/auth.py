
import secrets

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    abort,
)

from flask_login import (
    login_user,
    logout_user,
    current_user,
    login_required,
)

from services.user_repository import authenticate_user


auth_bp = Blueprint("auth", __name__)


def csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)

    return session["_csrf_token"]


def csrf_is_valid():
    """Confere o token da sessão contra o enviado pelo navegador.

    Aceita o campo de formulário `csrf_token` ou o cabeçalho `X-CSRF-Token`
    (usado pelas chamadas fetch; ver static/js/csrf.js).
    """
    expected = session.get("_csrf_token", "")
    received = (
        request.headers.get("X-CSRF-Token")
        or request.form.get("csrf_token", "")
    )

    return bool(expected) and secrets.compare_digest(expected, received)


def validate_csrf():
    if not csrf_is_valid():
        abort(400)


def user_home(user):
    if user.role == "carrier":
        return "/"

    return url_for("fretes.fretes")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if current_user.is_authenticated:
        return redirect(user_home(current_user))

    if request.method == "POST":

        validate_csrf()

        email = request.form.get("email", "")
        password = request.form.get("password", "")

        user = authenticate_user(email, password)

        if not user:
            flash("E-mail ou senha inválidos.", "error")

            return render_template(
                "login.html",
                csrf_token=csrf_token(),
            ), 401

        session.clear()

        login_user(user)

        return redirect(user_home(user))

    return render_template(
        "login.html",
        csrf_token=csrf_token(),
    )


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():

    validate_csrf()

    logout_user()
    session.clear()

    return redirect(url_for("auth.login"))
