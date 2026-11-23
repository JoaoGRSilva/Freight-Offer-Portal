import pandas as pd
import numpy as np
from pathlib import Path
import time
import re

# =====================================
# CONFIG
# =====================================

INPUT_FILE = "data/raw/baseEA.xlsx"
OUTPUT_FILE = "data/processed/baseEA.parquet"

DEBUG = True  # liga/desliga os prints de debug detalhados

RENAME_COLS = {
    "PD Header\nPD Header": "pd_header",
    "(Self)\nBilling Date Logistic Report": "billing_date",
    "Sales Organization\nSales Organization": "sales_organization",
    "Freight Header\nFreight Header": "freight_id",
    "Freight Header\nType Freight": "freight_type",
    "Freight Header\nStatus": "freight_status",
    "SD Item\nIncoterms": "incoterms",
    "Delivery Header\nDelivery Type": "delivery_type",
    "(Self)\nCreated On": "created_on",
    "(Self)\nOrder Due Date": "due_date",
    "(Self)\nRealized Finish Date": "finish_date",
    "Material\nMaterial Type": "material_type",
    "Freight Header\nZDELE_CDFATUR": "billing_code",  # Cd Faturado (código, não data)
    "Freight Header\nZDELE_CDATEND": "service_code",  # Cd Atendimento (código, não data)
    "(Self)\nIssuing Plant": "issuing_plant",
    "Material\nID": "material_id",
    "Material\nDescription": "material_description",
    "Delivery Header\nShip-to party": "ship_to_party",
    "Customer\nCustomer": "customer_id",
    "Customer\nDescription": "customer_name",
    "Customer\nCountry": "customer_country",
    "Customer\nCity": "customer_city",
    "Customer\nAccount group": "customer_account_group",
    "Vendor\nVendor": "vendor_id",
    "Vendor\nDescription": "vendor_name",
    "Vendor\nCountry": "vendor_country",
    "Vendor\nCity": "vendor_city",
    "Service Agent\nAccount Group": "service_agent_group",
    "Service Agent\nService Agent": "service_agent",
    "Service Agent\nDescription": "service_agent_description",
    "(Self)\nQuantity": "quantity",
    "(Self)\nBBP: Main Leg Discount": "main_leg_discount",
    "(Self)\nBBP: Main Leg Complement": "main_leg_complement",
    "(Self)\nBBP: Main Leg Bank Fee": "main_leg_bank_fee",
    "(Self)\nBBP: Main Leg Valor St": "main_leg_valor_st",
    "(Self)\nBBP: Main Leg Gris": "main_leg_gris",
    "(Self)\nBBP: Main Leg AD Valorem": "main_leg_ad_valorem",
    "(Self)\nBBP: Main Leg Standard Freight Value": "main_leg_standard_freight_value",
    "(Self)\nBBP: Main Leg Toll Value": "main_leg_toll_value",
    "(Self)\nBBP: Main Leg Net Freight Value": "main_leg_freight_value",
    "(Self)\nBBP: Main Leg Gross Freight Value": "main_leg_gross_freight_value",
    "(Self)\nBBP: Trans Leg Complement": "trans_leg_complement",
    "(Self)\nBBP: Trans Leg Gris": "trans_leg_gris",
    "(Self)\nBBP: Trans Leg Net Freight Value": "trans_leg_net_freight_value",
    "(Self)\nBBP: Trans Ship. Chapa": "trans_ship_chapa",
    "(Self)\nBBP: Complement Standard Freight Value": "complement_standard_freight_value",
    "(Self)\nBBP: Trans Leg Gross Freight Value": "trans_leg_gross_freight_value",
    "(Self)\nBBP: Trans Leg Bank Fee": "trans_leg_bank_fee",
    "(Self)\nBBP: Trans Ship. Complement": "trans_ship_complement",
    "(Self)\nBBP: Trans Leg Valor St": "trans_leg_valor_st",
    "(Self)\nBBP: Trans Leg Toll Value": "trans_leg_toll_value",
    "(Self)\nBBP: Trans Ship. Net Freight Value": "trans_ship_net_freight_value",
    "(Self)\nBBP: Trans Leg AD Valorem": "trans_leg_ad_valorem",
    "(Self)\nBBP: Trans Ship. Standard Freight Value": "trans_ship_standard_freight_value",
    "(Self)\nBBP: Trans Leg Standard Freight Value": "trans_leg_standard_freight_value",
    "(Self)\nBBP: Trans Ship. Discount": "trans_ship_discount",
    "(Self)\nBBP: Trans Leg Discount": "trans_leg_discount",
    "(Self)\nBBP: Trans Ship. Gross Freight Value": "trans_ship_gross_freight_value",
    "(Self)\nBBP: Total Standard Value": "total_standard_value",
    "(Self)\nBBP: Total Negociated Value": "negotiated_value",
    "Freight Header\nUsuário Reponsável": "responsible_user",
    "SD Header\nSales Office": "sales_office",
    "Storage Location\nStorage Location": "storage_location",
    "SD Header\nSD Header": "sd_header",
    "Batch\nBatch": "batch",
    "Customer Address\nTax Jurisdiction": "customer_tax_jurisdiction",
    "Customer\nRegion": "customer_region",
    "Ship-to Address\nTax Jurisdiction": "ship_to_tax_jurisdiction",
    "Cross Dock\nName transhipment pt.": "cross_dock",
    "Customer Address\nPostal Code" : "cep"
}

