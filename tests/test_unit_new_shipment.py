
import math
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import io
import numpy as np
import pandas as pd
import pytest
from flask import Flask


@pytest.fixture
def shipment_module():
    import routes.new_shipment as module
    return module


@pytest.fixture
def shipment_client(shipment_module, monkeypatch):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
    )
    app.register_blueprint(shipment_module.nova_carga_bp)

    user = SimpleNamespace(
        can_access_plant=Mock(return_value=True)
    )
    monkeypatch.setattr(shipment_module, "current_user", user)

    return app.test_client(), user


def ajax_headers():
    return {"X-Requested-With": "XMLHttpRequest"}


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

class TestCalcular:

    def test_calcular_chama_calcular_custos_com_dados_do_frete(
        self, shipment_module, monkeypatch
    ):
        esperado = {"antt": 100, "mercado": 120}
        mock = Mock(return_value=esperado)
        monkeypatch.setattr(shipment_module, "calcular_custos", mock)

        frete = {
            "id": 10,
            "uf": "SP",
            "peso_kg": 15000,
            "eixos": 5,
            "categoria": "carga_geral",
            "trechos": [{"distancia_km": 100}],
        }

        resultado = shipment_module._calcular(frete)

        assert resultado == esperado
        mock.assert_called_once_with(
            uf="SP",
            peso_kg=15000,
            eixos=5,
            categoria="carga_geral",
            trechos=frete["trechos"],
        )

    def test_calcular_prioriza_trechos_recebidos(
        self, shipment_module, monkeypatch
    ):
        mock = Mock(return_value={"antt": 100})
        monkeypatch.setattr(shipment_module, "calcular_custos", mock)

        frete = {
            "uf": "MG",
            "peso_kg": 1000,
            "eixos": 3,
            "categoria": "geral",
            "trechos": [{"distancia_km": 10}],
        }
        trechos = [{"distancia_km": 500}]

        shipment_module._calcular(frete, trechos=trechos)

        assert mock.call_args.kwargs["trechos"] == trechos

    def test_calcular_retorna_calculo_vazio_em_erro(
        self, shipment_module, monkeypatch
    ):
        monkeypatch.setattr(
            shipment_module,
            "calcular_custos",
            Mock(side_effect=RuntimeError("erro")),
        )

        resultado = shipment_module._calcular(
            {
                "id": 99,
                "uf": "SP",
                "peso_kg": 1000,
                "eixos": 3,
                "categoria": "geral",
                "trechos": [],
            }
        )

        assert resultado == shipment_module.CALCULO_VAZIO
        assert resultado is not shipment_module.CALCULO_VAZIO


class TestCustosDoFrete:

    def test_usa_calculo_original_quando_tem_trechos_e_eixos(
        self, shipment_module, monkeypatch
    ):
        esperado = {"antt": 100}
        mock = Mock(return_value=esperado)
        monkeypatch.setattr(shipment_module, "_calcular", mock)

        frete = {"trechos": [{"distancia_km": 10}], "eixos": 5}

        assert shipment_module._custos_do_frete(frete) == esperado
        mock.assert_called_once_with(frete)

    def test_retorna_vazio_quando_nao_tem_km_trechos(
        self, shipment_module
    ):
        assert shipment_module._custos_do_frete({}) == (
            shipment_module.CALCULO_VAZIO
        )

    def test_retorna_vazio_quando_recomendacao_caminhao_falha(
        self, shipment_module, monkeypatch
    ):
        monkeypatch.setattr(
            shipment_module,
            "recomendar_caminhao",
            Mock(side_effect=RuntimeError("erro")),
        )

        resultado = shipment_module._custos_do_frete(
            {"km_trechos": [100], "peso_kg": 1000}
        )

        assert resultado == shipment_module.CALCULO_VAZIO

    @pytest.mark.parametrize(
        "caminhao",
        [
            {},
            {"eixos": None},
            {"eixos": 0},
            {"eixos": 5, "excede": True},
        ],
    )
    def test_retorna_vazio_quando_caminhao_nao_pode_ser_usado(
        self, shipment_module, monkeypatch, caminhao
    ):
        monkeypatch.setattr(
            shipment_module,
            "recomendar_caminhao",
            Mock(return_value=caminhao),
        )

        resultado = shipment_module._custos_do_frete(
            {"km_trechos": [100], "peso_kg": 1000}
        )

        assert resultado == shipment_module.CALCULO_VAZIO

    def test_retorna_vazio_quando_categoria_padrao_e_none(
        self, shipment_module, monkeypatch
    ):
        monkeypatch.setattr(
            shipment_module,
            "recomendar_caminhao",
            Mock(return_value={"eixos": 5}),
        )
        monkeypatch.setattr(shipment_module, "CATEGORIA_PADRAO", None)

        frete = {"km_trechos": [100], "peso_kg": 1000}

        assert shipment_module._custos_do_frete(frete) == (
            shipment_module.CALCULO_VAZIO
        )

    def test_monta_trechos_e_calcula_custos(
        self, shipment_module, monkeypatch
    ):
        monkeypatch.setattr(
            shipment_module,
            "recomendar_caminhao",
            Mock(return_value={"eixos": 5}),
        )
        monkeypatch.setattr(
            shipment_module,
            "CATEGORIA_PADRAO",
            "geral",
        )
        monkeypatch.setattr(
            shipment_module,
            "PAVIMENTO_PADRAO",
            "pavimentado",
        )

        mock = Mock(return_value={"antt": 500})
        monkeypatch.setattr(shipment_module, "_calcular", mock)

        frete = {
            "peso_kg": 15000,
            "km_trechos": [100, 200],
        }

        resultado = shipment_module._custos_do_frete(frete)

        assert resultado == {"antt": 500}
        assert frete["eixos"] == 5
        assert frete["categoria"] == "geral"

        mock.assert_called_once_with(
            frete,
            trechos=[
                {"distancia_km": 100, "pavimento": "pavimentado"},
                {"distancia_km": 200, "pavimento": "pavimentado"},
            ],
        )


