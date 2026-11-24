from services.access_control import authorized_plants, plant_code
from flask_login import current_user
import json
import logging
import math
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    url_for,
    jsonify,
)
from werkzeug.utils import secure_filename

from analytics import config as C
from analytics.truck import (
    recomendar_caminhao,
    consumo_tabela,
)
from services.freight_processor import process_fretes
from services.freight_cost import calcular_custos
from services.carrier_recommendation import recomendar
from services.location_enrichment import enriquecer_localizacoes
from services.postal_code_history import preencher_cep
from services.freight_repository import (
    salvar_fretes,
    chave_do_frete,
    obter_id_por_chave,
    registrar_proposta,
    aceitar_proposta,
    confirmar_sap,
    listar_propostas,
    obter_fechamento,
    obter_estado_frete,
    iniciar_negociacao,
    inicializar_banco,
    publicar_oferta,
    retirar_oferta,
    atualizar_dados_carga,
    concluir_frete,
    obter_frete,
    listar_fretes_preparacao,
    delete_base
)

# ==========================================
# CONFIGURAÇÃO DA ROTA
# ==========================================

log = logging.getLogger(__name__)

nova_carga_bp = Blueprint("nova-carga", __name__)

# =====================================
# CONFIGURAÇÕES DE UPLOAD
# =====================================
EXTENSOES_ACEITAS = {
    ".csv",
    ".xlsx",
    ".parquet",
}

PASTA_UPLOAD = Path("data/entrada")

# =====================================
# CÁLCULO
# =====================================
CALCULO_VAZIO = {
    "antt": None,
    "mercado": None,
    "distancia_total_km": None,
    "litros_totais": None,
    "custo_combustivel": None,
}

# Categoria de carga e pavimento usados na tabela de consumo.
# valores que existem em consumo_tabela. Sem isso, usa o primeiro disponível
CATEGORIA_PADRAO = getattr(C, "DEFAULT_CATEGORY", None)
PAVIMENTO_PADRAO = getattr(C, "DEFAULT_PAVEMENT", None)


def _calcular(frete, trechos=None):
    """
    Calcula os custos de referência do frete.

    Se houver algum problema no cálculo, retorna um cálculo vazio
    para que um erro em um frete não derrube a página inteira.
    """
    try:
        return calcular_custos(
            uf=frete["uf"],
            peso_kg=frete["peso_kg"],
            eixos=frete["eixos"],
            categoria=frete["categoria"],
            trechos=trechos or frete["trechos"],
        )
    except Exception:
        log.warning(
            "Falha ao calcular custos do frete %s",
            frete.get("id"),
            exc_info=True,
        )
        return dict(CALCULO_VAZIO)

def _custos_do_frete(f):
    """
    Custos de referência (ANTT, mercado, litros, combustível).

    1) Frete que já traz 'trechos' e 'eixos': cálculo original.
    2) Demais: eixos pelo peso (recomendar_caminhao) e trechos montados
       com o km de cada trecho da rota (f['km_trechos']).
    """
    if f.get("trechos") and f.get("eixos"):
        return _calcular(f)

    km_trechos = f.get("km_trechos")

    if not km_trechos:
        return dict(CALCULO_VAZIO)

    try:
        caminhao = recomendar_caminhao(f.get("peso_kg")) or {}
    except Exception:
        log.warning("Falha ao recomendar caminhão", exc_info=True)
        return dict(CALCULO_VAZIO)

    eixos = caminhao.get("eixos")

    if not eixos or caminhao.get("excede"):
        return dict(CALCULO_VAZIO)


    categoria = CATEGORIA_PADRAO
    pavimento = PAVIMENTO_PADRAO

    if categoria is None:
        return dict(CALCULO_VAZIO)

    f["eixos"] = eixos
    f["categoria"] = categoria

    trechos_custo = [
        {"distancia_km": km, "pavimento": pavimento}
        for km in km_trechos
    ]

    return _calcular(f, trechos=trechos_custo)


