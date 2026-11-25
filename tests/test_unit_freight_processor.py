
from types import SimpleNamespace

import pandas as pd
import pytest
from io import BytesIO
from services import freight_processor as processor


@pytest.mark.parametrize(
    "valor, esperado",
    [
        (None, None),
        (float("nan"), None),
        ("", None),
        ("abc", None),
        ("0", None),
        ("-10", None),
        ("inf", None),
        ("nan", None),
        ("1500", 1500.0),
        ("1.500,50", 1500.50),
        ("1500,75", 1500.75),
        (" 250 ", 250.0),
    ],
)
def test_peso(valor, esperado):
    assert processor._peso(valor) == esperado


@pytest.mark.parametrize(
    "valor, esperado",
    [
        ("  ABC  ", "ABC"),
        ("", pd.NA),
        ("   ", pd.NA),
        ("nan", pd.NA),
        ("None", pd.NA),
        (None, pd.NA),
    ],
)
def test_limpar_texto(valor, esperado):
    resultado = processor._limpar_texto(
        pd.Series([valor], dtype="object")
    ).iloc[0]

    if pd.isna(esperado):
        assert pd.isna(resultado)
    else:
        assert resultado == esperado


@pytest.mark.parametrize(
    "valor, esperado",
    [
        (None, None),
        (float("nan"), None),
        ("", None),
        ("  ", None),
        ("nan", None),
        ("None", None),
        ("<NA>", None),
        ("123.0", "123"),
        ("123.00", "123"),
        ("00123", "00123"),
        ("ABC.0", "ABC.0"),
        ("  PED-123  ", "PED-123"),
        (123, "123"),
    ],
)
def test_identificador(valor, esperado):
    assert processor._identificador(valor) == esperado


@pytest.mark.parametrize(
    "valor, esperado",
    [
        ("abc", "ABC"),
        ("Abc", "ABC"),
        ("00123", "00123"),
        ("123.0", "123"),
        (None, None),
        ("", None),
    ],
)
def test_chave_cliente(valor, esperado):
    assert processor._chave_cliente(valor) == esperado


def test_separar_cidade_uf():
    serie = pd.Series([
        "Campinas-SP",
        "rio de janeiro-rj",
        "Curitiba-PR",
        "Cidade-XX1",
        "Cidade",
    ])

    resultado = processor._separar_cidade_uf(serie)

    assert resultado["cidade"].tolist() == [
        "Campinas",
        "Rio De Janeiro",
        "Curitiba",
        "Cidade",
        "Cidade",
    ]

    assert resultado["uf"].iloc[:3].tolist() == [
        "SP",
        "RJ",
        "PR",
    ]

    assert pd.isna(resultado["uf"].iloc[3])
    assert pd.isna(resultado["uf"].iloc[4])


def test_data_converte_datas_iso_e_brasileiras():
    serie = pd.Series([
        "2026-11-25",
        "25/11/2026",
        "data inválida",
        None,
    ])

    resultado = processor._data(serie)

    assert resultado.iloc[0] == pd.Timestamp("2026-11-25")
    assert resultado.iloc[1] == pd.Timestamp("2026-11-25")
    assert pd.isna(resultado.iloc[2])
    assert pd.isna(resultado.iloc[3])


def dataframe_base():
    return pd.DataFrame([
        {
            "Pedido / Ord. Venda": "1001",
            "Customer": "C001",
            "Cidade Destino": "Campinas-SP",
            "Data do Frete": "2026-11-25",
            "Quantidade": "1.000,50",
            "Nº. Frete": "F001",
            "Motorista": "Motorista A",
            "Local Transferência": None,
            "Material": "MAT01",
            "Descrição do Material": "Material teste",
        },
        {
            "Pedido / Ord. Venda": "1001",
            "Customer": "C001",
            "Cidade Destino": "Campinas-SP",
            "Data do Frete": "2026-11-25",
            "Quantidade": "500",
            "Nº. Frete": "F001",
            "Motorista": "Motorista A",
            "Local Transferência": None,
            "Material": "MAT02",
            "Descrição do Material": "Segundo material",
        },
        {
            "Pedido / Ord. Venda": "1002",
            "Customer": "C002",
            "Cidade Destino": "Santos-SP",
            "Data do Frete": "2026-11-25",
            "Quantidade": "250",
            "Nº. Frete": "F001",
            "Motorista": "Motorista B",
            "Local Transferência": None,
            "Material": "MAT03",
            "Descrição do Material": "Terceiro material",
        },
    ])