DATE_COLS = [
    "billing_date",
    "created_on",
    "due_date",
    "finish_date",
]

# Códigos internos (ex.: Cd Faturado, Cd Atendimento) — texto, não data.
CODE_COLS = [
    "billing_code",
    "service_code",
]

NUMERIC_COLS = [
    "quantity",
    "main_leg_discount",
    "main_leg_complement",
    "main_leg_bank_fee",
    "main_leg_valor_st",
    "main_leg_gris",
    "main_leg_ad_valorem",
    "main_leg_standard_freight_value",
    "main_leg_toll_value",
    "main_leg_freight_value",
    "main_leg_gross_freight_value",
    "trans_leg_complement",
    "trans_leg_gris",
    "trans_leg_net_freight_value",
    "trans_leg_bank_fee",
    "trans_leg_valor_st",
    "trans_leg_toll_value",
    "trans_leg_ad_valorem",
    "trans_leg_standard_freight_value",
    "trans_leg_discount",
    "trans_leg_gross_freight_value",
    "trans_ship_chapa",
    "trans_ship_complement",
    "trans_ship_net_freight_value",
    "trans_ship_standard_freight_value",
    "trans_ship_discount",
    "trans_ship_gross_freight_value",
    "total_standard_value",
    "negotiated_value",
]

ID_COLS = [
    "pd_header",
    "freight_id",
    "material_id",
    "customer_id",
    "ship_to_party",
    "vendor_id",
    "service_agent",
    "sd_header",
    "batch",
]

DESCRIPTION_COLS = [
    "material_description",
    "customer_name",
    "vendor_name",
    "service_agent_description",
]

LOCATION_COLS = [
    "issuing_plant",
    "storage_location",
    "customer_country",
    "customer_city",
    "customer_region",
    "vendor_country",
    "vendor_city",
    "cep"
]

BUSINESS_CLASSIFICATION_COLS = [
    "sales_organization",
    "sales_office",
    "freight_type",
    "freight_status",
    "incoterms",
    "delivery_type",
    "material_type",
    "customer_account_group",
    "service_agent_group",
]

USER_COLS = [
    "responsible_user",
]

TAX_COLS = [
    "customer_tax_jurisdiction",
    "ship_to_tax_jurisdiction",
]

CARRIER_COLS = [
    "service_agent",
    "service_agent_description",
    "service_agent_group",
]

CUSTOMER_COLS = [
    "customer_id",
    "customer_name",
    "customer_account_group",
    "customer_city",
    "customer_region",
    "customer_country",
    "cep"
]

MATERIAL_COLS = [
    "material_id",
    "material_description",
    "material_type",
]

FREIGHT_COST_COLS = [
    "main_leg_freight_value",
    "main_leg_gross_freight_value",
    "trans_leg_net_freight_value",
    "trans_leg_gross_freight_value",
    "trans_ship_net_freight_value",
    "trans_ship_gross_freight_value",
    "negotiated_value",
]

SAVINGS_COLS = [
    "total_standard_value",
    "negotiated_value",
]

CODE_DESC_COLS = [
    "material_type",
    "customer_account_group",
    "service_agent_group",
    "issuing_plant",
]

