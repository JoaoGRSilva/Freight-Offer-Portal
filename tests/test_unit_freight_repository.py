import json

import pytest

import uuid

from services import freight_repository as repository

from services.db import connect
from services.freight_repository import (
    inicializar_banco,
    iniciar_negociacao,
    registrar_proposta,
    aceitar_proposta,
    contrapropor,
    responder_negociacao_transportadora
)


def criar_frete(status="em_preparacao"):
    with connect("fretes") as conn:
        cursor = conn.execute(
            """
            INSERT INTO fretes (
                chave_origem,
                status,
                dados_json
            )
            VALUES (?, ?, ?)
            """,
            (
                f"frete-teste-{status}-{uuid.uuid4().hex}",
                status,
                json.dumps({
                    "planta": {
                        "codigo": "SP01"
                    }
                }),
            ),
        )

        return cursor.lastrowid


@pytest.fixture
def banco_fretes(isolated_databases):
    inicializar_banco()


@pytest.mark.parametrize(
    "transportadora",
    [None, "", "   ", "—"],
)
def test_negotiation_rejects_invalid_carrier(
    banco_fretes,
    transportadora,
):
    with pytest.raises(
        ValueError,
        match="Selecione uma transportadora válida.",
    ):
        iniciar_negociacao(999, transportadora)


def test_negotiation_rejects_nonexistent_freight(banco_fretes):
    with pytest.raises(
        ValueError,
        match="Frete não encontrado.",
    ):
        iniciar_negociacao(999, "Transportadora Teste")


def test_negotiation_rejects_incompatible_freight_status(
    banco_fretes,
):
    frete_id = criar_frete(status="concluido")

    with pytest.raises(
        ValueError,
        match="Este frete não permite adicionar transportadoras.",
    ):
        iniciar_negociacao(frete_id, "Transportadora Teste")


