import json
import math
import sqlite3
from services.db import connect
import hashlib
from pathlib import Path
from datetime import datetime, timezone

STATUS_VALIDOS = {
    "em_preparacao",
    "em_oferta",
    "negociacao",
    "cotacao_aceita",
    "concluido",
    "cancelado",
}


def inicializar_banco():
    with connect("fretes") as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fretes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chave_origem TEXT NOT NULL UNIQUE,
                numero_frete TEXT,
                origem TEXT,
                destino TEXT,
                peso_kg REAL,
                valor REAL,
                data_carga TEXT,
                transportadora_recomendada TEXT,
                transportadora_escolhida TEXT,
                status TEXT NOT NULL DEFAULT 'em_preparacao',
                dados_json TEXT NOT NULL,
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS fretes_historico_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                frete_id INTEGER NOT NULL,
                status_anterior TEXT,
                status_novo TEXT NOT NULL,
                alterado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (frete_id) REFERENCES fretes(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS fretes_propostas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                frete_id INTEGER NOT NULL,
                transportadora TEXT NOT NULL,
                valor REAL NOT NULL CHECK (valor >= 0),
                prazo_dias INTEGER,
                observacoes TEXT,
                aceita INTEGER NOT NULL DEFAULT 0,
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (frete_id) REFERENCES fretes(id)
            )
        """)

                # ==========================================
        # MIGRAÇÃO — NEGOCIAÇÃO DE PROPOSTAS
        # ==========================================

        # Verifica quais colunas já existem
        colunas_propostas = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(fretes_propostas)"
            ).fetchall()
        }

        # Status individual da negociação
        if "status_negociacao" not in colunas_propostas:
            conn.execute("""
                ALTER TABLE fretes_propostas
                ADD COLUMN status_negociacao TEXT
                NOT NULL DEFAULT 'aguardando_operador'
            """)

        # Data da última atualização
        if "atualizado_em" not in colunas_propostas:
            conn.execute("""
                ALTER TABLE fretes_propostas
                ADD COLUMN atualizado_em TEXT
            """)

            conn.execute("""
                UPDATE fretes_propostas
                SET atualizado_em = criado_em
                WHERE atualizado_em IS NULL
            """)

        # Propostas já aceitas precisam continuar aceitas
        conn.execute("""
            UPDATE fretes_propostas
            SET status_negociacao = 'aceita'
            WHERE aceita = 1
        """)

        # ==========================================
        # HISTÓRICO DA NEGOCIAÇÃO
        # ==========================================

        conn.execute("""
            CREATE TABLE IF NOT EXISTS fretes_negociacao_historico (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                proposta_id INTEGER NOT NULL,

                autor TEXT NOT NULL,
                tipo TEXT NOT NULL,

                valor REAL,
                prazo_dias INTEGER,
                observacoes TEXT,

                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (proposta_id)
                    REFERENCES fretes_propostas(id)
            )
        """)

        # Índice para consultar rapidamente o histórico
        conn.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_negociacao_historico_proposta
            ON fretes_negociacao_historico(proposta_id, criado_em)
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS fretes_fechamentos (
                frete_id INTEGER PRIMARY KEY,
                proposta_id INTEGER NOT NULL,
                referencia_sap TEXT NOT NULL,
                confirmado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (frete_id) REFERENCES fretes(id),
                FOREIGN KEY (proposta_id) REFERENCES fretes_propostas(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS fretes_transportadoras_negociacao (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                frete_id INTEGER NOT NULL,
                transportadora TEXT NOT NULL COLLATE NOCASE,
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                UNIQUE (frete_id, transportadora),

                FOREIGN KEY (frete_id) REFERENCES fretes(id)
            )
        """)

        # Migrate existing negotiation participants.
        conn.execute("""
            INSERT OR IGNORE INTO fretes_transportadoras_negociacao (
                frete_id,
                transportadora
            )
            SELECT id, TRIM(transportadora_escolhida)
            FROM fretes
            WHERE status = 'negociacao'
            AND transportadora_escolhida IS NOT NULL
            AND TRIM(transportadora_escolhida) NOT IN ('', '—')
        """)

        # Preserve carriers that have already submitted proposals.
        conn.execute("""
            INSERT OR IGNORE INTO fretes_transportadoras_negociacao (
                frete_id,
                transportadora
            )
            SELECT DISTINCT frete_id, TRIM(transportadora)
            FROM fretes_propostas
            WHERE TRIM(transportadora) NOT IN ('', '—')
        """)