# Colunas "âncora" usadas para detectar linhas de cabeçalho repetidas no meio
# dos dados (export SAP costuma repetir o header a cada quebra de página/bloco).
# Usamos um subconjunto, e não 100% das colunas, porque em exports reais nem
# toda coluna repete o texto do cabeçalho na linha "fantasma".
HEADER_ANCHOR_COLS_HINT = [
    "Freight Header\nFreight Header",
    "(Self)\nCreated On",
    "(Self)\nOrder Due Date",
]

# =====================================
# HELPERS DE LOG
# =====================================

_step_counter = {"n": 0}
_t0 = time.time()


def log_step(titulo):
    """Imprime um cabeçalho de etapa numerado, com timestamp relativo."""
    _step_counter["n"] += 1
    elapsed = time.time() - _t0
    print(
        f"\n[{_step_counter['n']:02d}] "
        f"({elapsed:6.2f}s) "
        f"=== {titulo} ==="
    )


def log_debug(msg):
    """Print de debug, só aparece se DEBUG=True."""
    if DEBUG:
        print(f"    [debug] {msg}")


def log_ok(msg):
    print(f"    [ok] {msg}")


def log_warn(msg):
    print(f"    [AVISO] {msg}")


def log_alert(msg):
    print(f"    [ALERTA] {msg}")


# =====================================
# HELPERS DE TRANSFORMAÇÃO
# =====================================

MESES_PT_NUM = {
    "jan": "01", "fev": "02", "mar": "03", "abr": "04",
    "mai": "05", "jun": "06", "jul": "07", "ago": "08",
    "set": "09", "out": "10", "nov": "11", "dez": "12",
}

# Regex que casa dd/mon_pt/yyyy (ou d/mon_pt/yy), ex: "24/jul/2025"
_PT_DATE_RE = r"^(\d{1,2})/([a-zç]{3,4})/(\d{2,4})$"


def parse_date_pt(series):
    """
    Converte datas em texto no formato brasileiro 'dd/mon/yyyy' com mês
    abreviado em português (jan, fev, mar, abr, mai, jun, jul, ago, set,
    out, nov, dez) — formato que o dateutil NÃO reconhece nativamente
    (só entende abreviações em inglês), causando 100% de falha silenciosa
    mesmo com format="mixed".

    Faz duas passadas:
      1. Tenta pd.to_datetime direto (cobre valores que já vêm como
         datetime nativo do Excel, ou em outro formato reconhecível).
      2. Para o que sobrou como NaT, tenta re-interpretar como texto
         'dd/mon_pt/yyyy', trocando o mês por extenso/abreviado pt pelo
         número correspondente antes de parsear com formato fixo.
    """

    original = series

    # Passo 1: tentativa "normal"
    parsed = pd.to_datetime(original, errors="coerce", format="mixed")

    ainda_invalido = parsed.isna() & original.notna()

    if ainda_invalido.any():
        texto = (
            original[ainda_invalido]
            .astype(str)
            .str.strip()
            .str.lower()
        )

        # normaliza acentos comuns (ex.: variações de "set")
        texto = texto.str.normalize("NFKD").str.encode(
            "ascii", errors="ignore"
        ).str.decode("ascii")

        def troca_mes(valor):
            m = re.match(_PT_DATE_RE, valor)
            if not m:
                return None
            dia, mes_abrev, ano = m.groups()
            mes_num = MESES_PT_NUM.get(mes_abrev[:3])
            if mes_num is None:
                return None
            if len(ano) == 2:
                ano = "20" + ano
            return f"{dia.zfill(2)}/{mes_num}/{ano}"

        texto_normalizado = texto.map(troca_mes)

        recuperadas = pd.to_datetime(
            texto_normalizado, format="%d/%m/%Y", errors="coerce"
        )

        parsed.loc[ainda_invalido] = recuperadas.values

    return parsed


def split_code_description(series):
    text = (
        series.fillna("")
        .astype(str)
        .str.strip()
    )

    extracted = text.str.extract(
        r"^([^\(]+?)\s*(?:\((.*)\))?$"
    )

    code = extracted[0].str.strip()
    desc = extracted[1].str.strip()

    return code, desc