def _json_safe(o):
    """Converte NaN, numpy, Timestamp e NA para tipos que o tojson aceita."""
    if isinstance(o, dict):
        return {k: _json_safe(v) for k, v in o.items()}

    if isinstance(o, (list, tuple)):
        return [_json_safe(v) for v in o]

    if o is pd.NA or o is None:
        return None

    if isinstance(o, (np.integer,)):
        return int(o)

    if isinstance(o, (np.floating, float)):
        return None if math.isnan(o) else float(o)

    if isinstance(o, pd.Timestamp):
        return o.strftime("%Y-%m-%d")

    return o


def _para_card(frete, i):
    """Traduz o frete do ETL para o formato que o template lê."""
    transf = frete.get("transfer_planta")

    return {
        **frete,
        "id": i,  # inteiro, o onclick usa sem aspas
        "pedido": ", ".join(frete.get("pedidos", [])),
        "origem": frete["planta"]["cidade"],
        "transfer": transf["cidade"] if transf else None,
        "calculo": frete.get("calculo", {}),
    }


def _recomendar_todos(fretes):
    """Calcula CEP, custos e recomendação uma única vez por frete."""
    com_sugestao = 0
    tempos = {"cep": 0.0, "custos": 0.0, "recomendacao": 0.0}

    for i, f in enumerate(fretes, start=1):
        f["id"] = i

        inicio = time.perf_counter()
        preencher_cep(f)
        tempos["cep"] += time.perf_counter() - inicio

        inicio = time.perf_counter()
        calculo = _custos_do_frete(f)
        tempos["custos"] += time.perf_counter() - inicio

        # Aproveita a distância estimada pelo enriquecimento.
        if calculo.get("distancia_total_km") is None:
            calculo["distancia_total_km"] = f.get("km_estimado")
        f["calculo"] = calculo

        inicio = time.perf_counter()
        try:
            f["recomendacao"] = recomendar(f, i, calculo=calculo)
        except Exception:
            log.exception("Recomendação falhou no frete %s", f.get("num"))
            f["recomendacao"] = None
        finally:
            tempos["recomendacao"] += time.perf_counter() - inicio

        r = f["recomendacao"]
        if r and r.get("transportadora") not in (None, "—"):
            com_sugestao += 1

    logging.info(
        f"[PERFORMANCE] CEP: {tempos['cep']:.2f}s | "
        f"Custos: {tempos['custos']:.2f}s | "
        f"Recomendação: {tempos['recomendacao']:.2f}s "
        f"({len(fretes)} fretes)",
        flush=True,
    )
    return com_sugestao


@nova_carga_bp.route("/nova-carga")
def nova_carga():

    inicializar_banco()

    fretes = listar_fretes_preparacao(authorized_plants())

    for indice, frete in enumerate(fretes, start=1):
        # ID temporário utilizado pelos componentes JavaScript.
        # O ID persistente continua em db_id.
        frete["id"] = indice

        frete["propostas"] = listar_propostas(frete["db_id"])
        frete["fechamento"] = obter_fechamento(frete["db_id"])

    return render_template(
        "new-shipment.html",
        fretes=fretes
    )