def test_negotiation_rejects_freight_with_accepted_proposal(
    banco_fretes,
):
    frete_id = criar_frete(status="negociacao")

    with connect("fretes") as conn:
        conn.execute(
            """
            INSERT INTO fretes_propostas (
                frete_id,
                transportadora,
                valor,
                aceita
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                frete_id,
                "Transportadora Teste",
                1500,
                1,
            ),
        )

    with pytest.raises(
        ValueError,
        match="Este frete já possui uma proposta aceita.",
    ):
        iniciar_negociacao(frete_id, "Outra Transportadora")


def test_negotiation_adds_carriers_and_preserves_participants(
    banco_fretes,
):
    frete_id = criar_frete(status="em_preparacao")

    # Primeira transportadora inicia a negociação.
    assert iniciar_negociacao(
        frete_id,
        "Transportadora A",
    ) is True

    # Segunda transportadora é adicionada sem substituir a primeira.
    assert iniciar_negociacao(
        frete_id,
        "Transportadora B",
    ) is True

    # Repetir a mesma transportadora não deve gerar duplicidade.
    assert iniciar_negociacao(
        frete_id,
        "Transportadora A",
    ) is True

    with connect("fretes") as conn:
        frete = conn.execute(
            """
            SELECT status, transportadora_escolhida
            FROM fretes
            WHERE id = ?
            """,
            (frete_id,),
        ).fetchone()

        transportadoras = conn.execute(
            """
            SELECT transportadora
            FROM fretes_transportadoras_negociacao
            WHERE frete_id = ?
            ORDER BY transportadora
            """,
            (frete_id,),
        ).fetchall()

        historico = conn.execute(
            """
            SELECT status_anterior, status_novo
            FROM fretes_historico_status
            WHERE frete_id = ?
            """,
            (frete_id,),
        ).fetchall()

    assert frete["status"] == "negociacao"
    assert frete["transportadora_escolhida"] is None

    assert [
        row["transportadora"] for row in transportadoras
    ] == [
        "Transportadora A",
        "Transportadora B",
    ]

    # A transição para negociação deve ser registrada uma única vez.
    assert len(historico) == 1
    assert historico[0]["status_anterior"] == "em_preparacao"
    assert historico[0]["status_novo"] == "negociacao"



@pytest.mark.parametrize(
    "transportadora",
    [None, "", "   "],
)
def test_register_proposal_rejects_invalid_carrier(
    banco_fretes,
    transportadora,
):
    frete_id = criar_frete(status="em_oferta")

    with pytest.raises(
        ValueError,
        match="Transportadora não informada.",
    ):
        registrar_proposta(
            frete_id,
            transportadora,
            1500,
        )


@pytest.mark.parametrize(
    "valor",
    [None, "", "abc", 0, -100, float("inf"), float("nan")],
)
def test_register_proposal_rejects_invalid_value(
    banco_fretes,
    valor,
):
    frete_id = criar_frete(status="em_oferta")

    with pytest.raises(ValueError):
        registrar_proposta(
            frete_id,
            "Transportadora Teste",
            valor,
        )


@pytest.mark.parametrize(
    "prazo",
    ["abc", -1, 366],
)
def test_register_proposal_rejects_invalid_deadline(
    banco_fretes,
    prazo,
):
    frete_id = criar_frete(status="em_oferta")

    with pytest.raises(ValueError):
        registrar_proposta(
            frete_id,
            "Transportadora Teste",
            1500,
            prazo_dias=prazo,
        )


def test_register_proposal_rejects_nonexistent_freight(
    banco_fretes,
):
    with pytest.raises(
        ValueError,
        match="Frete não encontrado.",
    ):
        registrar_proposta(
            999,
            "Transportadora Teste",
            1500,
        )


def test_register_proposal_rejects_incompatible_freight_status(
    banco_fretes,
):
    frete_id = criar_frete(status="concluido")

    with pytest.raises(
        ValueError,
        match="Este frete não está disponível para propostas.",
    ):
        registrar_proposta(
            frete_id,
            "Transportadora Teste",
            1500,
        )


def test_register_proposal_saves_proposal_and_history(
    banco_fretes,
):
    frete_id = criar_frete(status="em_oferta")

    registrar_proposta(
        frete_id,
        "Transportadora A",
        1500,
        prazo_dias=5,
        observacoes="Entrega dentro do prazo.",
    )

    with connect("fretes") as conn:
        proposta = conn.execute(
            """
            SELECT *
            FROM fretes_propostas
            WHERE frete_id = ?
            """,
            (frete_id,),
        ).fetchone()

        historico = conn.execute(
            """
            SELECT *
            FROM fretes_negociacao_historico
            WHERE proposta_id = ?
            """,
            (proposta["id"],),
        ).fetchone()

        participante = conn.execute(
            """
            SELECT *
            FROM fretes_transportadoras_negociacao
            WHERE frete_id = ?
            """,
            (frete_id,),
        ).fetchone()

    assert proposta["transportadora"] == "Transportadora A"
    assert proposta["valor"] == 1500
    assert proposta["prazo_dias"] == 5
    assert proposta["observacoes"] == "Entrega dentro do prazo."
    assert proposta["status_negociacao"] == "aguardando_operador"

    assert historico["autor"] == "transportadora"
    assert historico["tipo"] == "proposta_inicial"
    assert historico["valor"] == 1500

    assert participante["transportadora"] == "Transportadora A"


def test_register_proposal_rejects_duplicate_carrier(
    banco_fretes,
):
    frete_id = criar_frete(status="em_oferta")

    registrar_proposta(
        frete_id,
        "Transportadora A",
        1500,
    )

    with pytest.raises(
        ValueError,
        match="Esta transportadora já possui uma negociação neste frete.",
    ):
        registrar_proposta(
            frete_id,
            "transportadora a",
            1800,
        )



def criar_proposta(frete_id, transportadora, valor=1500):
    with connect("fretes") as conn:
        cursor = conn.execute(
            """
            INSERT INTO fretes_propostas (
                frete_id,
                transportadora,
                valor,
                status_negociacao
            )
            VALUES (?, ?, ?, 'aguardando_operador')
            """,
            (frete_id, transportadora, valor),
        )

        return cursor.lastrowid


def test_accept_proposal_rejects_nonexistent_freight(
    banco_fretes,
):
    with pytest.raises(
        ValueError,
        match="Frete não encontrado.",
    ):
        aceitar_proposta(999, 1)


def test_accept_proposal_rejects_freight_not_in_negotiation(
    banco_fretes,
):
    frete_id = criar_frete(status="em_oferta")
    proposta_id = criar_proposta(
        frete_id,
        "Transportadora A",
    )

    with pytest.raises(
        ValueError,
        match="Frete não está em negociação.",
    ):
        aceitar_proposta(frete_id, proposta_id)


def test_accept_proposal_rejects_nonexistent_proposal(
    banco_fretes,
):
    frete_id = criar_frete(status="negociacao")

    with pytest.raises(
        ValueError,
        match="Proposta não encontrada.",
    ):
        aceitar_proposta(frete_id, 999)


def test_accept_proposal_rejects_proposal_not_waiting_operator(
    banco_fretes,
):
    frete_id = criar_frete(status="negociacao")
    proposta_id = criar_proposta(
        frete_id,
        "Transportadora A",
    )

    with connect("fretes") as conn:
        conn.execute(
            """
            UPDATE fretes_propostas
            SET status_negociacao = 'aceita'
            WHERE id = ?
            """,
            (proposta_id,),
        )

    with pytest.raises(
        ValueError,
        match="Esta negociação não está aguardando ação do operador.",
    ):
        aceitar_proposta(frete_id, proposta_id)


def test_accept_proposal_updates_freight_and_history(
    banco_fretes,
):
    frete_id = criar_frete(status="negociacao")

    proposta_a = criar_proposta(
        frete_id,
        "Transportadora A",
        1500,
    )
    proposta_b = criar_proposta(
        frete_id,
        "Transportadora B",
        1800,
    )

    aceitar_proposta(frete_id, proposta_a)

    with connect("fretes") as conn:
        frete = conn.execute(
            """
            SELECT transportadora_escolhida
            FROM fretes
            WHERE id = ?
            """,
            (frete_id,),
        ).fetchone()

        propostas = conn.execute(
            """
            SELECT id, aceita, status_negociacao
            FROM fretes_propostas
            WHERE frete_id = ?
            ORDER BY id
            """,
            (frete_id,),
        ).fetchall()

        historico = conn.execute(
            """
            SELECT autor, tipo, valor
            FROM fretes_negociacao_historico
            WHERE proposta_id = ?
            """,
            (proposta_a,),
        ).fetchall()

    assert frete["transportadora_escolhida"] == "Transportadora A"

    assert propostas[0]["aceita"] == 1
    assert propostas[0]["status_negociacao"] == "aceita"

    assert propostas[1]["aceita"] == 0

    assert len(historico) == 1
    assert historico[0]["autor"] == "operador"
    assert historico[0]["tipo"] == "aceite"
    assert historico[0]["valor"] == 1500



@pytest.mark.parametrize(
    "valor",
    [None, "", "abc", 0, -100, float("inf"), float("nan")],
)
def test_counterproposal_rejects_invalid_value(
    banco_fretes,
    valor,
):
    frete_id = criar_frete(status="negociacao")
    proposta_id = criar_proposta(
        frete_id,
        "Transportadora A",
    )

    with pytest.raises(ValueError):
        contrapropor(
            frete_id,
            proposta_id,
            valor,
        )


@pytest.mark.parametrize(
    "prazo",
    ["abc", -1, 366],
)
def test_counterproposal_rejects_invalid_deadline(
    banco_fretes,
    prazo,
):
    frete_id = criar_frete(status="negociacao")
    proposta_id = criar_proposta(
        frete_id,
        "Transportadora A",
    )

    with pytest.raises(ValueError):
        contrapropor(
            frete_id,
            proposta_id,
            1800,
            prazo_dias=prazo,
        )


def test_counterproposal_rejects_nonexistent_proposal(
    banco_fretes,
):
    frete_id = criar_frete(status="negociacao")

    with pytest.raises(
        ValueError,
        match="Proposta não encontrada.",
    ):
        contrapropor(
            frete_id,
            999,
            1800,
        )


def test_counterproposal_rejects_freight_not_in_negotiation(
    banco_fretes,
):
    frete_id = criar_frete(status="em_oferta")
    proposta_id = criar_proposta(
        frete_id,
        "Transportadora A",
    )

    with pytest.raises(
        ValueError,
        match="Frete não está em negociação.",
    ):
        contrapropor(
            frete_id,
            proposta_id,
            1800,
        )


def test_counterproposal_rejects_proposal_not_waiting_operator(
    banco_fretes,
):
    frete_id = criar_frete(status="negociacao")
    proposta_id = criar_proposta(
        frete_id,
        "Transportadora A",
    )

    with connect("fretes") as conn:
        conn.execute(
            """
            UPDATE fretes_propostas
            SET status_negociacao = 'aguardando_transportadora'
            WHERE id = ?
            """,
            (proposta_id,),
        )

    with pytest.raises(
        ValueError,
        match="Esta negociação não está aguardando o operador.",
    ):
        contrapropor(
            frete_id,
            proposta_id,
            1800,
        )


def test_counterproposal_updates_proposal_and_history(
    banco_fretes,
):
    frete_id = criar_frete(status="negociacao")
    proposta_id = criar_proposta(
        frete_id,
        "Transportadora A",
        1500,
    )

    resultado = contrapropor(
        frete_id,
        proposta_id,
        1800,
        prazo_dias=7,
        observacoes="Novo valor negociado.",
    )

    with connect("fretes") as conn:
        proposta = conn.execute(
            """
            SELECT *
            FROM fretes_propostas
            WHERE id = ?
            """,
            (proposta_id,),
        ).fetchone()

        historico = conn.execute(
            """
            SELECT *
            FROM fretes_negociacao_historico
            WHERE proposta_id = ?
            """,
            (proposta_id,),
        ).fetchall()

    assert resultado is True

    assert proposta["valor"] == 1800
    assert proposta["prazo_dias"] == 7
    assert proposta["observacoes"] == "Novo valor negociado."
    assert proposta["status_negociacao"] == "aguardando_transportadora"

    assert len(historico) == 1
    assert historico[0]["autor"] == "operador"
    assert historico[0]["tipo"] == "contraproposta"
    assert historico[0]["valor"] == 1800



def preparar_proposta_para_transportadora(frete_id, proposta_id):
    with connect("fretes") as conn:
        conn.execute(
            """
            UPDATE fretes_propostas
            SET status_negociacao = 'aguardando_transportadora'
            WHERE id = ?
            """,
            (proposta_id,),
        )


def test_carrier_cannot_respond_to_another_carrier_proposal(
    banco_fretes,
):
    frete_id = criar_frete(status="negociacao")
    proposta_id = criar_proposta(
        frete_id,
        "Transportadora A",
    )
    preparar_proposta_para_transportadora(frete_id, proposta_id)

    with pytest.raises(
        ValueError,
        match="Esta negociação não pertence à sua transportadora.",
    ):
        responder_negociacao_transportadora(
            frete_id,
            proposta_id,
            "Transportadora B",
            "aceitar",
        )


def test_carrier_cannot_respond_when_freight_is_not_in_negotiation(
    banco_fretes,
):
    frete_id = criar_frete(status="em_oferta")
    proposta_id = criar_proposta(
        frete_id,
        "Transportadora A",
    )
    preparar_proposta_para_transportadora(frete_id, proposta_id)

    with pytest.raises(
        ValueError,
        match="Frete não está em negociação.",
    ):
        responder_negociacao_transportadora(
            frete_id,
            proposta_id,
            "Transportadora A",
            "aceitar",
        )


def test_carrier_cannot_respond_when_proposal_is_not_waiting(
    banco_fretes,
):
    frete_id = criar_frete(status="negociacao")
    proposta_id = criar_proposta(
        frete_id,
        "Transportadora A",
    )

    with pytest.raises(
        ValueError,
        match="Esta negociação não está aguardando a transportadora.",
    ):
        responder_negociacao_transportadora(
            frete_id,
            proposta_id,
            "Transportadora A",
            "aceitar",
        )


def test_carrier_cannot_respond_to_nonexistent_proposal(
    banco_fretes,
):
    frete_id = criar_frete(status="negociacao")

    with pytest.raises(
        ValueError,
        match="Negociação não encontrada.",
    ):
        responder_negociacao_transportadora(
            frete_id,
            999,
            "Transportadora A",
            "aceitar",
        )


def test_carrier_cannot_use_invalid_action(banco_fretes):
    frete_id = criar_frete(status="negociacao")
    proposta_id = criar_proposta(
        frete_id,
        "Transportadora A",
    )
    preparar_proposta_para_transportadora(frete_id, proposta_id)

    with pytest.raises(ValueError, match="Ação inválida."):
        responder_negociacao_transportadora(
            frete_id,
            proposta_id,
            "Transportadora A",
            "recusar",
        )


def test_carrier_accepts_counterproposal(banco_fretes):
    frete_id = criar_frete(status="negociacao")
    proposta_a = criar_proposta(
        frete_id,
        "Transportadora A",
    )
    proposta_b = criar_proposta(
        frete_id,
        "Transportadora B",
    )
    preparar_proposta_para_transportadora(frete_id, proposta_a)

    resultado = responder_negociacao_transportadora(
        frete_id,
        proposta_a,
        "Transportadora A",
        "aceitar",
    )

    with connect("fretes") as conn:
        frete = conn.execute(
            """
            SELECT transportadora_escolhida
            FROM fretes WHERE id = ?
            """,
            (frete_id,),
        ).fetchone()

        propostas = conn.execute(
            """
            SELECT id, aceita, status_negociacao
            FROM fretes_propostas
            WHERE frete_id = ?
            ORDER BY id
            """,
            (frete_id,),
        ).fetchall()

        historico = conn.execute(
            """
            SELECT autor, tipo
            FROM fretes_negociacao_historico
            WHERE proposta_id = ?
            """,
            (proposta_a,),
        ).fetchall()

    assert resultado["status"] == "aceita"
    assert frete["transportadora_escolhida"] == "Transportadora A"
    assert propostas[0]["aceita"] == 1
    assert propostas[0]["status_negociacao"] == "aceita"
    assert propostas[1]["aceita"] == 0
    assert propostas[1]["id"] == proposta_b
    assert historico[0]["autor"] == "transportadora"
    assert historico[0]["tipo"] == "aceite"


def test_carrier_sends_counterproposal(banco_fretes):
    frete_id = criar_frete(status="negociacao")
    proposta_id = criar_proposta(
        frete_id,
        "Transportadora A",
    )
    preparar_proposta_para_transportadora(frete_id, proposta_id)

    resultado = responder_negociacao_transportadora(
        frete_id,
        proposta_id,
        "Transportadora A",
        "contrapropor",
        valor=1700,
        prazo_dias=10,
        observacoes="Nova condição da transportadora.",
    )

    with connect("fretes") as conn:
        proposta = conn.execute(
            """
            SELECT *
            FROM fretes_propostas
            WHERE id = ?
            """,
            (proposta_id,),
        ).fetchone()

        historico = conn.execute(
            """
            SELECT autor, tipo, valor
            FROM fretes_negociacao_historico
            WHERE proposta_id = ?
            """,
            (proposta_id,),
        ).fetchall()

    assert resultado["status"] == "aguardando_operador"
    assert proposta["valor"] == 1700
    assert proposta["prazo_dias"] == 10
    assert proposta["observacoes"] == "Nova condição da transportadora."
    assert proposta["status_negociacao"] == "aguardando_operador"
    assert historico[0]["autor"] == "transportadora"
    assert historico[0]["tipo"] == "contraproposta"
    assert historico[0]["valor"] == 1700



@pytest.mark.parametrize(
    "valor",
    [None, "", "abc", 0, -100, float("inf"), float("nan")],
)
def test_carrier_counterproposal_rejects_invalid_value(
    banco_fretes,
    valor,
):
    frete_id = criar_frete(status="negociacao")
    proposta_id = criar_proposta(frete_id, "Transportadora A")
    preparar_proposta_para_transportadora(frete_id, proposta_id)

    with pytest.raises(ValueError):
        responder_negociacao_transportadora(
            frete_id,
            proposta_id,
            "Transportadora A",
            "contrapropor",
            valor=valor,
        )


@pytest.mark.parametrize(
    "prazo",
    ["abc", -1, 366],
)
def test_carrier_counterproposal_rejects_invalid_deadline(
    banco_fretes,
    prazo,
):
    frete_id = criar_frete(status="negociacao")
    proposta_id = criar_proposta(frete_id, "Transportadora A")
    preparar_proposta_para_transportadora(frete_id, proposta_id)

    with pytest.raises(ValueError, match="Prazo inválido."):
        responder_negociacao_transportadora(
            frete_id,
            proposta_id,
            "Transportadora A",
            "contrapropor",
            valor=1800,
            prazo_dias=prazo,
        )


def test_carrier_counterproposal_accepts_minimum_deadline(
    banco_fretes,
):
    frete_id = criar_frete(status="negociacao")
    proposta_id = criar_proposta(frete_id, "Transportadora A")
    preparar_proposta_para_transportadora(frete_id, proposta_id)

    responder_negociacao_transportadora(
        frete_id,
        proposta_id,
        "Transportadora A",
        "contrapropor",
        valor=1800,
        prazo_dias=0,
    )

    with connect("fretes") as conn:
        proposta = conn.execute(
            "SELECT prazo_dias FROM fretes_propostas WHERE id = ?",
            (proposta_id,),
        ).fetchone()

    assert proposta["prazo_dias"] == 0


def test_carrier_counterproposal_accepts_maximum_deadline(
    banco_fretes,
):
    frete_id = criar_frete(status="negociacao")
    proposta_id = criar_proposta(frete_id, "Transportadora A")
    preparar_proposta_para_transportadora(frete_id, proposta_id)

    responder_negociacao_transportadora(
        frete_id,
        proposta_id,
        "Transportadora A",
        "contrapropor",
        valor=1800,
        prazo_dias=365,
    )

    with connect("fretes") as conn:
        proposta = conn.execute(
            "SELECT prazo_dias FROM fretes_propostas WHERE id = ?",
            (proposta_id,),
        ).fetchone()

    assert proposta["prazo_dias"] == 365


def test_carrier_name_comparison_ignores_case_and_spaces(
    banco_fretes,
):
    frete_id = criar_frete(status="negociacao")
    proposta_id = criar_proposta(frete_id, "Transportadora A")
    preparar_proposta_para_transportadora(frete_id, proposta_id)

    resultado = responder_negociacao_transportadora(
        frete_id,
        proposta_id,
        "  TRANSPORTADORA A  ",
        "aceitar",
    )

    assert resultado["status"] == "aceita"


def test_carrier_cannot_respond_using_wrong_freight_id(
    banco_fretes,
):
    frete_id = criar_frete(status="negociacao")
    outro_frete_id = criar_frete(status="negociacao")
    proposta_id = criar_proposta(frete_id, "Transportadora A")
    preparar_proposta_para_transportadora(frete_id, proposta_id)

    with pytest.raises(
        ValueError,
        match="Negociação não encontrada.",
    ):
        responder_negociacao_transportadora(
            outro_frete_id,
            proposta_id,
            "Transportadora A",
            "aceitar",
        )


def test_carrier_cannot_respond_with_empty_name(
    banco_fretes,
):
    frete_id = criar_frete(status="negociacao")
    proposta_id = criar_proposta(frete_id, "Transportadora A")
    preparar_proposta_para_transportadora(frete_id, proposta_id)

    with pytest.raises(
        ValueError,
        match="Esta negociação não pertence à sua transportadora.",
    ):
        responder_negociacao_transportadora(
            frete_id,
            proposta_id,
            "",
            "aceitar",
        )


def test_carrier_action_is_case_insensitive(
    banco_fretes,
):
    frete_id = criar_frete(status="negociacao")
    proposta_id = criar_proposta(frete_id, "Transportadora A")
    preparar_proposta_para_transportadora(frete_id, proposta_id)

    resultado = responder_negociacao_transportadora(
        frete_id,
        proposta_id,
        "Transportadora A",
        "ACEITAR",
    )

    assert resultado["status"] == "aceita"


def test_carrier_counterproposal_clears_empty_observations(
    banco_fretes,
):
    frete_id = criar_frete(status="negociacao")
    proposta_id = criar_proposta(frete_id, "Transportadora A")
    preparar_proposta_para_transportadora(frete_id, proposta_id)

    responder_negociacao_transportadora(
        frete_id,
        proposta_id,
        "Transportadora A",
        "contrapropor",
        valor=1800,
        observacoes="   ",
    )

    with connect("fretes") as conn:
        proposta = conn.execute(
            "SELECT observacoes FROM fretes_propostas WHERE id = ?",
            (proposta_id,),
        ).fetchone()

    assert proposta["observacoes"] == ""



def test_complete_negotiation_flow(banco_fretes):
    # 1. Criar frete e registrar proposta inicial
    frete_id = criar_frete(status="negociacao")

    proposta_id = repository.registrar_proposta(
        frete_id=frete_id,
        transportadora="Transportadora A",
        valor=2000,
        prazo_dias=10,
        observacoes="Proposta inicial",
    )

    # 2. Operador envia contraproposta
    repository.contrapropor(
        frete_id=frete_id,
        proposta_id=proposta_id,
        valor=1800,
        prazo_dias=8,
        observacoes="Contraproposta do operador",
    )

    # 3. Transportadora envia nova contraproposta
    resultado = repository.responder_negociacao_transportadora(
        frete_id=frete_id,
        proposta_id=proposta_id,
        transportadora="Transportadora A",
        acao="contrapropor",
        valor=1900,
        prazo_dias=9,
        observacoes="Contraproposta da transportadora",
    )

    assert resultado["status"] == "aguardando_operador"

    # 4. Operador aceita a proposta
    repository.aceitar_proposta(
        frete_id=frete_id,
        proposta_id=proposta_id,
    )

    # 5. Conferir o estado final e o histórico
    with connect("fretes") as conn:
        frete = conn.execute(
            """
            SELECT transportadora_escolhida
            FROM fretes
            WHERE id = ?
            """,
            (frete_id,),
        ).fetchone()

        proposta = conn.execute(
            """
            SELECT valor, prazo_dias, aceita, status_negociacao
            FROM fretes_propostas
            WHERE id = ?
            """,
            (proposta_id,),
        ).fetchone()

        historico = conn.execute(
            """
            SELECT autor, tipo
            FROM fretes_negociacao_historico
            WHERE proposta_id = ?
            ORDER BY id
            """,
            (proposta_id,),
        ).fetchall()

    assert frete["transportadora_escolhida"] == "Transportadora A"
    assert proposta["valor"] == 1900
    assert proposta["prazo_dias"] == 9
    assert proposta["aceita"] == 1
    assert proposta["status_negociacao"] == "aceita"

    assert [(h["autor"], h["tipo"]) for h in historico] == [
        ("transportadora", "proposta_inicial"),
        ("operador", "contraproposta"),
        ("transportadora", "contraproposta"),
        ("operador", "aceite"),
    ]


def test_carrier_can_accept_operator_counterproposal_directly(banco_fretes):
    frete_id = criar_frete(status="negociacao")

    proposta_id = repository.registrar_proposta(
        frete_id=frete_id,
        transportadora="Transportadora B",
        valor=2500,
    )

    # Operador envia contraproposta
    repository.contrapropor(
        frete_id=frete_id,
        proposta_id=proposta_id,
        valor=2200,
    )

    # Transportadora aceita diretamente
    resultado = repository.responder_negociacao_transportadora(
        frete_id=frete_id,
        proposta_id=proposta_id,
        transportadora="Transportadora B",
        acao="aceitar",
    )

    assert resultado["status"] == "aceita"

    with connect("fretes") as conn:
        frete = conn.execute(
            """
            SELECT transportadora_escolhida
            FROM fretes
            WHERE id = ?
            """,
            (frete_id,),
        ).fetchone()

        proposta = conn.execute(
            """
            SELECT aceita, status_negociacao
            FROM fretes_propostas
            WHERE id = ?
            """,
            (proposta_id,),
        ).fetchone()

        historico = conn.execute(
            """
            SELECT autor, tipo
            FROM fretes_negociacao_historico
            WHERE proposta_id = ?
            ORDER BY id
            """,
            (proposta_id,),
        ).fetchall()

    assert frete["transportadora_escolhida"] == "Transportadora B"
    assert proposta["aceita"] == 1
    assert proposta["status_negociacao"] == "aceita"

    assert [(h["autor"], h["tipo"]) for h in historico] == [
        ("transportadora", "proposta_inicial"),
        ("operador", "contraproposta"),
        ("transportadora", "aceite"),
    ]


def test_carrier_cannot_respond_twice_to_same_counterproposal(banco_fretes):
    frete_id = criar_frete(status="negociacao")

    proposta_id = repository.registrar_proposta(
        frete_id=frete_id,
        transportadora="Transportadora C",
        valor=3000,
    )

    repository.contrapropor(
        frete_id=frete_id,
        proposta_id=proposta_id,
        valor=2800,
    )

    # Primeira resposta: contraproposta válida
    repository.responder_negociacao_transportadora(
        frete_id=frete_id,
        proposta_id=proposta_id,
        transportadora="Transportadora C",
        acao="contrapropor",
        valor=2700,
    )

    # A negociação agora aguarda o operador.
    # A transportadora não pode responder novamente.
    with pytest.raises(
        ValueError,
        match="Esta negociação não está aguardando a transportadora.",
    ):
        repository.responder_negociacao_transportadora(
            frete_id=frete_id,
            proposta_id=proposta_id,
            transportadora="Transportadora C",
            acao="aceitar",
        )


# ============================================================
# IMPORTAÇÃO, CHAVES E ATUALIZAÇÃO DE FRETES
# ============================================================

def frete_importacao(numero="12345", planta="SP01"):
    return {
        "num": numero,
        "planta": {"codigo": planta},
        "pedidos": ["PED-002", "PED-001"],
        "origem": "Campinas - SP",
        "destino": "Santos - SP",
        "peso_kg": 15000,
        "data_carga": "2026-11-25",
        "calculo": {"mercado": 2500},
        "recomendacao": {"transportadora": "Transportadora A"},
    }


def test_chave_do_frete_usa_numero_e_planta():
    frete = frete_importacao()

    chave = repository.chave_do_frete(frete)

    assert isinstance(chave, str)
    assert len(chave) == 64
    assert chave == repository.chave_do_frete(frete)


def test_chave_do_frete_sem_numero_considera_dados_da_carga():
    frete_a = frete_importacao(numero=None)
    frete_b = frete_importacao(numero=None)
    frete_b["pedidos"] = ["PED-001", "PED-002"]

    assert repository.chave_do_frete(frete_a) == (
        repository.chave_do_frete(frete_b)
    )


def test_chave_do_frete_diferencia_plantas():
    frete_a = frete_importacao(planta="SP01")
    frete_b = frete_importacao(planta="SP02")

    assert repository.chave_do_frete(frete_a) != (
        repository.chave_do_frete(frete_b)
    )


def test_salvar_fretes_insere_novo_frete(banco_fretes):
    resultado = repository.salvar_fretes([frete_importacao()])

    assert resultado == {
        "inseridos": 1,
        "atualizados": 0,
    }

    with connect("fretes") as conn:
        frete = conn.execute(
            "SELECT * FROM fretes"
        ).fetchone()

        historico = conn.execute(
            """
            SELECT status_anterior, status_novo
            FROM fretes_historico_status
            WHERE frete_id = ?
            """,
            (frete["id"],),
        ).fetchone()

    assert frete["numero_frete"] == "12345"
    assert frete["origem"] == "Campinas - SP"
    assert frete["destino"] == "Santos - SP"
    assert frete["peso_kg"] == 15000
    assert frete["valor"] == 2500
    assert frete["transportadora_recomendada"] == "Transportadora A"
    assert frete["status"] == "em_preparacao"

    assert historico["status_anterior"] is None
    assert historico["status_novo"] == "em_preparacao"


def test_salvar_fretes_atualiza_existente_sem_duplicar(banco_fretes):
    frete = frete_importacao()

    primeiro = repository.salvar_fretes([frete])
    segundo = repository.salvar_fretes([frete_importacao()])

    assert primeiro["inseridos"] == 1
    assert segundo["inseridos"] == 0
    assert segundo["atualizados"] == 1

    with connect("fretes") as conn:
        quantidade = conn.execute(
            "SELECT COUNT(*) FROM fretes"
        ).fetchone()[0]

        historicos = conn.execute(
            "SELECT COUNT(*) FROM fretes_historico_status"
        ).fetchone()[0]

    assert quantidade == 1
    assert historicos == 1


def test_salvar_fretes_preserva_dados_comerciais_e_status(banco_fretes):
    frete = frete_importacao()
    repository.salvar_fretes([frete])

    chave = repository.chave_do_frete(frete)

    with connect("fretes") as conn:
        registro = conn.execute(
            "SELECT id, dados_json FROM fretes WHERE chave_origem = ?",
            (chave,),
        ).fetchone()

        dados = json.loads(registro["dados_json"])
        dados.update({
            "tipo_carga": "paletizada",
            "peso_liquido_kg": 12000,
            "valor_inicial_negociacao": 2200,
            "comentarios_carga": "Informação do operador",
        })

        conn.execute(
            """
            UPDATE fretes
            SET dados_json = ?,
                status = 'negociacao',
                transportadora_escolhida = 'Transportadora B'
            WHERE id = ?
            """,
            (json.dumps(dados), registro["id"]),
        )

    repository.salvar_fretes([frete_importacao()])

    with connect("fretes") as conn:
        registro = conn.execute(
            "SELECT * FROM fretes WHERE id = ?",
            (registro["id"],),
        ).fetchone()

    dados_finais = json.loads(registro["dados_json"])

    assert registro["status"] == "negociacao"
    assert registro["transportadora_escolhida"] == "Transportadora B"
    assert dados_finais["tipo_carga"] == "paletizada"
    assert dados_finais["peso_liquido_kg"] == 12000
    assert dados_finais["valor_inicial_negociacao"] == 2200
    assert dados_finais["comentarios_carga"] == "Informação do operador"


def test_salvar_fretes_rejeita_valores_nan(banco_fretes):
    frete = frete_importacao()
    frete["peso_kg"] = float("nan")

    with pytest.raises(ValueError):
        repository.salvar_fretes([frete])


def test_salvar_fretes_status_inicial_invalido_volta_para_preparacao(
    banco_fretes,
):
    frete = frete_importacao()
    frete["status_inicial"] = "status_invalido"

    repository.salvar_fretes([frete])

    with connect("fretes") as conn:
        status = conn.execute(
            "SELECT status FROM fretes"
        ).fetchone()["status"]

    assert status == "em_preparacao"


# ============================================================
# CONSULTAS E FILTROS
# ============================================================

def test_listar_fretes_retorna_transportadora_escolhida(banco_fretes):
    frete_id = criar_frete()

    with connect("fretes") as conn:
        conn.execute(
            """
            UPDATE fretes
            SET transportadora_recomendada = 'Transportadora A',
                transportadora_escolhida = 'Transportadora B'
            WHERE id = ?
            """,
            (frete_id,),
        )

    resultado = repository.listar_fretes()

    assert len(resultado) == 1
    assert resultado[0]["id"] == frete_id
    assert resultado[0]["transportadora"] == "Transportadora B"


def test_listar_fretes_filtra_por_planta(banco_fretes):
    frete_sp = criar_frete()
    frete_mg = criar_frete()

    with connect("fretes") as conn:
        conn.execute(
            "UPDATE fretes SET dados_json = ? WHERE id = ?",
            (json.dumps({"planta": {"codigo": "SP01"}}), frete_sp),
        )
        conn.execute(
            "UPDATE fretes SET dados_json = ? WHERE id = ?",
            (json.dumps({"planta": {"codigo": "MG01"}}), frete_mg),
        )

    resultado = repository.listar_fretes(["SP01"])

    assert [frete["id"] for frete in resultado] == [frete_sp]


def test_listar_fretes_com_lista_vazia_nao_retorna_registros(
    banco_fretes,
):
    criar_frete()

    assert repository.listar_fretes([]) == []


def test_listar_fretes_preparacao_retorna_dados_completos(banco_fretes):
    frete = frete_importacao()
    repository.salvar_fretes([frete])

    resultado = repository.listar_fretes_preparacao()

    assert len(resultado) == 1
    assert resultado[0]["num"] == "12345"
    assert resultado[0]["db_id"] > 0
    assert resultado[0]["status_db"] == "em_preparacao"


def test_listar_fretes_em_oferta_retorna_somente_publicados(banco_fretes):
    frete_id = criar_frete(status="em_oferta")
    criar_frete(status="em_preparacao")

    resultado = repository.listar_fretes_em_oferta()

    assert len(resultado) == 1
    assert resultado[0]["db_id"] == frete_id
    assert resultado[0]["status"] == "em_oferta"


def test_listar_propostas_retorna_propostas_do_frete(banco_fretes):
    frete_id = criar_frete(status="em_oferta")

    repository.registrar_proposta(
        frete_id,
        "Transportadora A",
        1500,
    )

    resultado = repository.listar_propostas(frete_id)

    assert len(resultado) == 1
    assert resultado[0]["transportadora"] == "Transportadora A"


def test_listar_transportadoras_negociacao_retorna_participantes(
    banco_fretes,
):
    frete_id = criar_frete()

    iniciar_negociacao(frete_id, "Transportadora A")
    iniciar_negociacao(frete_id, "Transportadora B")

    resultado = repository.listar_transportadoras_negociacao(frete_id)

    assert [
        item["transportadora"] for item in resultado
    ] == [
        "Transportadora A",
        "Transportadora B",
    ]


def test_obter_id_por_chave_retorna_id_e_none(banco_fretes):
    frete = frete_importacao()
    repository.salvar_fretes([frete])

    chave = repository.chave_do_frete(frete)

    assert repository.obter_id_por_chave(chave) == 1
    assert repository.obter_id_por_chave("chave-inexistente") is None


def test_obter_estado_frete_retorna_estado_persistido(banco_fretes):
    frete_id = criar_frete()

    resultado = repository.obter_estado_frete(frete_id)

    assert resultado["id"] == frete_id
    assert resultado["status"] == "em_preparacao"
    assert repository.obter_estado_frete(999) is None


def test_obter_frete_retorna_detalhes_json(banco_fretes):
    frete = frete_importacao()
    repository.salvar_fretes([frete])

    resultado = repository.obter_frete(1)

    assert resultado["id"] == 1
    assert resultado["detalhes"]["num"] == "12345"
    assert repository.obter_frete(999) is None


def test_obter_fechamento_retorna_none_quando_nao_existe(banco_fretes):
    frete_id = criar_frete()

    assert repository.obter_fechamento(frete_id) is None


# ============================================================
# STATUS, PUBLICAÇÃO E RETIRADA DE OFERTAS
# ============================================================

def test_atualizar_status_registra_historico(banco_fretes):
    frete_id = criar_frete(status="em_preparacao")

    assert repository.atualizar_status(frete_id, "em_oferta") is True

    with connect("fretes") as conn:
        historico = conn.execute(
            """
            SELECT status_anterior, status_novo
            FROM fretes_historico_status
            WHERE frete_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (frete_id,),
        ).fetchone()

    assert historico["status_anterior"] == "em_preparacao"
    assert historico["status_novo"] == "em_oferta"