def drop_embedded_header_rows(df, anchor_cols=None, threshold=0.8):
    """
    Remove linhas onde os valores repetem o texto do cabeçalho da coluna
    (linhas de cabeçalho "fantasma" no meio do export).

    Em vez de exigir que 100% das colunas batam (o que raramente acontece
    em exports SAP reais, já que nem toda coluna repete o header na linha
    fantasma), usamos:
      - um subconjunto de colunas-âncora, se existirem no df
      - ou a fração `threshold` das colunas totais como critério
    """

    cols_para_checar = [c for c in (anchor_cols or []) if c in df.columns]

    if cols_para_checar:
        log_debug(
            f"drop_embedded_header_rows: usando colunas-âncora "
            f"{cols_para_checar}"
        )
        mask = pd.Series(True, index=df.index)
        for col in cols_para_checar:
            mask &= (
                df[col].astype(str).str.strip()
                == str(col).strip()
            )
    else:
        log_debug(
            f"drop_embedded_header_rows: nenhuma coluna-âncora encontrada, "
            f"usando limiar de {threshold*100:.0f}% das colunas batendo "
            f"com o nome do header"
        )
        match_matrix = pd.DataFrame(
            {
                col: df[col].astype(str).str.strip() == str(col).strip()
                for col in df.columns
            }
        )
        mask = match_matrix.mean(axis=1) >= threshold

    removidas = int(mask.sum())

    if removidas:
        log_warn(f"Linhas de cabeçalho embutido removidas: {removidas:,}")
    else:
        log_ok("Nenhuma linha de cabeçalho embutido encontrada")

    return df.loc[~mask].copy()