# =====================================
# UPLOAD DO HISTÓRICO
# =====================================
@nova_carga_bp.route("/nova-carga/upload", methods=["POST"])
def upload():
    """Recebe a base, processa uma vez e persiste os fretes."""
    inicio_total = time.perf_counter()
    arquivo = request.files.get("basedefretes")

    if not arquivo or not arquivo.filename:
        flash("Selecione um arquivo.")
        return redirect(url_for("nova-carga.nova_carga"))

    from analytics.plants import extrair_codigo
    from services.plant_repository import get_usable_plant
    codigo_planta = extrair_codigo(arquivo.filename)
    if not codigo_planta:
        flash("Não encontrei o código de uma planta cadastrada no nome do arquivo "
              "(ex.: fretes_1304.xlsx).")
        return redirect(url_for("nova-carga.nova_carga"))
    if not current_user.can_access_plant(codigo_planta):
        flash("Planta do arquivo não autorizada.")
        return redirect(url_for("nova-carga.nova_carga"))
    if not get_usable_plant(codigo_planta):
        flash(f"A planta {codigo_planta} está inativa ou pendente de validação. "
              "Peça ao administrador para ativá-la ou validá-la.")
        return redirect(url_for("nova-carga.nova_carga"))
    nome_seguro = secure_filename(arquivo.filename)
    extensao = Path(nome_seguro).suffix.lower()

    if extensao not in EXTENSOES_ACEITAS:
        flash("Formato não aceito. Use CSV, XLSX ou Parquet.")
        return redirect(url_for("nova-carga.nova_carga"))

    PASTA_UPLOAD.mkdir(parents=True, exist_ok=True)
    nome_arquivo = f"historico_{datetime.now():%Y%m%d_%H%M%S_%f}{extensao}"
    destino = PASTA_UPLOAD / nome_arquivo

    try:
        arquivo.save(destino)
        log.info("Arquivo de histórico recebido: %s", destino)

        # O arquivo salvo é usado como fonte para evitar ler o stream já consumido.
        t0 = time.perf_counter()
        arquivo.stream.seek(0)
        resultado = process_fretes(arquivo)
        fretes = resultado.get("fretes", [])
        if any(not current_user.can_access_plant(plant_code(f)) for f in fretes):
            destino.unlink(missing_ok=True)
            flash("Arquivo rejeitado: contém fretes de plantas não autorizadas.")
            return redirect(url_for("nova-carga.nova_carga"))
        log.info(
            f"[PERFORMANCE] ETL: {time.perf_counter() - t0:.2f}s | "
            f"{len(fretes)} fretes",
            flush=True,
        )

        t0 = time.perf_counter()
        fretes = enriquecer_localizacoes(fretes)
        log.info(
            f"[PERFORMANCE] Localizações: {time.perf_counter() - t0:.2f}s",
            flush=True,
        )

        t0 = time.perf_counter()
        com_sugestao = _recomendar_todos(fretes)
        log.info(
            f"[PERFORMANCE] Recomendações + custos + CEP: "
            f"{time.perf_counter() - t0:.2f}s",
            flush=True,
        )

        t0 = time.perf_counter()
        cards = _json_safe([
            _para_card(f, i) for i, f in enumerate(fretes, start=1)
        ])

        for card in cards:
            card.setdefault("tipo_carga", "batida")
            card.setdefault("peso_liquido_kg", None)
            card.setdefault("valor_inicial_negociacao", None)
            card.setdefault("comentarios_carga", "")

        log.info(
            f"[PERFORMANCE] Preparação JSON: {time.perf_counter() - t0:.2f}s",
            flush=True,
        )

        t0 = time.perf_counter()
        inicializar_banco()
        resultado_db = salvar_fretes(cards)

        for card in cards:
            card["db_id"] = obter_id_por_chave(chave_do_frete(card))

        log.info(
            f"[PERFORMANCE] SQLite: {time.perf_counter() - t0:.2f}s | "
            f"{resultado_db['inseridos']} inseridos, "
            f"{resultado_db['atualizados']} atualizados",
            flush=True,
        )

        com_localizacao = sum(
            1 for f in fretes
            if (f.get("localizacao_destino") or {}).get("lat") is not None
            and (f.get("localizacao_destino") or {}).get("lon") is not None
        )
        com_km = sum(1 for f in fretes if f.get("km_estimado") is not None)

        log.info(
            f"[UPLOAD] {len(fretes)} processados, "
            f"{len(resultado.get('ignorados', []))} ignorados, "
            f"{len(resultado.get('erros', []))} erros",
            flush=True,
        )
        flash(
            f"{len(fretes)} fretes processados. "
            f"{com_localizacao} com localização, {com_km} com distância, "
            f"{com_sugestao} com sugestão de transportadora."
        )

    except Exception as exc:
        log.exception("Erro ao processar ou enriquecer os fretes")
        flash(f"Ocorreu um erro durante o processamento: {exc}")

    finally:
        log.info(
            f"[PERFORMANCE] TOTAL: {time.perf_counter() - inicio_total:.2f}s",
            flush=True,
        )

    return redirect(url_for("nova-carga.nova_carga"))


@nova_carga_bp.route("/nova-carga/limpar", methods=["POST"])
def limpar():
    delete_base()
    flash("Fretes pendentes removidos.")
    return redirect(url_for("nova-carga.nova_carga"))