def configurar_processamento(monkeypatch, dataframe):
    planta = {"codigo": "SP01", "uf": "SP"}

    monkeypatch.setattr(
        processor,
        "_ler",
        lambda arquivo, nome: dataframe.copy(),
    )

    monkeypatch.setattr(
        processor,
        "get_planta",
        lambda codigo: planta if codigo == "fretes_1304" else None,
    )

    monkeypatch.setattr(
        processor,
        "_obter_mapa_clientes",
        lambda: {
            "C001": "Cliente Um",
            "C002": "Cliente Dois",
        },
    )


def arquivo_teste():
    return SimpleNamespace(filename="fretes_1304.xlsx")


def test_process_fretes_agrupa_pedidos_clientes_e_materiais(
    monkeypatch,
):
    configurar_processamento(monkeypatch, dataframe_base())

    resultado = processor.process_fretes(arquivo_teste())

    assert resultado["erros"] == []
    assert resultado["ignorados"] == []
    assert len(resultado["fretes"]) == 1

    frete = resultado["fretes"][0]

    assert frete["num"] == "F001"
    assert frete["motoristas"] == [
        "Motorista A",
        "Motorista B",
    ]
    assert frete["possui_motorista"] is True
    assert frete["status_inicial"] == "cotacao_aceita"

    assert frete["pedidos"] == ["1001", "1002"]

    assert frete["pedidos_clientes"] == [
        {"pedido": "1001", "customer_id": "C001"},
        {"pedido": "1002", "customer_id": "C002"},
    ]

    assert frete["clientes"] == [
        {
            "customer_id": "C001",
            "customer_name": "Cliente Um",
        },
        {
            "customer_id": "C002",
            "customer_name": "Cliente Dois",
        },
    ]

    assert frete["customer"] == "C001"
    assert frete["peso_kg"] == 1750.5

    assert frete["data_carga"] == "25/11/2026"
    assert frete["planta"]["codigo"] == "SP01"

    assert frete["destino"] == "Santos"
    assert frete["uf"] == "SP"
    assert frete["stops"] == [
        "Campinas-SP",
        "Santos-SP",
    ]

    assert frete["tipo"] == "Múltiplas paradas"
    assert frete["troca_nota"] is False

    assert len(frete["materiais"]) == 3
    assert frete["materiais"][0] == {
        "material": "MAT01",
        "descricao": "Material teste",
    }


def test_process_fretes_sem_motorista_fica_em_preparacao(
    monkeypatch,
):
    dataframe = dataframe_base().iloc[[0]].copy()
    dataframe["Motorista"] = None

    configurar_processamento(monkeypatch, dataframe)

    resultado = processor.process_fretes(arquivo_teste())

    frete = resultado["fretes"][0]

    assert frete["motoristas"] == []
    assert frete["possui_motorista"] is False
    assert frete["status_inicial"] == "em_preparacao"


def test_process_fretes_rejeita_nome_sem_planta(monkeypatch):
    monkeypatch.setattr(
        processor,
        "get_planta",
        lambda codigo: None,
    )

    arquivo = SimpleNamespace(filename="arquivo_invalido.xlsx")

    with pytest.raises(ValueError, match="Não encontrei uma planta válida"):
        processor.process_fretes(arquivo)


def test_process_fretes_rejeita_colunas_obrigatorias_ausentes(
    monkeypatch,
):
    dataframe = pd.DataFrame({
        "Pedido / Ord. Venda": ["1001"],
        "Customer": ["C001"],
    })

    configurar_processamento(monkeypatch, dataframe)

    with pytest.raises(ValueError, match="Colunas ausentes no arquivo"):
        processor.process_fretes(arquivo_teste())