def test_atualizar_status_ignora_status_inalterado(banco_fretes):
    frete_id = criar_frete(status="em_preparacao")

    assert repository.atualizar_status(
        frete_id,
        "em_preparacao",
    ) is True

    with connect("fretes") as conn:
        quantidade = conn.execute(
            """
            SELECT COUNT(*)
            FROM fretes_historico_status
            WHERE frete_id = ?
            """,
            (frete_id,),
        ).fetchone()[0]

    assert quantidade == 0


def test_atualizar_status_rejeita_status_invalido(banco_fretes):
    frete_id = criar_frete()

    with pytest.raises(ValueError, match="Status inválido"):
        repository.atualizar_status(frete_id, "invalido")


def test_atualizar_status_retorna_false_para_frete_inexistente(
    banco_fretes,
):
    assert repository.atualizar_status(999, "em_oferta") is False


def test_publicar_oferta_e_retirar_oferta(banco_fretes):
    frete_id = criar_frete(status="em_preparacao")

    assert repository.publicar_oferta(frete_id) is True
    assert repository.publicar_oferta(frete_id) is False

    assert repository.retirar_oferta(frete_id) is True
    assert repository.retirar_oferta(frete_id) is False

    with connect("fretes") as conn:
        status = conn.execute(
            "SELECT status FROM fretes WHERE id = ?",
            (frete_id,),
        ).fetchone()["status"]

        historico = conn.execute(
            """
            SELECT status_anterior, status_novo
            FROM fretes_historico_status
            WHERE frete_id = ?
            ORDER BY id
            """,
            (frete_id,),
        ).fetchall()

    assert status == "em_preparacao"
    assert [
        (item["status_anterior"], item["status_novo"])
        for item in historico
    ] == [
        ("em_preparacao", "em_oferta"),
        ("em_oferta", "em_preparacao"),
    ]