# ==========================================
# NOVA CARGA — NEGOCIAÇÃO
# ==========================================
@nova_carga_bp.route(
    "/nova-carga/fretes/<int:frete_id>/propostas",
    methods=["POST"],
)
def nova_proposta(frete_id):
    """
    Registra uma proposta de transportadora.

    Requisição AJAX:
        Retorna JSON com a confirmação e o histórico.

    Formulário tradicional:
        Mantém o comportamento de flash + redirect.
    """
    ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    try:
        # =====================================
        # TRANSPORTADORA
        # =====================================
        transportadora = request.form.get("transportadora", "").strip()

        if not transportadora:
            raise ValueError("Informe a transportadora.")

        # =====================================
        # VALOR DA PROPOSTA
        # =====================================
        valor_texto = request.form.get("valor", "").strip()
        valor = float(valor_texto.replace(",", "."))

        if not (math.isfinite(valor) and 0 < valor < 1_000_000_000):
            raise ValueError("Informe um valor válido.")

        # =====================================
        # PRAZO
        # =====================================
        prazo_texto = request.form.get("prazo_dias", "").strip()
        prazo = int(prazo_texto) if prazo_texto else None

        if prazo is not None and not 0 <= prazo <= 365:
            raise ValueError("Prazo inválido.")

        # =====================================
        # OBSERVAÇÕES
        # =====================================
        observacoes = request.form.get("observacoes", "").strip()

        # =====================================
        # REGISTRAR NO BANCO
        # =====================================
        proposta_id = registrar_proposta(
            frete_id=frete_id,
            transportadora=transportadora,
            valor=valor,
            prazo_dias=prazo,
            observacoes=observacoes,
        )

        mensagem = "Proposta registrada com sucesso."

        # =====================================
        # RETORNO PARA O MODAL
        # =====================================
        if ajax:
            return jsonify({
                "sucesso": True,
                "mensagem": mensagem,
                "proposta_id": proposta_id,
                "propostas": listar_propostas(frete_id),
            }), 201

        flash(mensagem)

    except (ValueError, OverflowError) as erro:
        mensagem = f"Erro ao registrar proposta: {erro}"

        if ajax:
            return jsonify({
                "sucesso": False,
                "mensagem": mensagem,
            }), 400

        flash(mensagem)

    return redirect(url_for("nova-carga.nova_carga"))


@nova_carga_bp.route(
    "/nova-carga/fretes/<int:frete_id>/propostas/<int:proposta_id>/aceitar",
    methods=["POST"],
)
def aceitar_cotacao(frete_id, proposta_id):
    ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    try:
        aceitar_proposta(frete_id, proposta_id)
        mensagem = "Proposta aceita. Aguardando confirmação SAP."

        if ajax:
            return jsonify({"sucesso": True, "mensagem": mensagem})

        flash(mensagem)

    except ValueError as erro:
        mensagem = str(erro)
        if ajax:
            return jsonify({"sucesso": False, "mensagem": mensagem}), 400
        flash(mensagem)

    except Exception:
        log.exception(
            "Erro ao aceitar proposta %s do frete %s",
            proposta_id,
            frete_id,
        )
        mensagem = "Erro interno ao aceitar a proposta."
        if ajax:
            return jsonify({"sucesso": False, "mensagem": mensagem}), 500
        flash(mensagem)

    return redirect(url_for("nova-carga.nova_carga"))


@nova_carga_bp.route(
    "/nova-carga/fretes/<int:frete_id>/confirmar-sap",
    methods=["POST"],
)
def confirmar_frete_sap(frete_id):
    ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    referencia = request.form.get("referencia_sap", "").strip()

    try:
        if not referencia:
            raise ValueError("Informe a referência SAP")

        confirmar_sap(frete_id, referencia)
        mensagem = (
            "Contratação confirmada no SAP. "
            "Status atualizado para Cotação aceita."
        )

        if ajax:
            return jsonify({"sucesso": True, "mensagem": mensagem})

        flash(mensagem)

    except ValueError as erro:
        mensagem = str(erro)
        if ajax:
            return jsonify({"sucesso": False, "mensagem": mensagem}), 400
        flash(mensagem)

    except Exception:
        log.exception("Erro ao confirmar contratação SAP do frete %s", frete_id)
        mensagem = "Erro interno ao confirmar a contratação no SAP."
        if ajax:
            return jsonify({"sucesso": False, "mensagem": mensagem}), 500
        flash(mensagem)

    return redirect(url_for("nova-carga.nova_carga"))