def test_process_fretes_registra_frete_sem_numero(
    monkeypatch,
):
    dataframe = dataframe_base().iloc[[0]].copy()
    dataframe["Nº. Frete"] = None

    configurar_processamento(monkeypatch, dataframe)

    resultado = processor.process_fretes(arquivo_teste())

    assert resultado["fretes"] == []
    assert resultado["erros"] == [
        "Linha 2: sem número de frete"
    ]


def test_process_fretes_descarta_todo_grupo_com_peso_invalido(
    monkeypatch,
):
    dataframe = dataframe_base().copy()
    dataframe.loc[1, "Quantidade"] = "inválido"

    configurar_processamento(monkeypatch, dataframe)

    resultado = processor.process_fretes(arquivo_teste())

    assert resultado["fretes"] == []
    assert any("peso inválido" in erro for erro in resultado["erros"])


def test_process_fretes_sem_historico_cliente(
    monkeypatch,
):
    dataframe = dataframe_base().iloc[[0]].copy()

    configurar_processamento(monkeypatch, dataframe)

    monkeypatch.setattr(
        processor,
        "_obter_mapa_clientes",
        lambda: {},
    )

    resultado = processor.process_fretes(arquivo_teste())

    assert resultado["fretes"][0]["clientes"] == [
        {
            "customer_id": "C001",
            "customer_name": None,
        }
    ]

def test_ler_csv_com_separador_ponto_virgula():
    conteudo = (
        "Customer;Cidade Destino;Quantidade\n"
        "C001;Campinas-SP;1500\n"
        "C002;Santos-SP;250\n"
    )

    arquivo = BytesIO(conteudo.encode("utf-8"))

    resultado = processor._ler(arquivo, "fretes.csv")

    assert resultado.shape == (2, 3)
    assert resultado["Customer"].tolist() == ["C001", "C002"]
    assert resultado["Cidade Destino"].tolist() == [
        "Campinas-SP",
        "Santos-SP",
    ]


def test_ler_csv_com_codificacao_latin1():
    conteudo = (
        "Customer;Cidade Destino\n"
        "C001;São Paulo-SP\n"
    ).encode("latin1")

    arquivo = BytesIO(conteudo)

    resultado = processor._ler(arquivo, "fretes.csv")

    assert resultado.loc[0, "Customer"] == "C001"
    assert resultado.loc[0, "Cidade Destino"] == "São Paulo-SP"


def test_ler_excel_com_planilha_sheet1():
    arquivo = BytesIO()

    dados = pd.DataFrame({
        "Customer": ["C001", "C002"],
        "Cidade Destino": ["Campinas-SP", "Santos-SP"],
        "Quantidade": ["1500", "250"],
    })

    with pd.ExcelWriter(arquivo, engine="openpyxl") as writer:
        dados.to_excel(writer, sheet_name="Sheet1", index=False)

    arquivo.seek(0)

    resultado = processor._ler(arquivo, "fretes.xlsx")

    assert resultado.shape == (2, 3)
    assert resultado["Customer"].tolist() == ["C001", "C002"]
    assert resultado["Quantidade"].tolist() == ["1500", "250"]


def test_ler_excel_rejeita_planilha_com_nome_diferente():
    arquivo = BytesIO()

    dados = pd.DataFrame({
        "Customer": ["C001"],
    })

    with pd.ExcelWriter(arquivo, engine="openpyxl") as writer:
        dados.to_excel(writer, sheet_name="Dados", index=False)

    arquivo.seek(0)

    with pytest.raises(ValueError, match="Worksheet named 'Sheet1' not found"):
        processor._ler(arquivo, "fretes.xlsx")



