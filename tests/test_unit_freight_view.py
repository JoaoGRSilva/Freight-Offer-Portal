
from services import freight_view


def test_get_freight_view_data_returns_none_when_freight_not_found(
    monkeypatch,
):
    monkeypatch.setattr(
        freight_view,
        "get_freight",
        lambda freight_id: None,
    )

    response = freight_view.get_freight_view_data(10)

    assert response is None


def test_get_freight_view_data_returns_prepared_data(monkeypatch):
    freight_record = {
        "id": 10,
        "status": "negociacao",
        "numero_frete": "FRETE-001",
        "origem": "São Paulo",
        "destino": "Campinas",
        "transportadora_escolhida": "Transportadora A",
        "dados_json": '{"peso_kg": 1000}',
        "detalhes": {
            "peso_kg": 1000,
            "origem": "Santos",
            "recomendacao": {
                "transportadora": "Transportadora B",
            },
        },
    }

    propostas = [{"id": 1, "valor": 1500}]
    fechamento = {"valor_final": 1400}

    monkeypatch.setattr(
        freight_view,
        "get_freight",
        lambda freight_id: freight_record,
    )
    monkeypatch.setattr(
        freight_view,
        "list_proposals",
        lambda freight_id: propostas,
    )
    monkeypatch.setattr(
        freight_view,
        "get_freight_closure",
        lambda freight_id: fechamento,
    )

    response = freight_view.get_freight_view_data(10)

    assert response["frete"]["db_id"] == 10
    assert response["frete"]["status_db"] == "negociacao"
    assert response["frete"]["num"] == "FRETE-001"
    assert response["frete"]["origem"] == "Santos"
    assert response["frete"]["destino"] == "Campinas"
    assert response["frete"]["transportadora_escolhida"] == "Transportadora A"

    assert response["frete"]["recomendacao"] == {
        "transportadora": "Transportadora B",
    }

    assert response["registro"]["id"] == 10
    assert "dados_json" not in response["registro"]
    assert "detalhes" not in response["registro"]

    assert response["propostas"] == propostas
    assert response["fechamento"] == fechamento


def test_get_freight_view_data_uses_record_origin_and_destination(
    monkeypatch,
):
    freight_record = {
        "id": 20,
        "status": "em_preparacao",
        "numero_frete": None,
        "origem": "São Paulo",
        "destino": "Rio de Janeiro",
        "detalhes": {},
    }

    monkeypatch.setattr(
        freight_view,
        "get_freight",
        lambda freight_id: freight_record,
    )
    monkeypatch.setattr(
        freight_view,
        "list_proposals",
        lambda freight_id: [],
    )
    monkeypatch.setattr(
        freight_view,
        "get_freight_closure",
        lambda freight_id: None,
    )

    response = freight_view.get_freight_view_data(20)

    assert response["frete"]["origem"] == "São Paulo"
    assert response["frete"]["destino"] == "Rio de Janeiro"
    assert response["frete"]["num"] is None


def test_get_freight_view_data_normalizes_invalid_recommendation(
    monkeypatch,
):
    freight_record = {
        "id": 30,
        "status": "em_preparacao",
        "detalhes": {
            "recomendacao": "recomendação inválida",
        },
    }

    monkeypatch.setattr(
        freight_view,
        "get_freight",
        lambda freight_id: freight_record,
    )
    monkeypatch.setattr(
        freight_view,
        "list_proposals",
        lambda freight_id: [],
    )
    monkeypatch.setattr(
        freight_view,
        "get_freight_closure",
        lambda freight_id: None,
    )

    response = freight_view.get_freight_view_data(30)

    assert response["frete"]["recomendacao"] == {}


def test_get_freight_view_data_does_not_modify_original_record(
    monkeypatch,
):
    detalhes = {
        "peso_kg": 2000,
        "origem": "Curitiba",
    }

    freight_record = {
        "id": 40,
        "status": "em_preparacao",
        "detalhes": detalhes,
    }

    monkeypatch.setattr(
        freight_view,
        "get_freight",
        lambda freight_id: freight_record,
    )
    monkeypatch.setattr(
        freight_view,
        "list_proposals",
        lambda freight_id: [],
    )
    monkeypatch.setattr(
        freight_view,
        "get_freight_closure",
        lambda freight_id: None,
    )

    freight_view.get_freight_view_data(40)

    assert "db_id" not in detalhes
    assert "status_db" not in detalhes
    assert "recomendacao" not in detalhes