def chave_do_frete(frete):
    """
    Chave provisória para o MVP.

    Usa número do frete e planta quando disponíveis.
    Se não houver número, usa dados básicos da carga.
    """
    numero = str(frete.get("num") or "").strip()
    planta = frete.get("planta") or {}

    codigo_planta = (
        planta.get("codigo")
        or planta.get("id")
        or ""
    ) if isinstance(planta, dict) else str(planta)

    if numero:
        base = f"numero:{codigo_planta}:{numero}"
    else:
        pedidos = frete.get("pedidos") or frete.get("pedido") or []

        if isinstance(pedidos, list):
            pedidos = sorted(str(p) for p in pedidos)

        base = json.dumps({
            "planta": codigo_planta,
            "pedidos": pedidos,
            "origem": frete.get("origem"),
            "destino": frete.get("destino"),
            "data_carga": frete.get("data_carga"),
        }, sort_keys=True, ensure_ascii=False)

    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def salvar_fretes(fretes):
    """
    Insere fretes novos e atualiza dados dos existentes.

    Preserva status e transportadora escolhida.
    """
    inseridos = 0
    atualizados = 0

    with connect("fretes") as conn:
        for frete in fretes:
            status_inicial = frete.get("status_inicial", "em_preparacao")

            if status_inicial not in ("em_preparacao", "cotacao_aceita"):
                status_inicial = "em_preparacao"

            chave = chave_do_frete(frete)
            recomendacao = frete.get("recomendacao") or {}
            calculo = frete.get("calculo") or {}

            numero = str(frete.get("num") or "")
            origem = str(frete.get("origem") or "")
            destino = str(frete.get("destino") or "")
            peso = frete.get("peso_kg")
            valor = calculo.get("mercado")
            data = frete.get("data_carga")
            transportadora = recomendacao.get("transportadora")

            dados = json.dumps(
                frete,
                ensure_ascii=False,
                allow_nan=False,
            )

            existente = conn.execute(
                "SELECT id, dados_json FROM fretes WHERE chave_origem = ?",
                (chave,),
            ).fetchone()

            if existente:
                # Preserve operator-entered fields when importing the same freight again.
                try:
                    dados_anteriores = json.loads(existente["dados_json"] or "{}")
                except (ValueError, TypeError):
                    dados_anteriores = {}

                for campo in (
                    "tipo_carga",
                    "peso_liquido_kg",
                    "valor_inicial_negociacao",
                    "comentarios_carga",
                ):
                    if campo in dados_anteriores:
                        frete[campo] = dados_anteriores[campo]

                dados = json.dumps(frete, ensure_ascii=False, allow_nan=False)

                conn.execute("""
                    UPDATE fretes
                    SET numero_frete = ?,
                        origem = ?,
                        destino = ?,
                        peso_kg = ?,
                        valor = ?,
                        data_carga = ?,
                        transportadora_recomendada = ?,
                        dados_json = ?,
                        atualizado_em = CURRENT_TIMESTAMP
                    WHERE chave_origem = ?
                """, (
                    numero, origem, destino, peso, valor,
                    data, transportadora, dados, chave,
                ))

                atualizados += 1

            else:
                cursor = conn.execute("""
                    INSERT INTO fretes (
                        chave_origem,
                        numero_frete,
                        origem,
                        destino,
                        peso_kg,
                        valor,
                        data_carga,
                        transportadora_recomendada,
                        dados_json,
                        status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    chave,
                    numero,
                    origem,
                    destino,
                    peso,
                    valor,
                    data,
                    transportadora,
                    dados,
                    status_inicial,
                ))

                conn.execute("""
                    INSERT INTO fretes_historico_status (
                        frete_id,
                        status_anterior,
                        status_novo
                    )
                    VALUES (?, NULL, ?)
                """, (cursor.lastrowid, status_inicial))

                inseridos += 1

    return {
        "inseridos": inseridos,
        "atualizados": atualizados,
    }


def listar_fretes(plants=None):
    clause, params = plant_scope(plants)
    with connect("fretes") as conn:
        registros = conn.execute(f"""
            SELECT id, numero_frete, origem, destino,
                   peso_kg, valor, data_carga, status,
                   transportadora_recomendada,
                   transportadora_escolhida
            FROM fretes
            WHERE 1=1
            {clause}
            ORDER BY id DESC
        """, params).fetchall()

    return [
        {
            "id": r["id"],
            "num": r["numero_frete"],
            "origem": r["origem"],
            "destino": r["destino"],
            "peso": r["peso_kg"],
            "valor": r["valor"],
            "coleta": r["data_carga"],
            "status": r["status"],
            "transportadora": (
                r["transportadora_escolhida"]
                or r["transportadora_recomendada"]
            ),
        }
        for r in registros
    ]


def atualizar_status(frete_id, novo_status):
    if novo_status not in STATUS_VALIDOS:
        raise ValueError("Status inválido")

    with connect("fretes") as conn:
        registro = conn.execute(
            "SELECT status FROM fretes WHERE id = ?",
            (frete_id,),
        ).fetchone()

        if registro is None:
            return False

        anterior = registro["status"]

        if anterior == novo_status:
            return True

        conn.execute("""
            UPDATE fretes
            SET status = ?,
                atualizado_em = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (novo_status, frete_id))

        conn.execute("""
            INSERT INTO fretes_historico_status
            (frete_id, status_anterior, status_novo)
            VALUES (?, ?, ?)
        """, (frete_id, anterior, novo_status))

    return True


