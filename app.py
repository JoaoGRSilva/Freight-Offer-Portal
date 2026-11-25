import os
from dotenv import load_dotenv
from flask import Flask, request, redirect, url_for, jsonify, abort
from flask_login import LoginManager, current_user
from routes.freight_offers import home_bp
from routes.dashboard import dashboard_bp
from routes.freight_board import fretes_bp
from routes.new_shipment import nova_carga_bp
from routes.my_freights import carrier_bp
from routes.auth import auth_bp, csrf_token, csrf_is_valid
from routes.admin import admin_bp
from services.freight_repository import inicializar_banco
from services.user_repository import initialize_users, get_user
from services.plant_repository import seed_plants_from_config
from services.access_control import require_freight_access

load_dotenv()
inicializar_banco()
initialize_users()
seed_plants_from_config()  # só popula se a tabela `plants` estiver vazia
app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["EXPLAIN_TEMPLATE_LOADING"] = True

app.secret_key = os.environ['FLASK_SECRET_KEY']
app.config.update(MAX_CONTENT_LENGTH=200*1024*1024, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'
@login_manager.user_loader
def load_user(user_id):
    return get_user(user_id)
for bp in (auth_bp, home_bp, dashboard_bp, fretes_bp, nova_carga_bp, admin_bp, carrier_bp):
    app.register_blueprint(bp)
@app.context_processor
def inject_auth_context():
    return {'auth_csrf_token': csrf_token}
@app.before_request
def protect_routes():
    endpoint = request.endpoint
    if endpoint in ('static','auth.login',None):
        return
    if not current_user.is_authenticated:
        if request.path.startswith('/api/') or request.method not in ('GET','HEAD'):
            return jsonify(sucesso=False,mensagem='Autenticação necessária.'),401
        return redirect(url_for('auth.login'))
    # CSRF: toda requisição que altera dados precisa do token da sessão.
    if request.method not in ('GET', 'HEAD', 'OPTIONS') and not csrf_is_valid():
        msg = 'Sessão expirada ou requisição inválida. Recarregue a página e tente novamente.'
        if (request.path.startswith('/api/') or request.is_json
                or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                or request.accept_mimetypes.best == 'application/json'):
            return jsonify(sucesso=False, ok=False, mensagem=msg, erro=msg), 400
        abort(400, description=msg)
    
    if endpoint == 'auth.logout':
        return
    if current_user.role == 'carrier':

        # Home pública do portal da transportadora.
        if endpoint == 'home.home' and request.method in ('GET', 'HEAD'):
            return

        # Envio de propostas pela transportadora autenticada.
        if endpoint == 'home.enviar_proposta' and request.method == 'POST':
            return

        # Telas exclusivas da transportadora.
        if request.blueprint == 'carrier':
            return

        abort(403)
    if current_user.role != 'internal' or request.blueprint == 'carrier':
        abort(403)
    if request.blueprint in ('dashboard','admin') and not current_user.is_admin:
        abort(403)
    if endpoint == 'home.enviar_proposta':
        abort(403)
    if endpoint == 'nova-carga.limpar' and not current_user.is_admin:
        abort(403)

    if 'frete_id' in (request.view_args or {}):
        require_freight_access(request.view_args['frete_id'])


if __name__ == "__main__":
    app.run(debug=True)