import sqlite3
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user
from routes.auth import validate_csrf
from services.user_repository import list_users, save_user
from services import plant_repository as plants_repo

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.before_request
def protect():
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)

@admin_bp.route("/")
def index():
    return render_template("admin/index.html")

@admin_bp.route('/users', methods=['GET','POST'])
def users():
    if request.method == 'POST':
        validate_csrf()
        try:
            uid = int(request.form['user_id']) if request.form.get('user_id') else None
            if uid == current_user.id and (request.form.get('profile') != 'admin' or not request.form.get('active')):
                raise ValueError('Você não pode remover seu próprio acesso administrativo.')
            save_user(request.form.get('name',''), request.form.get('email',''), request.form.get('password',''), request.form.get('profile',''), request.form.get('carrier',''), request.form.getlist('plants'), bool(request.form.get('active')), uid)
            flash('Usuário salvo.')
        except (ValueError, sqlite3.IntegrityError) as exc:
            flash('Não foi possível salvar: ' + ('E-mail já cadastrado.' if isinstance(exc, sqlite3.IntegrityError) else str(exc)))
        return redirect(url_for('admin.users'))
    users = list_users()
    selected = next((u for u in users if str(u.id)==request.args.get('edit')), None)
    return render_template('admin/users.html', users=users, selected=selected, plants=plants_repo.list_plants())


# ==========================================
# PLANTAS
# ==========================================
def _plants_page(**extra):
    plants = plants_repo.list_plants()
    summary = {
        'total': len(plants),
        'validated': sum(1 for p in plants if p['validation_status'] == plants_repo.STATUS_VALIDATED),
        'pending': sum(1 for p in plants if p['validation_status'] != plants_repo.STATUS_VALIDATED),
        'inactive': sum(1 for p in plants if not p['active']),
    }
    return render_template('admin/plants.html', plants=plants, summary=summary,
                           ufs=plants_repo.UFS, statuses=plants_repo.VALID_STATUSES, **extra)


@admin_bp.route('/plants', methods=['GET', 'POST'])
def plants():
    if request.method == 'POST':
        validate_csrf()
        editing = request.form.get('editing') == '1'
        form = request.form
        try:
            plants_repo.save_plant(
                form.get('code', ''), form.get('name', ''), form.get('zip_code', ''),
                form.get('city', ''), form.get('state', ''),
                active=bool(form.get('active')),
                validation_status=form.get('validation_status', ''),
                notes=form.get('notes', ''),
                allow_update=editing,
            )
        except ValueError as exc:
            # Reabre o formulário com o que foi digitado, em vez de perder os dados.
            return _plants_page(selected=dict(form), editing=editing, error=str(exc)), 400
        flash('Planta salva.')
        return redirect(url_for('admin.plants'))

    selected, editing = None, False
    if request.args.get('edit'):
        selected = plants_repo.get_plant(request.args['edit'])
        editing = selected is not None
        if not editing:
            abort(404)
    elif request.args.get('new') == '1':
        selected = {'active': 1, 'validation_status': plants_repo.STATUS_PENDING}
    return _plants_page(selected=selected, editing=editing, error=None)


@admin_bp.route('/plants/<code>/toggle', methods=['POST'])
def toggle_plant(code):
    validate_csrf()
    active = request.form.get('active') == '1'
    if plants_repo.toggle_plant(code, active):
        flash('Planta ativada.' if active else 'Planta inativada.')
    else:
        flash('Planta não encontrada.')
    return redirect(url_for('admin.plants'))



# ==========================================
# PLANTAS
# ==========================================
@admin_bp.route('/costs', methods=['GET', 'POST'])
def costs():
    pass