# ============================================================
# EDIÇÃO DOS DADOS COMERCIAIS
# ============================================================

def test_atualizar_dados_carga_salva_campos_comerciais(banco_fretes):
    frete_id = criar_frete()

    resultado = repository.atualizar_dados_carga(
        frete_id,
        tipo_carga="paletizada",
        peso_liquido_kg="12000",
        valor_inicial_negociacao="2500",
        comentarios_carga="  Carga frágil  ",
    )

    assert resultado["tipo_carga"] == "paletizada"
    assert resultado["peso_liquido_kg"] == 12000
    assert resultado["valor_inicial_negociacao"] == 2500
    assert resultado["comentarios_carga"] == "Carga frágil"

    with connect("fretes") as conn:
        registro = conn.execute(
            "SELECT dados_json FROM fretes WHERE id = ?",
            (frete_id,),
        ).fetchone()

    assert json.loads(registro["dados_json"]) == resultado


@pytest.mark.parametrize(
    "tipo,peso,valor,comentarios",
    [
        ("invalido", 1000, 1000, ""),
        ("batida", -1, 1000, ""),
        ("batida", float("inf"), 1000, ""),
        ("batida", 1000, -1, ""),
        ("batida", 1000, float("nan"), ""),
        ("batida", 1000, 1000, 123),
        ("batida", 1000, 1000, "x" * 3001),
        ("batida", "abc", 1000, ""),
        ("batida", 1000, "abc", ""),
    ],
)
def test_atualizar_dados_carga_rejeita_dados_invalidos(
    banco_fretes,
    tipo,
    peso,
    valor,
    comentarios,
):
    frete_id = criar_frete()

    with pytest.raises(ValueError):
        repository.atualizar_dados_carga(
            frete_id,
            tipo,
            peso,
            valor,
            comentarios,
        )