def test_ler_csv_com_separador_ponto_virgula():
    conteudo = (
        "Customer;Cidade Destino;Quantidade\n"
        "C001;Campinas-SP;1500\n"
        "C002;Santos-SP;250\n"
    )
    arquivo = BytesIO(conteudo.encode("utf-8"))

    resultado = processor._ler(arquivo, "fretes.csv")

    assert resultado.shape == (2, 3)
    assert resultado["Customer"].tolist() == ["C001", "C002"]
    assert resultado["Cidade Destino"].tolist() == [
        "Campinas-SP",
        "Santos-SP",
    ]


def test_ler_csv_com_codificacao_latin1():
    conteudo = (
        "Customer;Cidade Destino\n"
        "C001;São Paulo-SP\n"
    ).encode("latin1")
    arquivo = BytesIO(conteudo)

    resultado = processor._ler(arquivo, "fretes.csv")

    assert resultado.loc[0, "Customer"] == "C001"
    assert resultado.loc[0, "Cidade Destino"] == "São Paulo-SP"


def test_ler_excel_com_planilha_sheet1():
    arquivo = BytesIO()
    dados = pd.DataFrame({
        "Customer": ["C001", "C002"],
        "Cidade Destino": ["Campinas-SP", "Santos-SP"],
        "Quantidade": ["1500", "250"],
    })

    with pd.ExcelWriter(arquivo, engine="openpyxl") as writer:
        dados.to_excel(writer, sheet_name="Sheet1", index=False)

    arquivo.seek(0)

    resultado = processor._ler(arquivo, "fretes.xlsx")

    assert resultado.shape == (2, 3)
    assert resultado["Customer"].tolist() == ["C001", "C002"]
    assert resultado["Quantidade"].tolist() == ["1500", "250"]


def test_ler_excel_rejeita_planilha_com_nome_diferente():
    arquivo = BytesIO()
    dados = pd.DataFrame({"Customer": ["C001"]})

    with pd.ExcelWriter(arquivo, engine="openpyxl") as writer:
        dados.to_excel(writer, sheet_name="Dados", index=False)

    arquivo.seek(0)

    with pytest.raises(ValueError):
        processor._ler(arquivo, "fretes.xlsx")



def test_mapa_clientes_parquet_normaliza_dados_e_preserva_primeiro_nome(
    tmp_path,
):
    arquivo = tmp_path / "clientes.parquet"

    dados = pd.DataFrame({
        "customer_id": [
            "123.0",
            "00123",
            "ABC",
            "abc",
            None,
            "C004",
        ],
        "customer_name": [
            "  Nome   Um  ",
            "Nome duplicado",
            " Cliente  A ",
            "Nome duplicado A",
            "Cliente sem código",
            None,
        ],
    })

    dados.to_parquet(arquivo, index=False)

    processor._mapa_clientes_parquet.cache_clear()

    try:
        resultado = processor._mapa_clientes_parquet(
            str(arquivo),
            arquivo.stat().st_mtime_ns,
        )

        assert resultado == {
            "123": "Nome Um",
            "00123": "Nome duplicado",
            "ABC": "Cliente A",
        }

        # Confirma que a segunda chamada utiliza o cache.
        segunda_chamada = processor._mapa_clientes_parquet(
            str(arquivo),
            arquivo.stat().st_mtime_ns,
        )

        assert segunda_chamada is resultado
        assert processor._mapa_clientes_parquet.cache_info().hits == 1

    finally:
        processor._mapa_clientes_parquet.cache_clear()


def test_obter_mapa_clientes_le_arquivo_configurado(
    tmp_path,
    monkeypatch,
):
    arquivo = tmp_path / "clientes.parquet"

    dados = pd.DataFrame({
        "customer_id": ["C001", "C002"],
        "customer_name": ["Cliente Um", "Cliente Dois"],
    })

    dados.to_parquet(arquivo, index=False)

    monkeypatch.setattr(processor, "PARQUET_PATH", arquivo)

    processor._mapa_clientes_parquet.cache_clear()

    try:
        resultado = processor._obter_mapa_clientes()

        assert resultado == {
            "C001": "Cliente Um",
            "C002": "Cliente Dois",
        }

    finally:
        processor._mapa_clientes_parquet.cache_clear()