def obter_frete(frete_id):
    with connect("fretes") as conn:
        registro = conn.execute(
            "SELECT * FROM fretes WHERE id = ?",
            (frete_id,),
        ).fetchone()

        if registro is None:
            return None

        frete = dict(registro)
        frete["detalhes"] = json.loads(frete["dados_json"])
        return frete

def listar_fretes_preparacao(plants=None):
    """Recupera os dados completos dos fretes em preparação."""

    clause, params = plant_scope(plants)
    with connect("fretes") as conn:
        registros = conn.execute(f"""
            SELECT id, status, transportadora_escolhida, dados_json
            FROM fretes
            WHERE status = 'em_preparacao'
            {clause}
            ORDER BY id DESC
        """, params).fetchall()

    fretes = []

    for registro in registros:
        frete = json.loads(registro["dados_json"])
        frete["db_id"] = registro["id"]
        frete["status_db"] = registro["status"]
        frete["transportadora_escolhida"] = registro["transportadora_escolhida"]
        fretes.append(frete)

    return fretes

def listar_propostas(frete_id):
    with connect("fretes") as conn:
        registros = conn.execute("""
            SELECT *
            FROM fretes_propostas
            WHERE frete_id = ?
            ORDER BY id DESC
        """, (frete_id,)).fetchall()

        return [dict(r) for r in registros]


def obter_fechamento(frete_id):
    with connect("fretes") as conn:
        registro = conn.execute("""
            SELECT *
            FROM fretes_fechamentos
            WHERE frete_id = ?
        """, (frete_id,)).fetchone()

        return dict(registro) if registro else None


def registrar_proposta(
    frete_id,
    transportadora,
    valor,
    prazo_dias=None,
    observacoes="",
):
    """
    Registra uma proposta no SQLite.

    Permite propostas em:
    - em_oferta: propostas recebidas pelo portal;
    - negociacao: propostas negociadas pela equipe.

    Registrar uma proposta não altera o status do frete.
    """
    transportadora = str(transportadora or "").strip()

    if not transportadora:
        raise ValueError("Transportadora não informada.")

    try:
        valor = float(valor)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Valor da proposta inválido.")

    if not math.isfinite(valor) or valor <= 0:
        raise ValueError("O valor da proposta deve ser positivo.")

    if prazo_dias is not None:
        try:
            prazo_dias = int(prazo_dias)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Prazo inválido.")

        if not 0 <= prazo_dias <= 365:
            raise ValueError("Prazo deve estar entre 0 e 365 dias.")

    observacoes = str(observacoes or "").strip()

    with connect("fretes") as conn:
        frete = conn.execute(
            """
            SELECT status
            FROM fretes
            WHERE id = ?
            """,
            (frete_id,),
        ).fetchone()

        if frete is None:
            raise ValueError("Frete não encontrado.")

        if frete["status"] not in ("em_oferta", "negociacao"):
            raise ValueError(
                "Este frete não está disponível para receber propostas."
            )

        cursor = conn.execute(
            """
            INSERT INTO fretes_propostas (
                frete_id,
                transportadora,
                valor,
                prazo_dias,
                observacoes
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                frete_id,
                transportadora,
                valor,
                prazo_dias,
                observacoes,
            ),
        )

        return cursor.lastrowid


def aceitar_proposta(frete_id, proposta_id):
    with connect("fretes") as conn:
        frete = conn.execute(
            "SELECT status FROM fretes WHERE id = ?",
            (frete_id,),
        ).fetchone()

        if frete is None or frete["status"] != "negociacao":
            raise ValueError("Frete não está em negociação")

        proposta = conn.execute("""
            SELECT id, transportadora
            FROM fretes_propostas
            WHERE id = ? AND frete_id = ?
        """, (proposta_id, frete_id)).fetchone()

        if proposta is None:
            raise ValueError("Proposta não encontrada")

        conn.execute("""
            UPDATE fretes_propostas
            SET aceita = 0
            WHERE frete_id = ?
        """, (frete_id,))

        conn.execute("""
            UPDATE fretes_propostas
            SET aceita = 1
            WHERE id = ?
        """, (proposta_id,))

        conn.execute("""
            UPDATE fretes
            SET transportadora_escolhida = ?,
                atualizado_em = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (proposta["transportadora"], frete_id))