def process_historico(input_file, output_file=OUTPUT_FILE):
    """
    Processa uma nova base histórica e publica o parquet de histórico.

    O arquivo de entrada pode ser fornecido dinamicamente pelo upload
    da aplicação ou diretamente pelo script.

    O parquet ativo só é substituído depois que todo o processamento
    termina com sucesso.
    """

    global _step_counter, _t0

    _step_counter = {"n": 0}
    _t0 = time.time()

    input_path = Path(input_file)
    output_path = Path(output_file)

    # =====================================
    # VALIDAÇÃO DO ARQUIVO
    # =====================================

    log_step("Validação do arquivo de entrada")

    log_debug(f"INPUT_FILE = {input_path}")
    log_debug(f"OUTPUT_FILE = {output_path}")

    if not input_path.exists():
        log_alert(f"Arquivo não encontrado: {input_path}")
        raise FileNotFoundError(
            f"Arquivo não encontrado: {input_path}"
        )

    log_ok(f"Arquivo encontrado: {input_path}")

    # =====================================
    # LEITURA
    # =====================================
    log_step("Leitura do arquivo")

    extensao = input_path.suffix.lower()

    if extensao == ".xlsx":
        df = pd.read_excel(
            input_path,
            engine="openpyxl"
        )

    elif extensao == ".csv":
        try:
            df = pd.read_csv(input_path)
        except UnicodeDecodeError:
            df = pd.read_csv(
                input_path,
                encoding="latin1"
            )

    elif extensao == ".parquet":
        df = pd.read_parquet(input_path)

    else:
        raise ValueError(
            f"Formato não suportado: {extensao}. "
            "Use XLSX, CSV ou Parquet."
        )

    log_ok(f"Linhas brutas: {len(df):,}")
    log_ok(f"Colunas brutas: {len(df.columns)}")

    log_debug(
        f"Primeiras colunas lidas: {list(df.columns[:5])}"
    )

    # =====================================
    # LIMPEZA INICIAL
    # =====================================
    log_step(
        "Remoção de linhas de cabeçalho embutido "
        "e linhas totalmente vazias"
    )

    df = drop_embedded_header_rows(
        df,
        anchor_cols=HEADER_ANCHOR_COLS_HINT
    )

    linhas_antes_dropna = len(df)

    df.dropna(
        how="all",
        inplace=True
    )

    linhas_removidas_vazias = (
        linhas_antes_dropna - len(df)
    )

    if linhas_removidas_vazias:
        log_warn(
            f"Linhas totalmente vazias removidas: "
            f"{linhas_removidas_vazias:,}"
        )
    else:
        log_ok(
            "Nenhuma linha totalmente vazia encontrada"
        )

    log_ok(
        f"Linhas após limpeza inicial: {len(df):,}"
    )


    # =====================================
    # VALIDAÇÃO SCHEMA
    # =====================================

    log_step("Validação do schema obrigatório")

    required_columns = [
        "Freight Header\nFreight Header",
        "(Self)\nCreated On",
        "(Self)\nOrder Due Date",
        "(Self)\nQuantity",
    ]

    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        log_alert("Colunas obrigatórias ausentes:")
        for col in missing_columns:
            log_alert(f"  - {col}")
        raise ValueError(
            "\nColunas obrigatórias ausentes:\n" + "\n".join(missing_columns)
        )

    log_ok("Todas as colunas obrigatórias presentes")

    # =====================================
    # RENOMEAR COLUNAS (com detecção de colunas ausentes)
    # =====================================

    log_step("Mapeamento e renomeação de colunas")

    cols_presentes = {
        k: v for k, v in RENAME_COLS.items() if k in df.columns
    }

    log_ok(f"Colunas do dicionário encontradas no arquivo: {len(cols_presentes)} / {len(RENAME_COLS)}")

    # --- Detecta ANTES de criar as colunas vazias, quais colunas esperadas
    #     (origem OU destino) não existem no arquivo bruto.
    missing_source_cols = [
        (k, v) for k, v in RENAME_COLS.items()
        if k not in df.columns and v not in df.columns
    ]

    if missing_source_cols:
        log_alert(
            f"{len(missing_source_cols)} coluna(s) esperada(s) NÃO existem no "
            f"arquivo de origem. Serão criadas vazias (NA) e todos os KPIs "
            f"derivados delas ficarão inválidos/zerados:"
        )
        for origem, destino in missing_source_cols:
            log_alert(f"  - '{origem}' -> '{destino}'")
    else:
        log_ok("Todas as colunas mapeadas existem no arquivo de origem")

    df.rename(columns=cols_presentes, inplace=True)
    log_debug(f"Renomeadas {len(cols_presentes)} colunas")

    for col in RENAME_COLS.values():
        if col not in df.columns:
            df[col] = pd.NA

    unmapped_columns = [
        col for col in df.columns if col not in RENAME_COLS.values()
    ]

    if unmapped_columns:
        log_warn(f"{len(unmapped_columns)} coluna(s) do arquivo não mapeada(s) no dicionário:")
        for col in unmapped_columns:
            log_warn(f"  - {col}")
    else:
        log_ok("Todas as colunas do arquivo estão mapeadas")

    # =====================================
    # DATAS
    # =====================================

    log_step("Conversão de colunas de data")

    for col in DATE_COLS:
        if col in df.columns:
            antes_validas = df[col].notna().sum()
            amostra_bruta = (
                df[col].dropna().astype(str).head(1).tolist()
            )
            df[col] = parse_date_pt(df[col])
            depois_validas = df[col].notna().sum()

            taxa = (depois_validas / antes_validas * 100) if antes_validas else 0

            log_debug(
                f"{col}: exemplo bruto={amostra_bruta} | "
                f"{antes_validas:,} valores originais -> "
                f"{depois_validas:,} convertidos ({taxa:.1f}% de sucesso)"
            )

            if antes_validas > 0 and depois_validas == 0:
                log_alert(
                    f"{col}: 0% de conversão — formato de data não reconhecido, "
                    f"verifique manualmente a amostra bruta acima"
                )

    # =====================================
    # VALIDAÇÃO DATAS
    # =====================================

    log_step("Validação de qualidade das datas")

    for col in DATE_COLS:
        if col not in df.columns:
            continue

        invalid_dates = df[col].isna().sum()
        valid_dates = len(df) - invalid_dates
        pct_valido = valid_dates / len(df) * 100 if len(df) else 0
        pct_invalido = 100 - pct_valido

        # % sempre na frente e com largura fixa, pra bater o olho e comparar
        # entre colunas sem precisar ler o número absoluto (que pode ter
        # 6+ dígitos e disfarçar uma taxa de conversão ruim).
        linha = (
            f"{pct_valido:5.1f}% válido "
            f"(inválido {pct_invalido:5.1f}%) — {col} "
            f"[{valid_dates:,}/{len(df):,}]"
        )

        if col in [d for _, d in missing_source_cols]:
            log_alert(f"{linha} — esperado: coluna ausente no arquivo bruto")
        elif pct_invalido > 20:
            log_alert(linha)
        else:
            log_ok(linha)

    # =====================================
    # NUMÉRICOS
    # =====================================

    log_step("Conversão de colunas numéricas")

    for col in NUMERIC_COLS:
        if col in df.columns:
            antes_validos = df[col].notna().sum()
            df[col] = pd.to_numeric(df[col], errors="coerce")
            depois_validos = df[col].notna().sum()
            log_debug(
                f"{col}: {antes_validos:,} -> {depois_validos:,} valores numéricos válidos"
            )

    df[NUMERIC_COLS] = df[NUMERIC_COLS].replace([np.inf, -np.inf], np.nan)
    log_debug("Infinitos (+/-) substituídos por NaN em todas as colunas numéricas")

    qtd_nulos_negociado_antes = df["negotiated_value"].isna().sum()
    df["negotiated_value"] = df["negotiated_value"].fillna(0)
    log_ok(f"negotiated_value: {qtd_nulos_negociado_antes:,} nulos preenchidos com 0")

    # =====================================
    # VALIDAÇÃO NUMÉRICOS
    # =====================================

    log_step("Validação de valores negativos")

    algum_negativo = False
    for col in NUMERIC_COLS:
        if col not in df.columns:
            continue

        negativos = (df[col] < 0).sum()

        if negativos:
            algum_negativo = True
            log_warn(f"{col}: {negativos:,} registros negativos")

    if not algum_negativo:
        log_ok("Nenhum valor negativo encontrado nas colunas numéricas")

    # =====================================
    # IDS
    # =====================================

    log_step("Normalização de colunas de ID")

    for col in ID_COLS:
        if col in df.columns:
            df[col] = df[col].astype("string").str.strip()
            log_debug(f"{col}: normalizado, {df[col].nunique():,} valores únicos")

    log_step("Normalização de colunas de código (billing_code, service_code)")

    for col in CODE_COLS:
        if col in df.columns:
            df[col] = df[col].astype("string").str.strip()
            log_debug(f"{col}: normalizado, {df[col].nunique():,} valores únicos")

    # =====================================
    # CODE / DESCRIPTION
    # =====================================

    log_step("Split code/description")

    for col in CODE_DESC_COLS:
        if col in df.columns:
            code, desc = split_code_description(df[col])
            df[f"{col}_code"] = code
            df[f"{col}_desc"] = desc
            log_debug(
                f"{col}: gerado {col}_code ({code.notna().sum():,} válidos) "
                f"e {col}_desc ({desc.notna().sum():,} válidos)"
            )

    # =====================================
    # FREIGHT ORIGIN (issuing_plant) E FREIGHT LINK TYPE
    # =====================================

    log_step("Origem do frete (freight_origin) a partir de issuing_plant")

    # A origem física/real do frete é a planta emissora (issuing_plant), não
    # uma inferência a partir de pd_header/vendor_id.
    df["freight_origin"] = (
        df["issuing_plant"]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace("", pd.NA)
    )

    qtd_sem_origem = df["freight_origin"].isna().sum()
    pct_sem_origem = qtd_sem_origem / len(df) * 100 if len(df) else 0

    if "issuing_plant" in [v for _, v in missing_source_cols]:
        log_alert(
            "issuing_plant vem de coluna ausente no arquivo bruto — "
            "freight_origin ficará 100% nulo."
        )
    elif pct_sem_origem > 5:
        log_alert(
            f"freight_origin: {pct_sem_origem:.1f}% sem planta emissora "
            f"({qtd_sem_origem:,} registros)"
        )
    else:
        log_ok(
            f"freight_origin: {pct_sem_origem:.1f}% sem planta emissora — "
            f"dentro do esperado"
        )

    log_debug(
        f"Plantas de origem únicas: {df['freight_origin'].nunique():,}\n"
        + df["freight_origin"].value_counts(dropna=False).head(10).to_string()
    )

    log_step("Classificação de freight_link_type (vínculo com pedido/vendor)")

    # Isto NÃO é a origem do frete — é apenas se o frete está vinculado a um
    # pedido (pd_header) ou é um frete "solto" atrelado direto a um vendor.
    if "pd_header" in [v for _, v in missing_source_cols] or "vendor_id" in [v for _, v in missing_source_cols]:
        log_alert(
            "pd_header e/ou vendor_id vêm de colunas ausentes no arquivo bruto — "
            "freight_link_type provavelmente ficará 100% 'unclassified'."
        )

    tem_pedido = df["pd_header"].fillna("").astype(str).str.strip().ne("")
    tem_vendor = df["vendor_id"].fillna("").astype(str).str.strip().ne("")

    df["freight_link_type"] = np.select(
        [tem_pedido, (~tem_pedido & tem_vendor)],
        ["linked_to_order", "standalone_vendor"],
        default="unclassified",
    )

    freight_link_counts = df["freight_link_type"].value_counts(dropna=False)
    log_debug(f"Distribuição de freight_link_type:\n{freight_link_counts.to_string()}")

    pct_unclassified = (
        freight_link_counts.get("unclassified", 0) / len(df) * 100 if len(df) else 0
    )
    if pct_unclassified > 50:
        log_alert(
            f"freight_link_type: {pct_unclassified:.1f}% ficou 'unclassified' — "
            f"verifique se pd_header/vendor_id estão populados corretamente"
        )
    else:
        log_ok(f"freight_link_type: {pct_unclassified:.1f}% unclassified — dentro do esperado")

    # =====================================
    # CALENDÁRIO
    # =====================================

    log_step("Derivação de colunas de calendário")

    df["year"] = df["created_on"].dt.year
    df["month"] = df["created_on"].dt.month
    df["quarter"] = df["created_on"].dt.quarter

    MESES_PT = {
        1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
        7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
    }

    df["month_name"] = df["month"].map(MESES_PT)
    df["year_month"] = df["created_on"].dt.strftime("%Y-%m")

    log_ok(
        f"Período coberto: {df['year_month'].min()} a {df['year_month'].max()}"
    )


    # =====================================
    # VALIDAÇÃO DO PERÍODO REAL DA BASE
    # =====================================

    log_step("Validação do período real da base")

    periodos_reais = (
        df.loc[df["created_on"].notna(), "created_on"]
        .dt.to_period("M")
        .value_counts()
        .sort_index()
    )

    log_ok(
        f"Primeiro mês real: "
        f"{periodos_reais.index.min() if len(periodos_reais) else 'N/A'}"
    )

    log_ok(
        f"Último mês real: "
        f"{periodos_reais.index.max() if len(periodos_reais) else 'N/A'}"
    )

    log_debug("Meses realmente existentes na base:")

    if len(periodos_reais):
        print(periodos_reais.to_string())
    else:
        log_alert("Nenhuma data válida encontrada em created_on")


    # =====================================
    # LEAD TIME
    # =====================================

    log_step("Cálculo de lead time, atraso e status de conclusão")

    df["lead_time_days"] = (df["finish_date"] - df["created_on"]).dt.days
    df["delivery_delay_days"] = (df["finish_date"] - df["due_date"]).dt.days
    df["is_completed"] = df["finish_date"].notna()

    log_debug(
        f"lead_time_days: média={df['lead_time_days'].mean():.1f} dias, "
        f"nulos={df['lead_time_days'].isna().sum():,}"
    )
    log_debug(
        f"is_completed: {df['is_completed'].sum():,} concluídos de {len(df):,}"
    )

    # =====================================
    # SLA
    # =====================================

    log_step("Cálculo de SLA")

    df["sla_met"] = pd.NA

    mask = df["finish_date"].notna() & df["due_date"].notna()

    df.loc[mask, "sla_met"] = (
        df.loc[mask, "finish_date"] <= df.loc[mask, "due_date"]
    )

    df["sla_met"] = df["sla_met"].astype("boolean")

    sla_counts = df["sla_met"].value_counts(dropna=False)
    log_debug(f"Distribuição de sla_met:\n{sla_counts.to_string()}")

    # =====================================
    # UNIT VALUE
    # =====================================

    log_step("Cálculo de custo por unidade")

    df["cost_per_unit"] = np.where(
        df["quantity"] > 0,
        df["negotiated_value"] / df["quantity"],
        np.nan,
    )

    df["cost_per_unit"] = df["cost_per_unit"].replace([np.inf, -np.inf], np.nan)

    log_debug(
        f"cost_per_unit: {df['cost_per_unit'].notna().sum():,} valores calculados, "
        f"{df['cost_per_unit'].isna().sum():,} nulos (quantity <= 0 ou ausente)"
    )

    # =====================================
    # OTIF
    # =====================================

    log_step("Cálculo de OTIF (on-time)")

    df["on_time"] = np.where(
        df["delivery_delay_days"].notna(),
        (df["delivery_delay_days"] <= 0).astype(int),
        np.nan,
    )

    df["delivery_status"] = np.select(
        [
            df["delivery_delay_days"] < 0,
            df["delivery_delay_days"] == 0,
            df["delivery_delay_days"] > 0,
        ],
        ["early", "on_time", "late"],
        default="unknown",
    )

    log_debug(
        f"delivery_status:\n{df['delivery_status'].value_counts(dropna=False).to_string()}"
    )

    # =====================================
    # SAVINGS
    # =====================================

    log_step("Cálculo de savings")

    if "total_standard_value" in [v for _, v in missing_source_cols]:
        log_alert(
            "total_standard_value vem de coluna ausente no arquivo bruto — "
            "savings_value/savings_pct ficarão inválidos ou distorcidos."
        )

    df["savings_value"] = df["total_standard_value"] - df["negotiated_value"]

    df["savings_pct"] = np.where(
        df["total_standard_value"] > 0,
        (df["savings_value"] / df["total_standard_value"] * 100),
        np.nan,
    )

    log_debug(
        f"savings_value: soma={df['savings_value'].sum():,.2f}, "
        f"nulos={df['savings_value'].isna().sum():,}"
    )

    # =====================================
    # KPI LOGÍSTICOS
    # =====================================

    log_step("Cálculo de KPIs logísticos (cost_per_day, cost_variance, etc.)")

    df["cost_per_day"] = np.where(
        df["lead_time_days"] > 0,
        df["negotiated_value"] / df["lead_time_days"],
        np.nan,
    )

    df["completed_and_on_time"] = np.where(
        (df["is_completed"] & (df["on_time"] == 1)), 1, 0
    )

    df["cost_variance"] = df["negotiated_value"] - df["total_standard_value"]

    df["delay_cost_ratio"] = np.where(
        df["lead_time_days"] > 0,
        df["negotiated_value"] / df["lead_time_days"],
        np.nan,
    )

    log_ok("KPIs logísticos calculados")

    # =====================================
    # QUALIDADE
    # =====================================

    log_step("Relatório de qualidade final")

    for col in DATE_COLS:
        if col in df.columns:
            print(f"    {col}: {df[col].notna().sum():,} válidas")


    # =====================================
    # RESUMO ETL
    # =====================================

    log_step("Resumo final do ETL")

    print(f"    Linhas finais: {len(df):,}")
    print(f"    Colunas finais: {len(df.columns):,}")
    print(f"    Fretes únicos: {df['freight_id'].nunique():,}")
    print(f"    Clientes únicos: {df['customer_id'].nunique():,}")
    print(f"    Transportadoras únicas: {df['service_agent'].nunique():,}")
    print(f"    Valor negociado total: R$ {df['negotiated_value'].sum():,.2f}")
    print(f"    Saving total: R$ {df['savings_value'].sum():,.2f}")

    sla_mean = df["sla_met"].mean()
    if pd.notna(sla_mean):
        print(f"    SLA Médio: {sla_mean*100:.2f}%")
    else:
        log_warn("SLA Médio: não calculável (sem registros válidos)")

    if missing_source_cols:
        log_alert(
            f"ATENÇÃO: {len(missing_source_cols)} coluna(s) mapeada(s) não foram "
            f"encontradas no arquivo bruto nesta execução. Revise a lista impressa "
            f"na etapa 'Mapeamento e renomeação de colunas' antes de usar este "
            f"output em produção."
        )

    # =====================================
    # EXPORT
    # =====================================

    log_step("Exportação para parquet")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Publicação atômica: primeiro grava um arquivo temporário.
    # Só substitui o parquet ativo depois que o write termina com sucesso.
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")

    if temp_path.exists():
        temp_path.unlink()

    try:
        df.to_parquet(temp_path, index=False)
        temp_path.replace(output_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise

    log_ok(f"Arquivo salvo em: {output_path}")

    total_elapsed = time.time() - _t0
    print(f"\n[FIM] Pipeline concluído em {total_elapsed:.2f}s")

    return {
        "input_file": str(input_path),
        "output_file": str(output_path),
        "linhas": int(len(df)),
        "colunas": int(len(df.columns)),
        "fretes_unicos": int(df["freight_id"].nunique()),
        "clientes_unicos": int(df["customer_id"].nunique()),
        "transportadoras_unicas": int(df["service_agent"].nunique()),
        "valor_negociado": float(df["negotiated_value"].sum()),
        "savings_total": float(df["savings_value"].sum()),
        "sla_medio": float(sla_mean) if pd.notna(sla_mean) else None,
    }

if __name__ == "__main__":
    process_historico(INPUT_FILE, OUTPUT_FILE)