def test_obter_mapa_clientes_sem_caminho_configurado(monkeypatch):
    monkeypatch.setattr(processor, "PARQUET_PATH", None)

    resultado = processor._obter_mapa_clientes()

    assert resultado == {}


def test_obter_mapa_clientes_com_arquivo_inexistente(
    tmp_path,
    monkeypatch,
):
    arquivo = tmp_path / "inexistente.parquet"
    monkeypatch.setattr(processor, "PARQUET_PATH", arquivo)

    resultado = processor._obter_mapa_clientes()

    assert resultado == {}


def test_obter_mapa_clientes_retorna_vazio_quando_leitura_falha(
    tmp_path,
    monkeypatch,
):
    arquivo = tmp_path / "clientes.parquet"
    arquivo.touch()

    monkeypatch.setattr(processor, "PARQUET_PATH", arquivo)

    def falhar_leitura(*args, **kwargs):
        raise RuntimeError("Falha simulada na leitura")

    monkeypatch.setattr(
        processor,
        "_mapa_clientes_parquet",
        falhar_leitura,
    )

    resultado = processor._obter_mapa_clientes()

    assert resultado == {}


def test_mapa_clientes_parquet_ignora_nomes_vazios_e_invalidos(
    tmp_path,
):
    arquivo = tmp_path / "clientes_invalidos.parquet"

    dados = pd.DataFrame({
        "customer_id": ["C001", "C002", "C003", "C004"],
        "customer_name": ["", "nan", "None", "Cliente válido"],
    })

    dados.to_parquet(arquivo, index=False)

    processor._mapa_clientes_parquet.cache_clear()

    try:
        resultado = processor._mapa_clientes_parquet(
            str(arquivo),
            arquivo.stat().st_mtime_ns,
        )

        assert resultado == {
            "C004": "Cliente válido",
        }
    finally:
        processor._mapa_clientes_parquet.cache_clear()


def test_process_fretes_descarta_grupo_com_uf_invalida(
    monkeypatch,
):
    dataframe = dataframe_base().copy()
    dataframe.loc[1, "Cidade Destino"] = "Campinas-SPX"

    configurar_processamento(monkeypatch, dataframe)

    resultado = processor.process_fretes(arquivo_teste())

    assert resultado["fretes"] == []
    assert any(
        "destino fora do padrão CIDADE-UF" in erro
        for erro in resultado["erros"]
    )


def test_process_fretes_descarta_grupo_com_cidade_sem_uf(
    monkeypatch,
):
    dataframe = dataframe_base().copy()
    dataframe.loc[0, "Cidade Destino"] = "Campinas"

    configurar_processamento(monkeypatch, dataframe)

    resultado = processor.process_fretes(arquivo_teste())

    assert resultado["fretes"] == []
    assert any(
        "destino fora do padrão CIDADE-UF" in erro
        for erro in resultado["erros"]
    )


def test_process_fretes_aceita_data_invalida_sem_interromper(
    monkeypatch,
):
    dataframe = dataframe_base().iloc[[0]].copy()
    dataframe.loc[0, "Data do Frete"] = "data inválida"

    configurar_processamento(monkeypatch, dataframe)

    resultado = processor.process_fretes(arquivo_teste())

    assert len(resultado["fretes"]) == 1
    assert resultado["fretes"][0]["data_carga"] is None
    assert resultado["erros"] == []


def test_process_fretes_sem_pedido_ou_cliente(
    monkeypatch,
):
    dataframe = dataframe_base().iloc[[0]].copy()
    dataframe["Pedido / Ord. Venda"] = None
    dataframe["Customer"] = None

    configurar_processamento(monkeypatch, dataframe)

    resultado = processor.process_fretes(arquivo_teste())

    frete = resultado["fretes"][0]

    assert frete["pedidos"] == []
    assert frete["pedidos_clientes"] == []
    assert frete["clientes"] == []
    assert frete["customer"] is None