def confirmar_sap(frete_id, referencia_sap):
    with connect("fretes") as conn:
        frete = conn.execute(
            "SELECT status FROM fretes WHERE id = ?",
            (frete_id,),
        ).fetchone()

        if frete is None or frete["status"] != "negociacao":
            raise ValueError("Frete não está em negociação")

        proposta = conn.execute("""
            SELECT id
            FROM fretes_propostas
            WHERE frete_id = ? AND aceita = 1
        """, (frete_id,)).fetchone()

        if proposta is None:
            raise ValueError("Aceite uma proposta primeiro")

        fechamento = conn.execute("""
            SELECT frete_id
            FROM fretes_fechamentos
            WHERE frete_id = ?
        """, (frete_id,)).fetchone()

        if fechamento is not None:
            raise ValueError("Frete já possui fechamento")

        conn.execute("""
            INSERT INTO fretes_fechamentos (
                frete_id, proposta_id, referencia_sap
            )
            VALUES (?, ?, ?)
        """, (frete_id, proposta["id"], referencia_sap))

        conn.execute("""
            UPDATE fretes
            SET status = 'cotacao_aceita',
                atualizado_em = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (frete_id,))

        conn.execute("""
            INSERT INTO fretes_historico_status (
                frete_id, status_anterior, status_novo
            )
            VALUES (?, 'negociacao', 'cotacao_aceita')
        """, (frete_id,))


def obter_id_por_chave(chave):
    with connect("fretes") as conn:
        registro = conn.execute(
            "SELECT id, dados_json FROM fretes WHERE chave_origem = ?",
            (chave,),
        ).fetchone()

    return registro["id"] if registro else None


def obter_estado_frete(frete_id):
    """Retorna o status persistido e a transportadora escolhida."""
    with connect("fretes") as conn:
        registro = conn.execute("""
            SELECT
                id,
                status,
                transportadora_recomendada,
                transportadora_escolhida
            FROM fretes
            WHERE id = ?
        """, (frete_id,)).fetchone()

    return dict(registro) if registro else None



def iniciar_negociacao(frete_id, transportadora):
    """
    Add a carrier to the freight negotiation.

    The first carrier starts the negotiation.
    Additional carriers do not replace previous participants.
    """
    carrier = str(transportadora or "").strip()

    if not carrier or carrier == "—":
        raise ValueError("Selecione uma transportadora válida.")

    with connect("fretes") as conn:
        conn.execute("BEGIN IMMEDIATE")

        freight = conn.execute(
            """
            SELECT status
            FROM fretes
            WHERE id = ?
            """,
            (frete_id,),
        ).fetchone()

        if freight is None:
            raise ValueError("Frete não encontrado.")

        previous_status = freight["status"]

        if previous_status not in (
            "disponivel",
            "em_preparacao",
            "em_oferta",
            "negociacao",
        ):
            raise ValueError(
                "Este frete não permite adicionar transportadoras."
            )

        accepted = conn.execute(
            """
            SELECT 1
            FROM fretes_propostas
            WHERE frete_id = ?
              AND aceita = 1
            LIMIT 1
            """,
            (frete_id,),
        ).fetchone()

        if accepted:
            raise ValueError(
                "Este frete já possui uma proposta aceita."
            )

        conn.execute(
            """
            INSERT OR IGNORE INTO fretes_transportadoras_negociacao (
                frete_id,
                transportadora
            )
            VALUES (?, ?)
            """,
            (frete_id, carrier),
        )

        conn.execute(
            """
            UPDATE fretes
            SET status = 'negociacao',
                transportadora_escolhida = NULL,
                atualizado_em = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (frete_id,),
        )

        if previous_status != "negociacao":
            conn.execute(
                """
                INSERT INTO fretes_historico_status (
                    frete_id,
                    status_anterior,
                    status_novo
                )
                VALUES (?, ?, 'negociacao')
                """,
                (frete_id, previous_status),
            )

    return True