class TestJsonSafe:

    def test_converte_dicionario_recursivamente(self, shipment_module):
        resultado = shipment_module._json_safe({
            "inteiro": np.int64(10),
            "flutuante": np.float64(2.5),
            "lista": (np.int32(3), None),
            "nan": float("nan"),
            "nulo": pd.NA,
        })

        assert resultado == {
            "inteiro": 10,
            "flutuante": 2.5,
            "lista": [3, None],
            "nan": None,
            "nulo": None,
        }

    def test_converte_timestamp_para_data(self, shipment_module):
        timestamp = pd.Timestamp("2025-03-15 10:30:00")

        assert shipment_module._json_safe(timestamp) == "2025-03-15"

    def test_converte_float_infinito_sem_alterar(
        self, shipment_module
    ):
        assert shipment_module._json_safe(float("inf")) == float("inf")
        assert shipment_module._json_safe(float("-inf")) == float("-inf")

    def test_preserva_valores_comuns(self, shipment_module):
        objeto = object()

        assert shipment_module._json_safe("texto") == "texto"
        assert shipment_module._json_safe(10) == 10
        assert shipment_module._json_safe(True) is True
        assert shipment_module._json_safe(objeto) is objeto

    def test_converte_lista_e_tupla(self, shipment_module):
        assert shipment_module._json_safe((1, 2, (3,))) == [1, 2, [3]]

    def test_nao_converte_nan_de_numpy_para_valor_invalido(
        self, shipment_module
    ):
        assert shipment_module._json_safe(np.float64("nan")) is None


class TestParaCard:

    def test_converte_frete_para_card(self, shipment_module):
        frete = {
            "pedidos": ["100", "200"],
            "planta": {"cidade": "Campinas"},
            "transfer_planta": {"cidade": "Jundiaí"},
            "calculo": {"antt": 100},
            "num": "F001",
        }

        resultado = shipment_module._para_card(frete, 7)

        assert resultado["id"] == 7
        assert resultado["pedido"] == "100, 200"
        assert resultado["origem"] == "Campinas"
        assert resultado["transfer"] == "Jundiaí"
        assert resultado["calculo"] == {"antt": 100}
        assert resultado["num"] == "F001"

    def test_card_sem_transferencia(self, shipment_module):
        frete = {
            "pedidos": [],
            "planta": {"cidade": "Santos"},
            "transfer_planta": None,
        }

        resultado = shipment_module._para_card(frete, 1)

        assert resultado["transfer"] is None
        assert resultado["pedido"] == ""

    def test_card_sem_calculo_usa_dicionario_vazio(
        self, shipment_module
    ):
        frete = {
            "pedidos": [],
            "planta": {"cidade": "Santos"},
            "transfer_planta": None,
        }

        assert shipment_module._para_card(frete, 1)["calculo"] == {}