def test_atualizar_dados_carga_rejeita_frete_inexistente(banco_fretes):
    with pytest.raises(ValueError, match="Frete não encontrado"):
        repository.atualizar_dados_carga(
            999,
            "batida",
            1000,
        )


def test_atualizar_dados_carga_rejeita_frete_em_oferta(banco_fretes):
    frete_id = criar_frete(status="em_oferta")

    with pytest.raises(ValueError, match="Retire a oferta antes de editar"):
        repository.atualizar_dados_carga(
            frete_id,
            "batida",
            1000,
        )


def test_atualizar_dados_carga_aceita_campos_opcionais_vazios(
    banco_fretes,
):
    frete_id = criar_frete()

    resultado = repository.atualizar_dados_carga(
        frete_id,
        "batida",
        "",
        "",
        None,
    )

    assert resultado["peso_liquido_kg"] is None
    assert resultado["valor_inicial_negociacao"] is None
    assert resultado["comentarios_carga"] == ""


# ============================================================
# FECHAMENTO SAP E CONCLUSÃO
# ============================================================

def test_confirmar_sap_registra_fechamento_e_altera_status(banco_fretes):
    frete_id = criar_frete(status="negociacao")
    proposta_id = criar_proposta(
        frete_id,
        "Transportadora A",
        1500,
    )

    aceitar_proposta(frete_id, proposta_id)
    repository.confirmar_sap(frete_id, "SAP-12345")

    fechamento = repository.obter_fechamento(frete_id)

    assert fechamento["frete_id"] == frete_id
    assert fechamento["proposta_id"] == proposta_id
    assert fechamento["referencia_sap"] == "SAP-12345"

    estado = repository.obter_estado_frete(frete_id)
    assert estado["status"] == "cotacao_aceita"