def listar_transportadoras_negociacao(frete_id):
    """Return carriers participating in the freight negotiation."""

    with connect("fretes") as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                transportadora,
                criado_em
            FROM fretes_transportadoras_negociacao
            WHERE frete_id = ?
            ORDER BY id ASC
            """,
            (frete_id,),
        ).fetchall()

    return [dict(row) for row in rows]



def publicar_oferta(frete_id):
    """
    Publica um frete na página Oferta de Fretes.

    Somente fretes em preparação podem ser publicados.
    """
    with connect("fretes") as conn:
        cursor = conn.execute("""
            UPDATE fretes
            SET status = 'em_oferta',
                atualizado_em = CURRENT_TIMESTAMP
            WHERE id = ?
              AND status = 'em_preparacao'
        """, (frete_id,))

        if cursor.rowcount != 1:
            return False

        conn.execute("""
            INSERT INTO fretes_historico_status (
                frete_id,
                status_anterior,
                status_novo
            )
            VALUES (?, 'em_preparacao', 'em_oferta')
        """, (frete_id,))

    return True


def listar_fretes_em_oferta(plants=None):
    """Retorna apenas os fretes publicados."""
    clause, params = plant_scope(plants)
    with connect("fretes") as conn:
        registros = conn.execute(f"""
            SELECT id, dados_json, status
            FROM fretes
            WHERE status = 'em_oferta'
            {clause}
            ORDER BY atualizado_em DESC, id DESC
        """, params).fetchall()

    fretes = []

    for registro in registros:
        dados = json.loads(registro["dados_json"])
        dados["db_id"] = registro["id"]
        dados["status"] = registro["status"]
        fretes.append(dados)

    return fretes


# ==========================================
# EDITABLE FREIGHT FIELDS / OFFER WITHDRAWAL
# ==========================================
def retirar_oferta(frete_id):
    """Unpublish without deleting. Keep history and allow editing/republishing."""
    with connect("fretes") as conn:
        cursor = conn.execute("""
            UPDATE fretes
               SET status = 'em_preparacao', atualizado_em = CURRENT_TIMESTAMP
             WHERE id = ? AND status = 'em_oferta'
        """, (frete_id,))

        if cursor.rowcount != 1:
            return False

        conn.execute("""
            INSERT INTO fretes_historico_status
                (frete_id, status_anterior, status_novo)
            VALUES (?, 'em_oferta', 'em_preparacao')
        """, (frete_id,))

    return True


def atualizar_dados_carga(
    frete_id,
    tipo_carga,
    peso_liquido_kg,
    valor_inicial_negociacao=None,
    comentarios_carga="",
):
    """
    Atualiza os dados comerciais da carga no SQLite.

    Somente fretes em preparação podem ser editados.

    Campos:
    - tipo_carga
    - peso_liquido_kg
    - valor_inicial_negociacao
    - comentarios_carga

    Não altera o peso operacional nem os dados da rota.
    """

    # =====================================
    # TIPO DE CARGA
    # =====================================
    if tipo_carga not in ("batida", "paletizada"):
        raise ValueError("Tipo de carga inválido.")

    # =====================================
    # PESO LÍQUIDO
    # =====================================
    if peso_liquido_kg in ("", None):
        peso_liquido_kg = None
    else:
        try:
            peso_liquido_kg = float(peso_liquido_kg)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Peso líquido inválido.")

        if not (
            math.isfinite(peso_liquido_kg)
            and 0 < peso_liquido_kg < 1_000_000_000
        ):
            raise ValueError("O peso líquido deve ser um número positivo.")

    # =====================================
    # VALOR INICIAL DE NEGOCIAÇÃO
    # =====================================
    if valor_inicial_negociacao in ("", None):
        valor_inicial_negociacao = None
    else:
        try:
            valor_inicial_negociacao = float(valor_inicial_negociacao)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Valor inicial inválido.")

        if not (
            math.isfinite(valor_inicial_negociacao)
            and 0 <= valor_inicial_negociacao < 1_000_000_000
        ):
            raise ValueError("Valor inicial inválido.")

    # =====================================
    # COMENTÁRIOS
    # =====================================
    if comentarios_carga is None:
        comentarios_carga = ""

    if not isinstance(comentarios_carga, str):
        raise ValueError("Comentários inválidos.")

    comentarios_carga = comentarios_carga.strip()

    if len(comentarios_carga) > 3000:
        raise ValueError("Comentários excedem o limite de 3000 caracteres.")

    # =====================================
    # ATUALIZAÇÃO NO SQLITE
    # =====================================
    with connect("fretes") as conn:
        registro = conn.execute(
            """
            SELECT status, dados_json
            FROM fretes
            WHERE id = ?
            """,
            (frete_id,),
        ).fetchone()

        if registro is None:
            raise ValueError("Frete não encontrado.")

        if registro["status"] not in ("em_preparacao", "disponivel"):
            raise ValueError(
                "Retire a oferta antes de editar os dados da carga."
            )

        dados = json.loads(registro["dados_json"] or "{}")

        dados["tipo_carga"] = tipo_carga
        dados["peso_liquido_kg"] = peso_liquido_kg
        dados["valor_inicial_negociacao"] = valor_inicial_negociacao
        dados["comentarios_carga"] = comentarios_carga

        conn.execute(
            """
            UPDATE fretes
            SET
                dados_json = ?,
                atualizado_em = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                json.dumps(
                    dados,
                    ensure_ascii=False,
                    allow_nan=False,
                ),
                frete_id,
            ),
        )

    return dados