class TestRecomendarTodos:

    def test_processa_fretes_e_contabiliza_sugestoes(
        self, shipment_module, monkeypatch
    ):
        monkeypatch.setattr(
            shipment_module,
            "preencher_cep",
            Mock(),
        )
        monkeypatch.setattr(
            shipment_module,
            "_custos_do_frete",
            Mock(return_value={"distancia_total_km": 100}),
        )
        monkeypatch.setattr(
            shipment_module,
            "recomendar",
            Mock(side_effect=[
                {"transportadora": "Transportadora A"},
                {"transportadora": "—"},
                None,
            ]),
        )

        fretes = [
            {"num": "A", "km_estimado": 90},
            {"num": "B", "km_estimado": 80},
            {"num": "C", "km_estimado": 70},
        ]

        resultado = shipment_module._recomendar_todos(fretes)

        assert resultado == 1
        assert [f["id"] for f in fretes] == [1, 2, 3]
        assert all("calculo" in f for f in fretes)
        assert fretes[0]["recomendacao"]["transportadora"] == (
            "Transportadora A"
        )

    def test_usa_km_estimado_quando_calculo_nao_tem_distancia(
        self, shipment_module, monkeypatch
    ):
        monkeypatch.setattr(shipment_module, "preencher_cep", Mock())
        monkeypatch.setattr(
            shipment_module,
            "_custos_do_frete",
            Mock(return_value={"distancia_total_km": None}),
        )
        monkeypatch.setattr(
            shipment_module,
            "recomendar",
            Mock(return_value=None),
        )

        fretes = [{"num": "A", "km_estimado": 250}]

        shipment_module._recomendar_todos(fretes)

        assert fretes[0]["calculo"]["distancia_total_km"] == 250

    def test_trata_excecao_na_recomendacao(
        self, shipment_module, monkeypatch
    ):
        monkeypatch.setattr(shipment_module, "preencher_cep", Mock())
        monkeypatch.setattr(
            shipment_module,
            "_custos_do_frete",
            Mock(return_value={}),
        )
        monkeypatch.setattr(
            shipment_module,
            "recomendar",
            Mock(side_effect=RuntimeError("falha")),
        )

        fretes = [{"num": "A"}]

        resultado = shipment_module._recomendar_todos(fretes)

        assert resultado == 0
        assert fretes[0]["recomendacao"] is None

    def test_contabiliza_recomendacao_com_transportadora_vazia(
        self, shipment_module, monkeypatch
    ):
        monkeypatch.setattr(shipment_module, "preencher_cep", Mock())
        monkeypatch.setattr(
            shipment_module,
            "_custos_do_frete",
            Mock(return_value={}),
        )
        monkeypatch.setattr(
            shipment_module,
            "recomendar",
            Mock(return_value={"transportadora": None}),
        )

        assert shipment_module._recomendar_todos([{"num": "A"}]) == 0

    def test_trata_transportadora_com_traco_longo(
        self, shipment_module, monkeypatch
    ):
        monkeypatch.setattr(shipment_module, "preencher_cep", Mock())
        monkeypatch.setattr(
            shipment_module,
            "_custos_do_frete",
            Mock(return_value={}),
        )
        monkeypatch.setattr(
            shipment_module,
            "recomendar",
            Mock(return_value={"transportadora": "—"}),
        )

        assert shipment_module._recomendar_todos([{"num": "A"}]) == 0

    def test_lista_vazia(self, shipment_module):
        assert shipment_module._recomendar_todos([]) == 0


# ============================================================
# ROTA PRINCIPAL
# ============================================================