def test_confirmar_sap_rejeita_frete_inexistente(banco_fretes):
    with pytest.raises(ValueError, match="Frete não está em negociação"):
        repository.confirmar_sap(999, "SAP-123")


def test_confirmar_sap_rejeita_frete_sem_proposta_aceita(banco_fretes):
    frete_id = criar_frete(status="negociacao")

    with pytest.raises(ValueError, match="Aceite uma proposta primeiro"):
        repository.confirmar_sap(frete_id, "SAP-123")


def test_confirmar_sap_rejeita_fechamento_duplicado(banco_fretes):
    frete_id = criar_frete(status="negociacao")
    proposta_id = criar_proposta(
        frete_id,
        "Transportadora A",
    )

    aceitar_proposta(frete_id, proposta_id)
    repository.confirmar_sap(frete_id, "SAP-123")

    with pytest.raises(ValueError, match="Frete já possui fechamento"):
        repository.confirmar_sap(frete_id, "SAP-456")


def test_concluir_frete_registra_transicao(banco_fretes):
    frete_id = criar_frete(status="cotacao_aceita")

    assert repository.concluir_frete(frete_id) is True

    estado = repository.obter_estado_frete(frete_id)
    assert estado["status"] == "concluido"


def test_concluir_frete_rejeita_status_incorreto(banco_fretes):
    frete_id = criar_frete(status="em_preparacao")

    with pytest.raises(ValueError, match="Somente fretes com cotação aceita"):
        repository.concluir_frete(frete_id)