def concluir_frete(frete_id):
    """
    Conclui um frete com cotação aceita.

    Registra a transição no histórico de status.
    """
    with connect("fretes") as conn:
        registro = conn.execute(
            """
            SELECT status
            FROM fretes
            WHERE id = ?
            """,
            (frete_id,),
        ).fetchone()

        if registro is None:
            raise ValueError("Frete não encontrado.")

        if registro["status"] != "cotacao_aceita":
            raise ValueError(
                "Somente fretes com cotação aceita "
                "podem ser concluídos."
            )

        conn.execute(
            """
            UPDATE fretes
            SET status = 'concluido',
                atualizado_em = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (frete_id,),
        )

        conn.execute(
            """
            INSERT INTO fretes_historico_status (
                frete_id,
                status_anterior,
                status_novo
            )
            VALUES (?, 'cotacao_aceita', 'concluido')
            """,
            (frete_id,),
        )

    return True

def plant_scope(plants):
    if plants is None:
        return '', ()
    if not plants:
        return 'AND 1=0', ()
    return "AND CASE WHEN json_valid(dados_json) THEN CAST(json_extract(dados_json, '$.planta.codigo') AS TEXT) END IN (" + ','.join('?' for _ in plants) + ')', tuple(plants)



def delete_base():

    with connect("fretes") as conn:

        caminho = conn.execute(
            "PRAGMA database_list"
        ).fetchall()

        print("\n=== BANCO UTILIZADO PELA APLICAÇÃO ===")

        for banco in caminho:
            print(banco)

        tabelas = [
            "fretes_fechamentos",
            "fretes_historico_status",
            "fretes_propostas",
            "fretes_transportadoras_negociacao",
            "fretes",
        ]

        for tabela in tabelas:
            conn.execute(f"DELETE FROM {tabela}")

        conn.commit()

        print("\n=== REGISTROS RESTANTES ===")

        for tabela in tabelas:
            resultado = conn.execute(
                f"SELECT COUNT(*) FROM {tabela}"
            ).fetchone()

            print(f"{tabela}: {resultado[0]}")

    return True

def list_propose_send(carrier):

    with connect("fretes") as conn:

        freight = conn.execute(
            """
            SELECT
                fretes.id,
                fretes.numero_frete,
                fretes.origem,
                fretes.destino,
                fretes.peso_kg,
                fretes.valor AS valor_frete,
                fretes.status,
                fretes_propostas.valor AS valor_proposta,
                fretes_propostas.prazo_dias,
                fretes_propostas.observacoes,
                fretes_propostas.aceita,
                fretes_propostas.criado_em

            FROM fretes

            INNER JOIN fretes_propostas
                ON fretes.id = fretes_propostas.frete_id

            WHERE fretes_propostas.transportadora = ?

            ORDER BY fretes_propostas.criado_em DESC
            """,
            (carrier,)
        ).fetchall()

        return [dict(r) for r in freight]