def test_process_fretes_remove_motoristas_duplicados_e_vazios(
    monkeypatch,
):
    dataframe = dataframe_base().copy()

    dataframe.loc[0, "Motorista"] = "Motorista A"
    dataframe.loc[1, "Motorista"] = " Motorista A "
    dataframe.loc[2, "Motorista"] = " "

    configurar_processamento(monkeypatch, dataframe)

    resultado = processor.process_fretes(arquivo_teste())

    frete = resultado["fretes"][0]

    assert frete["motoristas"] == ["Motorista A"]
    assert frete["possui_motorista"] is True
    assert frete["status_inicial"] == "cotacao_aceita"


def test_process_fretes_sem_colunas_opcionais_de_material(
    monkeypatch,
):
    dataframe = dataframe_base().iloc[[0]].copy()

    dataframe = dataframe.drop(
        columns=["Material", "Descrição do Material"]
    )

    configurar_processamento(monkeypatch, dataframe)

    resultado = processor.process_fretes(arquivo_teste())

    assert resultado["fretes"][0]["materiais"] == [
        {
            "material": None,
            "descricao": None,
        }
    ]


def test_process_fretes_com_transbordo(
    monkeypatch,
):
    dataframe = dataframe_base().iloc[[0]].copy()
    dataframe.loc[0, "Local Transferência"] = "1305"

    planta_origem = {"codigo": "SP01", "uf": "SP"}
    planta_transbordo = {"codigo": "RJ02", "uf": "RJ"}

    monkeypatch.setattr(
        processor,
        "_ler",
        lambda arquivo, nome: dataframe.copy(),
    )

    monkeypatch.setattr(
        processor,
        "get_planta",
        lambda codigo: {
            "fretes_1304": planta_origem,
            "1305": planta_transbordo,
        }.get(codigo),
    )

    monkeypatch.setattr(
        processor,
        "_obter_mapa_clientes",
        lambda: {},
    )

    resultado = processor.process_fretes(arquivo_teste())

    frete = resultado["fretes"][0]

    assert frete["transfer_planta"] == planta_transbordo
    assert frete["tipo"] == "Transbordo"
    assert frete["troca_nota"] is False


def test_process_fretes_direto_com_troca_de_nota(
    monkeypatch,
):
    dataframe = dataframe_base().iloc[[0]].copy()
    dataframe.loc[0, "Cidade Destino"] = "Curitiba-PR"

    configurar_processamento(monkeypatch, dataframe)

    resultado = processor.process_fretes(arquivo_teste())

    frete = resultado["fretes"][0]

    assert frete["tipo"] == "Direta"
    assert frete["destino"] == "Curitiba"
    assert frete["uf"] == "PR"
    assert frete["troca_nota"] is True
    assert frete["transfer_planta"] is None


def test_process_fretes_conserva_pares_pedido_cliente_sem_duplicar(
    monkeypatch,
):
    dataframe = dataframe_base().copy()

    # Repetição do mesmo pedido e cliente em outra linha.
    dataframe.loc[1, "Pedido / Ord. Venda"] = "1001"
    dataframe.loc[1, "Customer"] = "C001"

    configurar_processamento(monkeypatch, dataframe)

    resultado = processor.process_fretes(arquivo_teste())

    frete = resultado["fretes"][0]

    assert frete["pedidos_clientes"] == [
        {"pedido": "1001", "customer_id": "C001"},
        {"pedido": "1002", "customer_id": "C002"},
    ]

    assert frete["clientes"] == [
        {
            "customer_id": "C001",
            "customer_name": "Cliente Um",
        },
        {
            "customer_id": "C002",
            "customer_name": "Cliente Dois",
        },
    ]


def test_separar_cidade_uf_sem_hifen():
    serie = pd.Series([
        "Campinas",
        "Santos",
        "Curitiba",
    ])

    resultado = processor._separar_cidade_uf(serie)

    assert resultado["cidade"].tolist() == [
        "Campinas",
        "Santos",
        "Curitiba",
    ]

    assert resultado["uf"].isna().all()