class TestNovaCarga:

    def test_carrega_fretes_propostas_e_fechamento(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client

        fretes = [
            {"db_id": 10, "num": "A"},
            {"db_id": 20, "num": "B"},
        ]

        monkeypatch.setattr(shipment_module, "inicializar_banco", Mock())
        monkeypatch.setattr(
            shipment_module,
            "authorized_plants",
            Mock(return_value=["1304"]),
        )
        monkeypatch.setattr(
            shipment_module,
            "listar_fretes_preparacao",
            Mock(return_value=fretes),
        )
        monkeypatch.setattr(
            shipment_module,
            "listar_propostas",
            Mock(side_effect=[[{"id": 1}], []]),
        )
        monkeypatch.setattr(
            shipment_module,
            "obter_fechamento",
            Mock(side_effect=[{"status": "aberto"}, None]),
        )
        monkeypatch.setattr(
            shipment_module,
            "render_template",
            Mock(return_value="Página renderizada"),
        )

        response = client.get("/nova-carga")

        assert response.status_code == 200
        assert fretes[0]["id"] == 1
        assert fretes[1]["id"] == 2
        assert fretes[0]["propostas"] == [{"id": 1}]
        assert fretes[1]["propostas"] == []
        assert fretes[0]["fechamento"] == {"status": "aberto"}
        assert fretes[1]["fechamento"] is None
        assert response.get_data(as_text=True) == "Página renderizada"

        shipment_module.render_template.assert_called_once_with(
            "new-shipment.html",
            fretes=fretes,
        )


# ============================================================
# UPLOAD
# ============================================================


class TestUpload:

    def test_upload_sem_arquivo(self, shipment_client):
        client, _ = shipment_client

        response = client.post("/nova-carga/upload")

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/nova-carga")

    def test_upload_sem_nome_de_arquivo(
        self, shipment_client
    ):
        client, _ = shipment_client

        response = client.post(
            "/nova-carga/upload",
            data={
                "basedefretes": (io.BytesIO(b""), "")
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 302

    def test_upload_sem_codigo_de_planta(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client

        monkeypatch.setattr(
            "analytics.plants.extrair_codigo",
            Mock(return_value=None),
        )

        response = client.post(
            "/nova-carga/upload",
            data={
                "basedefretes": (
                    io.BytesIO(b"conteudo"),
                    "arquivo.xlsx",
                ),
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 302

    def test_upload_planta_nao_autorizada(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, user = shipment_client
        user.can_access_plant.return_value = False

        monkeypatch.setattr(
            "analytics.plants.extrair_codigo",
            Mock(return_value="1304"),
        )

        response = client.post(
            "/nova-carga/upload",
            data={
                "basedefretes": (
                    io.BytesIO(b"conteudo"),
                    "fretes_1304.xlsx",
                ),
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/nova-carga")
        user.can_access_plant.assert_called_once_with("1304")

        with client.session_transaction() as sess:
            flashes = sess.get("_flashes", [])

        assert any(
            "não autorizada" in mensagem.lower()
            for _, mensagem in flashes
        )

    def test_upload_planta_inativa(
        self, shipment_client, monkeypatch
    ):
        client, _ = shipment_client

        monkeypatch.setattr(
            "analytics.plants.extrair_codigo",
            Mock(return_value="1304"),
        )

        monkeypatch.setattr(
            "services.plant_repository.get_usable_plant",
            Mock(return_value=None),
        )

        response = client.post(
            "/nova-carga/upload",
            data={
                "basedefretes": (
                    io.BytesIO(b"conteudo"),
                    "fretes_1304.xlsx",
                ),
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 302

    @pytest.mark.parametrize(
        "filename",
        [
            "fretes_1304.txt",
            "fretes_1304.pdf",
            "fretes_1304.xls",
            "fretes_1304.json",
        ],
    )
    def test_upload_rejeita_extensao_nao_permitida(
        self, shipment_client, monkeypatch, filename
    ):
        client, _ = shipment_client

        monkeypatch.setattr(
            "analytics.plants.extrair_codigo",
            Mock(return_value="1304"),
        )

        monkeypatch.setattr(
            "services.plant_repository.get_usable_plant",
            Mock(return_value={"codigo": "1304"}),
        )

        response = client.post(
            "/nova-carga/upload",
            data={
                "basedefretes": (
                    io.BytesIO(b"conteudo"),
                    filename,
                ),
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 302

    def test_upload_rejeita_frete_de_planta_nao_autorizada(
        self, shipment_module, shipment_client, monkeypatch, tmp_path
    ):
        client, user = shipment_client

        monkeypatch.setattr(
            "analytics.plants.extrair_codigo",
            Mock(return_value="1304"),
        )

        monkeypatch.setattr(
            "services.plant_repository.get_usable_plant",
            Mock(return_value={"codigo": "1304"}),
        )

        monkeypatch.setattr(
            shipment_module,
            "PASTA_UPLOAD",
            tmp_path,
        )

        monkeypatch.setattr(
            shipment_module,
            "process_fretes",
            Mock(
                return_value={
                    "fretes": [
                        {"planta": {"codigo": "9999"}}
                    ],
                    "ignorados": [],
                    "erros": [],
                }
            ),
        )

        monkeypatch.setattr(
            shipment_module,
            "plant_code",
            Mock(return_value="9999"),
        )

        user.can_access_plant.side_effect = [True, False]

        response = client.post(
            "/nova-carga/upload",
            data={
                "basedefretes": (
                    io.BytesIO(b"conteudo"),
                    "fretes_1304.xlsx",
                ),
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 302
        assert list(tmp_path.iterdir()) == []

    def test_upload_com_sucesso_sem_fretes(
        self, shipment_module, shipment_client, monkeypatch, tmp_path
    ):
        client, _ = shipment_client

        monkeypatch.setattr(
            "analytics.plants.extrair_codigo",
            Mock(return_value="1304"),
        )

        monkeypatch.setattr(
            "services.plant_repository.get_usable_plant",
            Mock(return_value={"codigo": "1304"}),
        )

        monkeypatch.setattr(
            shipment_module,
            "PASTA_UPLOAD",
            tmp_path,
        )

        mock_processar = Mock(
            return_value={
                "fretes": [],
                "ignorados": [],
                "erros": [],
            }
        )
        monkeypatch.setattr(
            shipment_module,
            "process_fretes",
            mock_processar,
        )

        mock_enriquecer = Mock(return_value=[])
        monkeypatch.setattr(
            shipment_module,
            "enriquecer_localizacoes",
            mock_enriquecer,
        )

        monkeypatch.setattr(
            shipment_module,
            "_recomendar_todos",
            Mock(return_value=0),
        )

        monkeypatch.setattr(
            shipment_module,
            "inicializar_banco",
            Mock(),
        )

        monkeypatch.setattr(
            shipment_module,
            "salvar_fretes",
            Mock(
                return_value={
                    "inseridos": 0,
                    "atualizados": 0,
                }
            ),
        )

        monkeypatch.setattr(
            shipment_module,
            "obter_id_por_chave",
            Mock(return_value=None),
        )

        response = client.post(
            "/nova-carga/upload",
            data={
                "basedefretes": (
                    io.BytesIO(b"conteudo"),
                    "fretes_1304.xlsx",
                ),
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/nova-carga")

        mock_processar.assert_called_once()
        mock_enriquecer.assert_called_once()

        arquivos = list(tmp_path.iterdir())
        assert len(arquivos) == 1
        assert arquivos[0].is_file()

    
    def test_upload_com_sucesso_com_fretes(
        self, shipment_module, shipment_client, monkeypatch, tmp_path
    ):
        client, user = shipment_client

        monkeypatch.setattr(
            "analytics.plants.extrair_codigo",
            Mock(return_value="1304"),
        )

        monkeypatch.setattr(
            "services.plant_repository.get_usable_plant",
            Mock(return_value={"codigo": "1304"}),
        )

        monkeypatch.setattr(
            shipment_module,
            "PASTA_UPLOAD",
            tmp_path,
        )

        fretes = [
            {"planta": {"codigo": "1304"}}
        ]

        monkeypatch.setattr(
            shipment_module,
            "process_fretes",
            Mock(
                return_value={
                    "fretes": fretes,
                    "ignorados": [],
                    "erros": [],
                }
            ),
        )

        monkeypatch.setattr(
            shipment_module,
            "plant_code",
            Mock(return_value="1304"),
        )

        monkeypatch.setattr(
            shipment_module,
            "enriquecer_localizacoes",
            Mock(return_value=fretes),
        )

        monkeypatch.setattr(
            shipment_module,
            "_recomendar_todos",
            Mock(return_value=0),
        )

        monkeypatch.setattr(
            shipment_module,
            "_para_card",
            Mock(return_value={"frete": "teste"}),
        )

        monkeypatch.setattr(
            shipment_module,
            "inicializar_banco",
            Mock(),
        )

        mock_salvar = Mock(
            return_value={
                "inseridos": 1,
                "atualizados": 0,
            }
        )
        monkeypatch.setattr(
            shipment_module,
            "salvar_fretes",
            mock_salvar,
        )

        monkeypatch.setattr(
            shipment_module,
            "chave_do_frete",
            Mock(return_value="chave-teste"),
        )

        mock_obter_id = Mock(return_value=123)
        monkeypatch.setattr(
            shipment_module,
            "obter_id_por_chave",
            mock_obter_id,
        )

        response = client.post(
            "/nova-carga/upload",
            data={
                "basedefretes": (
                    io.BytesIO(b"conteudo"),
                    "fretes_1304.xlsx",
                ),
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/nova-carga")

        mock_salvar.assert_called_once()

        cards_salvos = mock_salvar.call_args.args[0]
        assert len(cards_salvos) == 1

        card = cards_salvos[0]

        assert card["tipo_carga"] == "batida"
        assert card["peso_liquido_kg"] is None
        assert card["valor_inicial_negociacao"] is None
        assert card["comentarios_carga"] == ""

        mock_obter_id.assert_called_once_with("chave-teste")
        assert card["db_id"] == 123


    def test_upload_trata_erro_no_processamento(
        self, shipment_module, shipment_client, monkeypatch, tmp_path
    ):
        client, _ = shipment_client

        monkeypatch.setattr(
            "analytics.plants.extrair_codigo",
            Mock(return_value="1304"),
        )

        monkeypatch.setattr(
            "services.plant_repository.get_usable_plant",
            Mock(return_value={"codigo": "1304"}),
        )

        monkeypatch.setattr(
            shipment_module,
            "PASTA_UPLOAD",
            tmp_path,
        )

        monkeypatch.setattr(
            shipment_module,
            "process_fretes",
            Mock(
                side_effect=RuntimeError(
                    "erro de processamento"
                )
            ),
        )

        response = client.post(
            "/nova-carga/upload",
            data={
                "basedefretes": (
                    io.BytesIO(b"conteudo"),
                    "fretes_1304.xlsx",
                ),
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/nova-carga")

    def test_upload_trata_erro_ao_salvar_arquivo(
        self, shipment_module, shipment_client, monkeypatch, tmp_path
    ):
        client, _ = shipment_client

        monkeypatch.setattr(
            "analytics.plants.extrair_codigo",
            Mock(return_value="1304"),
        )

        monkeypatch.setattr(
            "services.plant_repository.get_usable_plant",
            Mock(return_value={"codigo": "1304"}),
        )

        monkeypatch.setattr(
            shipment_module,
            "PASTA_UPLOAD",
            tmp_path,
        )

        response = client.post(
            "/nova-carga/upload",
            data={
                "basedefretes": (
                    io.BytesIO(b"conteudo"),
                    "fretes_1304.xlsx",
                ),
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/nova-carga")


# ============================================================
# LIMPAR BASE
# ============================================================

class TestLimpar:

    def test_limpar_exclui_base_e_redireciona(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client
        mock = Mock()
        monkeypatch.setattr(shipment_module, "delete_base", mock)

        response = client.post("/nova-carga/limpar")

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/nova-carga")
        mock.assert_called_once_with()


# ============================================================
# REGISTRO DE PROPOSTAS
# ============================================================

class TestNovaProposta:

    def test_registra_proposta_ajax(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client

        monkeypatch.setattr(
            shipment_module,
            "registrar_proposta",
            Mock(return_value=123),
        )
        monkeypatch.setattr(
            shipment_module,
            "listar_propostas",
            Mock(return_value=[{"id": 123}]),
        )

        response = client.post(
            "/nova-carga/fretes/10/propostas",
            headers=ajax_headers(),
            data={
                "transportadora": "  Empresa A  ",
                "valor": "1234,56",
                "prazo_dias": "30",
                "observacoes": "  observação  ",
            },
        )

        assert response.status_code == 201
        data = response.get_json()

        assert data["sucesso"] is True
        assert data["proposta_id"] == 123
        assert data["propostas"] == [{"id": 123}]

        shipment_module.registrar_proposta.assert_called_once_with(
            frete_id=10,
            transportadora="Empresa A",
            valor=1234.56,
            prazo_dias=30,
            observacoes="observação",
        )

    def test_registra_proposta_sem_prazo(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client

        monkeypatch.setattr(
            shipment_module,
            "registrar_proposta",
            Mock(return_value=1),
        )
        monkeypatch.setattr(
            shipment_module,
            "listar_propostas",
            Mock(return_value=[]),
        )

        response = client.post(
            "/nova-carga/fretes/1/propostas",
            headers=ajax_headers(),
            data={
                "transportadora": "Empresa A",
                "valor": "1000",
            },
        )

        assert response.status_code == 201
        assert shipment_module.registrar_proposta.call_args.kwargs[
            "prazo_dias"
        ] is None

    @pytest.mark.parametrize(
        "dados",
        [
            {"transportadora": "", "valor": "100"},
            {"transportadora": "Empresa", "valor": ""},
            {"transportadora": "Empresa", "valor": "abc"},
            {"transportadora": "Empresa", "valor": "0"},
            {"transportadora": "Empresa", "valor": "-10"},
            {"transportadora": "Empresa", "valor": "nan"},
            {"transportadora": "Empresa", "valor": "inf"},
            {"transportadora": "Empresa", "valor": "1000000000"},
            {"transportadora": "Empresa", "valor": "100", "prazo_dias": "-1"},
            {"transportadora": "Empresa", "valor": "100", "prazo_dias": "366"},
            {"transportadora": "Empresa", "valor": "100", "prazo_dias": "abc"},
            {"transportadora": "Empresa", "valor": "100", "prazo_dias": "1.5"},
        ],
    )
    def test_rejeita_dados_invalidos(
        self, shipment_client, monkeypatch, dados
    ):
        client, _ = shipment_client

        response = client.post(
            "/nova-carga/fretes/1/propostas",
            headers=ajax_headers(),
            data=dados,
        )

        assert response.status_code == 400
        assert response.get_json()["sucesso"] is False

    def test_trata_overflow_no_valor(
        self, shipment_client
    ):
        client, _ = shipment_client

        response = client.post(
            "/nova-carga/fretes/1/propostas",
            headers=ajax_headers(),
            data={
                "transportadora": "Empresa",
                "valor": "1e9999",
            },
        )

        assert response.status_code == 400

    def test_formulario_tradicional_redireciona(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client

        monkeypatch.setattr(
            shipment_module,
            "registrar_proposta",
            Mock(return_value=1),
        )

        response = client.post(
            "/nova-carga/fretes/1/propostas",
            data={
                "transportadora": "Empresa",
                "valor": "1000",
            },
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/nova-carga")

    def test_erro_no_formulario_tradicional_redireciona(
        self, shipment_module, shipment_client
    ):
        client, _ = shipment_client

        response = client.post(
            "/nova-carga/fretes/1/propostas",
            data={
                "transportadora": "",
                "valor": "1000",
            },
        )

        assert response.status_code == 302


# ============================================================
# ACEITAR PROPOSTA
# ============================================================

class TestAceitarCotacao:

    def test_aceita_proposta_ajax(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client
        mock = Mock()
        monkeypatch.setattr(shipment_module, "aceitar_proposta", mock)

        response = client.post(
            "/nova-carga/fretes/10/propostas/20/aceitar",
            headers=ajax_headers(),
        )

        assert response.status_code == 200
        assert response.get_json()["sucesso"] is True
        mock.assert_called_once_with(10, 20)

    def test_trata_value_error_ajax(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client

        monkeypatch.setattr(
            shipment_module,
            "aceitar_proposta",
            Mock(side_effect=ValueError("proposta inválida")),
        )

        response = client.post(
            "/nova-carga/fretes/10/propostas/20/aceitar",
            headers=ajax_headers(),
        )

        assert response.status_code == 400
        assert response.get_json()["mensagem"] == "proposta inválida"

    def test_trata_erro_interno_ajax(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client

        monkeypatch.setattr(
            shipment_module,
            "aceitar_proposta",
            Mock(side_effect=RuntimeError("erro")),
        )

        response = client.post(
            "/nova-carga/fretes/10/propostas/20/aceitar",
            headers=ajax_headers(),
        )

        assert response.status_code == 500
        assert response.get_json()["sucesso"] is False

    def test_erro_em_formulario_tradicional_redireciona(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client

        monkeypatch.setattr(
            shipment_module,
            "aceitar_proposta",
            Mock(side_effect=ValueError("inválida")),
        )

        response = client.post(
            "/nova-carga/fretes/10/propostas/20/aceitar"
        )

        assert response.status_code == 302

    def test_aceita_proposta_formulario_tradicional(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client
        mock = Mock()

        monkeypatch.setattr(
            shipment_module,
            "aceitar_proposta",
            mock,
        )

        response = client.post(
            "/nova-carga/fretes/10/propostas/20/aceitar"
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/nova-carga")
        mock.assert_called_once_with(10, 20)

        with client.session_transaction() as sess:
            flashes = sess.get("_flashes", [])

        assert any(
            "proposta aceita" in mensagem.lower()
            for _, mensagem in flashes
        )

    def test_trata_erro_interno_formulario_tradicional(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client

        monkeypatch.setattr(
            shipment_module,
            "aceitar_proposta",
            Mock(side_effect=RuntimeError("erro")),
        )

        response = client.post(
            "/nova-carga/fretes/10/propostas/20/aceitar"
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/nova-carga")

        with client.session_transaction() as sess:
            flashes = sess.get("_flashes", [])

        assert any(
            "erro interno ao aceitar a proposta" in mensagem.lower()
            for _, mensagem in flashes
        )


# ============================================================
# CONFIRMAÇÃO SAP
# ============================================================

class TestConfirmarFreteSap:

    def test_confirma_sap_ajax(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client
        mock = Mock()
        monkeypatch.setattr(shipment_module, "confirmar_sap", mock)

        response = client.post(
            "/nova-carga/fretes/10/confirmar-sap",
            headers=ajax_headers(),
            data={"referencia_sap": "  SAP123  "},
        )

        assert response.status_code == 200
        assert response.get_json()["sucesso"] is True
        mock.assert_called_once_with(10, "SAP123")

    def test_rejeita_referencia_vazia_ajax(
        self, shipment_client
    ):
        client, _ = shipment_client

        response = client.post(
            "/nova-carga/fretes/10/confirmar-sap",
            headers=ajax_headers(),
            data={"referencia_sap": "   "},
        )

        assert response.status_code == 400
        assert response.get_json()["sucesso"] is False

    def test_trata_value_error_ajax(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client

        monkeypatch.setattr(
            shipment_module,
            "confirmar_sap",
            Mock(side_effect=ValueError("referência inválida")),
        )

        response = client.post(
            "/nova-carga/fretes/10/confirmar-sap",
            headers=ajax_headers(),
            data={"referencia_sap": "SAP123"},
        )

        assert response.status_code == 400
        assert response.get_json()["mensagem"] == "referência inválida"

    def test_trata_erro_interno_ajax(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client

        monkeypatch.setattr(
            shipment_module,
            "confirmar_sap",
            Mock(side_effect=RuntimeError("erro")),
        )

        response = client.post(
            "/nova-carga/fretes/10/confirmar-sap",
            headers=ajax_headers(),
            data={"referencia_sap": "SAP123"},
        )

        assert response.status_code == 500

    def test_formulario_tradicional_redireciona(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client

        monkeypatch.setattr(
            shipment_module,
            "confirmar_sap",
            Mock(return_value=None),
        )

        response = client.post(
            "/nova-carga/fretes/10/confirmar-sap",
            data={"referencia_sap": "SAP123"},
        )

        assert response.status_code == 302

    def test_trata_value_error_formulario_tradicional(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client

        monkeypatch.setattr(
            shipment_module,
            "confirmar_sap",
            Mock(side_effect=ValueError("referência inválida")),
        )

        response = client.post(
            "/nova-carga/fretes/10/confirmar-sap",
            data={"referencia_sap": "SAP123"},
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/nova-carga")

        with client.session_transaction() as sess:
            flashes = sess.get("_flashes", [])

        assert any(
            "referência inválida" in mensagem.lower()
            for _, mensagem in flashes
        )

    def test_trata_erro_interno_formulario_tradicional(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client

        monkeypatch.setattr(
            shipment_module,
            "confirmar_sap",
            Mock(side_effect=RuntimeError("erro")),
        )

        response = client.post(
            "/nova-carga/fretes/10/confirmar-sap",
            data={"referencia_sap": "SAP123"},
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/nova-carga")

        with client.session_transaction() as sess:
            flashes = sess.get("_flashes", [])

        assert any(
            "erro interno ao confirmar" in mensagem.lower()
            for _, mensagem in flashes
        )


# ============================================================
# INICIAR NEGOCIAÇÃO
# ============================================================

class TestIniciarNegociacao:

    def test_inicia_negociacao_com_sucesso(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client
        mock = Mock()
        monkeypatch.setattr(shipment_module, "iniciar_negociacao", mock)

        response = client.post(
            "/api/nova-carga/fretes/10/negociacao",
            json={"transportadora": "Empresa A"},
        )

        assert response.status_code == 200
        assert response.get_json() == {
            "sucesso": True,
            "status": "negociacao",
            "transportadora": "Empresa A",
        }
        mock.assert_called_once_with(
            frete_id=10,
            transportadora="Empresa A",
        )

    def test_trata_value_error(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client

        monkeypatch.setattr(
            shipment_module,
            "iniciar_negociacao",
            Mock(side_effect=ValueError("transportadora inválida")),
        )

        response = client.post(
            "/api/nova-carga/fretes/10/negociacao",
            json={"transportadora": "Empresa A"},
        )

        assert response.status_code == 400
        assert response.get_json()["erro"] == "transportadora inválida"

    def test_json_ausente(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client
        mock = Mock()
        monkeypatch.setattr(shipment_module, "iniciar_negociacao", mock)

        response = client.post(
            "/api/nova-carga/fretes/10/negociacao",
            data="não é json",
            content_type="text/plain",
        )

        assert response.status_code == 200
        mock.assert_called_once_with(
            frete_id=10,
            transportadora=None,
        )


# ============================================================
# PUBLICAR OFERTA
# ============================================================

class TestPublicarFrete:

    def test_publica_frete_com_sucesso(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client
        mock = Mock(return_value=True)
        monkeypatch.setattr(shipment_module, "publicar_oferta", mock)

        response = client.post("/mesa/fretes/10/publicar")

        assert response.status_code == 200
        assert response.get_json()["sucesso"] is True
        assert response.get_json()["status"] == "em_oferta"
        mock.assert_called_once_with(10)

    @pytest.mark.parametrize("retorno", [False, None, 0])
    def test_publicacao_indisponivel(
        self, shipment_module, shipment_client, monkeypatch, retorno
    ):
        client, _ = shipment_client

        monkeypatch.setattr(
            shipment_module,
            "publicar_oferta",
            Mock(return_value=retorno),
        )

        response = client.post("/mesa/fretes/10/publicar")

        assert response.status_code == 409
        assert response.get_json()["sucesso"] is False


# ============================================================
# RETIRAR OFERTA
# ============================================================

class TestRetirarOferta:

    def test_retira_oferta_com_sucesso(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client
        mock = Mock(return_value=True)
        monkeypatch.setattr(shipment_module, "retirar_oferta", mock)

        response = client.post("/mesa/fretes/10/retirar-oferta")

        assert response.status_code == 200
        assert response.get_json()["sucesso"] is True
        assert response.get_json()["status"] == "em_preparacao"
        mock.assert_called_once_with(10)

    def test_nao_retira_oferta_nao_publicada(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client

        monkeypatch.setattr(
            shipment_module,
            "retirar_oferta",
            Mock(return_value=False),
        )

        response = client.post("/mesa/fretes/10/retirar-oferta")

        assert response.status_code == 409
        assert response.get_json()["sucesso"] is False


# ============================================================
# EDITAR DADOS DA CARGA
# ============================================================

class TestEditarDadosCarga:

    def test_rejeita_json_invalido(
        self, shipment_client
    ):
        client, _ = shipment_client

        response = client.patch(
            "/nova-carga/fretes/10/dados",
            data="texto",
            content_type="text/plain",
        )

        assert response.status_code == 400
        assert response.get_json()["sucesso"] is False

    def test_atualiza_dados_com_sucesso(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client

        dados_atualizados = {
            "tipo_carga": "paletizada",
            "peso_liquido_kg": 12000,
            "valor_inicial_negociacao": 2500.50,
            "comentarios_carga": "Carga frágil",
        }

        mock = Mock(return_value=dados_atualizados)
        monkeypatch.setattr(
            shipment_module,
            "atualizar_dados_carga",
            mock,
        )

        response = client.patch(
            "/nova-carga/fretes/10/dados",
            json=dados_atualizados,
        )

        assert response.status_code == 200
        assert response.get_json()["sucesso"] is True
        assert response.get_json()["tipo_carga"] == "paletizada"
        assert response.get_json()["peso_liquido_kg"] == 12000
        assert response.get_json()["valor_inicial_negociacao"] == 2500.50
        assert response.get_json()["comentarios_carga"] == "Carga frágil"

        mock.assert_called_once_with(
            frete_id=10,
            tipo_carga="paletizada",
            peso_liquido_kg=12000,
            valor_inicial_negociacao=2500.50,
            comentarios_carga="Carga frágil",
        )

    def test_aplica_valores_padrao(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client

        mock = Mock(return_value={
            "tipo_carga": "batida",
            "peso_liquido_kg": None,
            "valor_inicial_negociacao": None,
            "comentarios_carga": "",
        })
        monkeypatch.setattr(
            shipment_module,
            "atualizar_dados_carga",
            mock,
        )

        response = client.patch(
            "/nova-carga/fretes/10/dados",
            json={},
        )

        assert response.status_code == 200
        mock.assert_called_once_with(
            frete_id=10,
            tipo_carga="batida",
            peso_liquido_kg=None,
            valor_inicial_negociacao=None,
            comentarios_carga="",
        )

    def test_trata_value_error(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client

        monkeypatch.setattr(
            shipment_module,
            "atualizar_dados_carga",
            Mock(side_effect=ValueError("peso inválido")),
        )

        response = client.patch(
            "/nova-carga/fretes/10/dados",
            json={"peso_liquido_kg": -1},
        )

        assert response.status_code == 400
        assert response.get_json()["mensagem"] == "peso inválido"


# ============================================================
# CONCLUIR FRETE
# ============================================================

class TestConcluirFrete:

    def test_conclui_frete_com_sucesso(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client
        mock = Mock()
        monkeypatch.setattr(shipment_module, "concluir_frete", mock)

        response = client.post(
            "/api/nova-carga/fretes/10/concluir"
        )

        assert response.status_code == 200
        assert response.get_json() == {
            "sucesso": True,
            "status": "concluido",
            "mensagem": "Frete concluído com sucesso.",
        }
        mock.assert_called_once_with(10)

    def test_trata_value_error(
        self, shipment_module, shipment_client, monkeypatch
    ):
        client, _ = shipment_client

        monkeypatch.setattr(
            shipment_module,
            "concluir_frete",
            Mock(side_effect=ValueError("frete não pode ser concluído")),
        )

        response = client.post(
            "/api/nova-carga/fretes/10/concluir"
        )

        assert response.status_code == 400
        assert response.get_json()["sucesso"] is False
        assert response.get_json()["mensagem"] == (
            "frete não pode ser concluído"
        )