def test_concluir_frete_rejeita_frete_inexistente(banco_fretes):
    with pytest.raises(ValueError, match="Frete não encontrado"):
        repository.concluir_frete(999)


# ============================================================
# CONSULTA DE PROPOSTAS POR TRANSPORTADORA
# ============================================================

def test_list_propose_send_filtra_transportadora_sem_diferenciar_caixa(
    banco_fretes,
):
    frete_id = criar_frete(status="em_oferta")

    repository.registrar_proposta(
        frete_id,
        "Transportadora A",
        1500,
    )

    resultado = repository.list_propose_send("transportadora a")

    assert len(resultado) == 1
    assert resultado[0]["id"] == frete_id
    assert resultado[0]["status_negociacao"] == "aguardando_operador"


def test_list_propose_send_retorna_lista_vazia_para_transportadora_sem_propostas(
    banco_fretes,
):
    assert repository.list_propose_send("Transportadora inexistente") == []



def test_delete_base_remove_todos_os_registros_relacionados(banco_fretes):
    from services.db import connect

    frete_id = criar_frete(status="negociacao")
    proposta_id = criar_proposta(
        frete_id,
        "Transportadora A",
    )

    repository.aceitar_proposta(frete_id, proposta_id)

    # Confirma que existe histórico antes da limpeza.
    with connect("fretes") as conn:
        historico_antes = conn.execute("""
            SELECT COUNT(*)
            FROM fretes_negociacao_historico
        """).fetchone()[0]

    assert historico_antes > 0

    # Executa a limpeza.
    repository.delete_base()

    # Verifica se todas as tabelas foram esvaziadas.
    with connect("fretes") as conn:
        tabelas = [
            "fretes_fechamentos",
            "fretes_historico_status",
            "fretes_negociacao_historico",
            "fretes_propostas",
            "fretes_transportadoras_negociacao",
            "fretes",
        ]

        for tabela in tabelas:
            total = conn.execute(
                f"SELECT COUNT(*) FROM {tabela}"
            ).fetchone()[0]

            assert total == 0, (
                f"A tabela {tabela} ainda possui {total} registros"
            )