@nova_carga_bp.route(
    "/api/nova-carga/fretes/<int:frete_id>/negociacao",
    methods=["POST"],
)
def iniciar_negociacao_frete(frete_id):
    dados = request.get_json(silent=True) or {}
    transportadora = dados.get("transportadora")

    try:
        iniciar_negociacao(
            frete_id=frete_id,
            transportadora=transportadora,
        )
    except ValueError as erro:
        return jsonify({
            "sucesso": False,
            "erro": str(erro),
        }), 400

    return jsonify({
        "sucesso": True,
        "status": "negociacao",
        "transportadora": transportadora,
    })


@nova_carga_bp.route("/mesa/fretes/<int:frete_id>/publicar", methods=["POST"])
def publicar_frete(frete_id):
    publicado = publicar_oferta(frete_id)

    if not publicado:
        return jsonify({
            "sucesso": False,
            "mensagem": "Frete não encontrado ou indisponível para publicação.",
        }), 409

    return jsonify({
        "sucesso": True,
        "mensagem": "Frete publicado com sucesso!",
        "status": "em_oferta",
    })


@nova_carga_bp.route(
    "/mesa/fretes/<int:frete_id>/retirar-oferta",
    methods=["POST"],
)
def retirar_oferta_frete(frete_id):
    if not retirar_oferta(frete_id):
        return jsonify({
            "sucesso": False,
            "mensagem": "Só é possível retirar uma oferta publicada.",
        }), 409

    return jsonify({
        "sucesso": True,
        "status": "em_preparacao",
        "mensagem": "Oferta retirada; carga editável novamente.",
    })


@nova_carga_bp.route(
    "/nova-carga/fretes/<int:frete_id>/dados",
    methods=["PATCH"],
)

@nova_carga_bp.route(
    "/nova-carga/fretes/<int:frete_id>/dados",
    methods=["PATCH"]
)
def editar_dados_carga(frete_id):
    """
    Atualiza os dados da carga.

    Retorna JSON para o modal atualizar os
    campos e apresentar a confirmação.
    """

    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return jsonify({
            "sucesso": False,
            "mensagem": "Envie um JSON válido."
        }), 400

    tipo_carga = dados.get(
        "tipo_carga",
        "batida"
    )

    peso_liquido_kg = dados.get(
        "peso_liquido_kg"
    )

    valor_inicial_negociacao = dados.get(
        "valor_inicial_negociacao"
    )

    comentarios_carga = dados.get(
        "comentarios_carga",
        ""
    )

    try:
        atualizados = atualizar_dados_carga(
            frete_id=frete_id,
            tipo_carga=tipo_carga,
            peso_liquido_kg=peso_liquido_kg,
            valor_inicial_negociacao=valor_inicial_negociacao,
            comentarios_carga=comentarios_carga
        )

    except ValueError as erro:
        return jsonify({
            "sucesso": False,
            "mensagem": str(erro)
        }), 400

    return jsonify({
        "sucesso": True,
        "mensagem": "Dados da carga salvos com sucesso.",
        "tipo_carga": atualizados["tipo_carga"],
        "peso_liquido_kg": atualizados["peso_liquido_kg"],
        "valor_inicial_negociacao": (
            atualizados["valor_inicial_negociacao"]
        ),
        "comentarios_carga": (
            atualizados["comentarios_carga"]
        )
    })



@nova_carga_bp.route(
    "/api/nova-carga/fretes/<int:frete_id>/concluir",
    methods=["POST"]
)
def concluir_frete_api(frete_id):

    try:
        concluir_frete(frete_id)

        return jsonify({
            "sucesso": True,
            "status": "concluido",
            "mensagem": "Frete concluído com sucesso."
        })

    except ValueError as erro:
        return jsonify({
            "sucesso": False,
            "mensagem": str(erro)
        }), 400