def test_confirmar_sap_rejeita_frete_fora_de_negociacao(banco_fretes):
    frete_id = criar_frete(status="disponivel")

    with pytest.raises(
        ValueError,
        match="Frete não está em negociação",
    ):
        repository.confirmar_sap(frete_id, "SAP-123")




def test_inicializar_banco_migra_propostas_legadas(isolated_databases):
    import sqlite3

    caminho = isolated_databases["fretes"]

    # Cria um banco legado sem as colunas adicionadas pela migração.
    with sqlite3.connect(caminho) as conn:
        conn.execute("""
            CREATE TABLE fretes (
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
            CREATE TABLE fretes_propostas (
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

        conn.execute("""
            INSERT INTO fretes (
                chave_origem,
                status,
                dados_json
            )
            VALUES ('frete-legado', 'negociacao', '{}')
        """)

        conn.execute("""
            INSERT INTO fretes_propostas (
                frete_id,
                transportadora,
                valor,
                aceita,
                criado_em
            )
            VALUES (
                1,
                'Transportadora Legada',
                1500,
                1,
                '2025-01-15 10:30:00'
            )
        """)

    # Executa a migração sobre o banco legado.
    repository.inicializar_banco()

    from services.db import connect

    with connect("fretes") as conn:
        proposta = conn.execute("""
            SELECT
                status_negociacao,
                atualizado_em,
                aceita
            FROM fretes_propostas
            WHERE id = 1
        """).fetchone()

    assert proposta["status_negociacao"] == "aceita"
    assert proposta["atualizado_em"] == "2025-01-15 10:30:00"
    assert proposta["aceita"] == 1

    # Executar novamente verifica que a migração é idempotente.
    repository.inicializar_banco()

    with connect("fretes") as conn:
        proposta_reprocessada = conn.execute("""
            SELECT
                status_negociacao,
                atualizado_em
            FROM fretes_propostas
            WHERE id = 1
        """).fetchone()

    assert proposta_reprocessada["status_negociacao"] == "aceita"
    assert proposta_reprocessada["atualizado_em"] == "2025-01-15 10:30:00"



def test_salvar_fretes_recupera_json_existente_invalido(banco_fretes):
    import json

    frete = frete_importacao()

    primeiro = repository.salvar_fretes([frete])
    assert primeiro["inseridos"] == 1

    # Simula um registro legado com JSON corrompido.
    with connect("fretes") as conn:
        conn.execute("""
            UPDATE fretes
            SET dados_json = '{json-invalido'
            WHERE chave_origem = ?
        """, (repository.chave_do_frete(frete),))

    # Reimporta o mesmo frete.
    resultado = repository.salvar_fretes([frete_importacao()])

    assert resultado["inseridos"] == 0
    assert resultado["atualizados"] == 1

    with connect("fretes") as conn:
        registro = conn.execute("""
            SELECT dados_json
            FROM fretes
            WHERE chave_origem = ?
        """, (repository.chave_do_frete(frete),)).fetchone()

    dados = json.loads(registro["dados_json"])
    assert isinstance(dados, dict)



def test_chave_do_frete_sem_numero_aceita_pedidos_em_texto():
    frete = frete_importacao(numero=None)
    frete["pedidos"] = "PED-001"

    chave = repository.chave_do_frete(frete)

    assert isinstance(chave, str)
    assert len(chave) == 64
    assert chave == repository.chave_do_frete(frete)
