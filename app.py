import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
import os
import unicodedata
import hashlib
import sqlite3
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Dashboard Obstetricia - CG",
    page_icon="🏥",
    layout="wide",
)

# ══════════════════════════════════════════════════════════════════════════════
# LOGIN
# ══════════════════════════════════════════════════════════════════════════════

USERS = {
    "admin": hashlib.sha256("obstetricia2026".encode()).hexdigest(),
}


def check_login():
    if st.session_state.get("authenticated"):
        return True

    # Centralizar e reduzir tamanho
    _, col_mid, _ = st.columns([1, 1.5, 1])

    with col_mid:
        st.markdown(
            "<h2 style='text-align:center;'>Dashboard Obstetricia - CG</h2>"
            "<p style='text-align:center;'>Faca login para acessar o dashboard</p>",
            unsafe_allow_html=True,
        )

        with st.form("login_form"):
            usuario = st.text_input("Usuario")
            senha = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar", use_container_width=True)

        if submitted:
            senha_hash = hashlib.sha256(senha.encode()).hexdigest()
            if usuario in USERS and USERS[usuario] == senha_hash:
                st.session_state["authenticated"] = True
                st.session_state["user"] = usuario
                st.rerun()
            else:
                st.error("Usuario ou senha incorretos.")

    return False


if not check_login():
    st.stop()

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
EXCEL_FILE = os.path.join(DATA_DIR, "Produção AIH's Obstetricia CG_ISEA_CLIPSI_2025.xlsx")
CSV_PAES = os.path.join(DATA_DIR, "pactuacao_paes_2025.csv")
CSV_ITENS = os.path.join(DATA_DIR, "itens_programacao.csv")

MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
BONUS_CLIPSI = 800.0


def fmt_brl(valor):
    """Formata valor em R$ brasileiro."""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_int(valor):
    """Formata inteiro com separador de milhar."""
    return f"{int(valor):,}".replace(",", ".")


def fmt_valor_grafico(v):
    """Formata valor para labels de graficos: M para milhoes, k para mil."""
    if abs(v) >= 1_000_000:
        return f"R$ {v / 1_000_000:,.1f}M"
    elif abs(v) >= 1_000:
        return f"R$ {v / 1_000:,.0f}k"
    else:
        return f"R$ {v:,.0f}"


def normalize_name(name: str) -> str:
    name = str(name).upper().strip()
    name = unicodedata.normalize("NFKD", name)
    return "".join(c for c in name if not unicodedata.combining(c))


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data
def load_pactuacao():
    df = pd.read_csv(CSV_PAES, sep=";")
    df["municipio"] = df["municipio_encaminhador"].astype(str).str.upper().str.strip()
    df["pactuado"] = pd.to_numeric(df["quantidade_pactuada"], errors="coerce").fillna(0).astype(int)
    
    val = df["valor_total"].astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    df["valor_pactuado"] = pd.to_numeric(val, errors="coerce").fillna(0.0)
    
    val_unit = df["valor_unitario"].astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    df["valor_unitario"] = pd.to_numeric(val_unit, errors="coerce").fillna(706.62)
    return df


@st.cache_data
def load_itens_programacao():
    df = pd.read_csv(CSV_ITENS, sep=";")
    df["codigo"] = df["codigo_procedimento"].astype(str).str.zfill(10)
    return df[["codigo", "descricao"]]


def _parse_proc_sheet(df):
    """Parse a procedure sheet returning (qty_df, val_df)."""
    qty_rows, val_rows = [], []
    section = None
    for _, row in df.iterrows():
        val = str(row.iloc[0]) if pd.notna(row.iloc[0]) else ""
        if "QUANTITATIVO" in val.upper():
            section = "qty"; continue
        if "VALORES" in val.upper():
            section = "val"; continue
        if section and re.match(r"^\d{10}\s", val):
            codigo = val[:10]
            descricao = val[11:].strip()
            valores = [row.iloc[c] if pd.notna(row.iloc[c]) else 0 for c in range(1, 13)]
            total = row.iloc[13] if pd.notna(row.iloc[13]) else sum(valores)
            entry = {"codigo": codigo, "descricao": descricao,
                     **{m: v for m, v in zip(MESES, valores)}, "total": total}
            if section == "qty":
                qty_rows.append(entry)
            else:
                val_rows.append(entry)
    return pd.DataFrame(qty_rows), pd.DataFrame(val_rows)


def _parse_mun_sheet(df):
    """Parse a municipality sheet returning (qty_df, val_df)."""
    qty_rows, val_rows = [], []
    section = None
    for _, row in df.iterrows():
        val = str(row.iloc[0]) if pd.notna(row.iloc[0]) else ""
        if "QUANTITATIVO" in val.upper():
            section = "qty"; continue
        if "VALORES" in val.upper():
            section = "val"; continue
        if section and re.match(r"^\d{6}\s", val):
            cod = val[:6]
            nome = val[7:].strip()
            valores = [row.iloc[c] if pd.notna(row.iloc[c]) else 0 for c in range(1, 13)]
            total = row.iloc[13] if pd.notna(row.iloc[13]) else sum(valores)
            entry = {"codigo_ibge": cod, "municipio": nome,
                     **{m: v for m, v in zip(MESES, valores)}, "total": total}
            if section == "qty":
                qty_rows.append(entry)
            else:
                val_rows.append(entry)
    return pd.DataFrame(qty_rows), pd.DataFrame(val_rows)


@st.cache_data
def load_excel():
    import openpyxl
    wb = openpyxl.load_workbook(EXCEL_FILE, read_only=True)
    sn = wb.sheetnames
    wb.close()

    data = {}

    df = pd.read_excel(EXCEL_FILE, sheet_name=sn[0], header=None)
    data["clipsi_proc_qty"], data["clipsi_proc_val"] = _parse_proc_sheet(df)

    df = pd.read_excel(EXCEL_FILE, sheet_name=sn[2], header=None)
    data["isea_proc_qty"], data["isea_proc_val"] = _parse_proc_sheet(df)

    df = pd.read_excel(EXCEL_FILE, sheet_name=sn[1], header=None)
    data["clipsi_mun_qty"], data["clipsi_mun_val"] = _parse_mun_sheet(df)

    df = pd.read_excel(EXCEL_FILE, sheet_name=sn[3], header=None)
    data["isea_mun_qty"], data["isea_mun_val"] = _parse_mun_sheet(df)

    # CPN - Planilha 1
    # A planilha tem duas secoes, cada uma precedida por um header "Procedimentos realizados":
    #   - Primeira secao: quantitativos (ex: row 6)
    #   - Segunda secao: valores/custos SUS (ex: row 11)
    df_cpn = pd.read_excel(EXCEL_FILE, sheet_name="Planilha1", header=None)

    # Encontrar as rows com "Procedimentos realizados" para delimitar secoes
    header_rows = df_cpn.index[df_cpn.iloc[:, 0].astype(str).str.contains("Procedimentos realizados", case=False, na=False)].tolist()

    def _extract_cpn_row(df_section, code):
        found = df_section[df_section.iloc[:, 0].astype(str).str.contains(code, na=False)]
        if not found.empty:
            row = found.iloc[0]
            vals = [pd.to_numeric(row.iloc[c], errors="coerce") for c in range(1, 13)]
            vals = [v if pd.notna(v) else 0 for v in vals]
            return vals
        return [0] * 12

    if len(header_rows) >= 2:
        # Secao de quantitativos: entre o primeiro e o segundo header
        cpn_q_vals = _extract_cpn_row(df_cpn.iloc[header_rows[0]+1:header_rows[1]], "0310010055")
        # Secao de valores/custos: apos o segundo header
        cpn_v_vals = _extract_cpn_row(df_cpn.iloc[header_rows[1]+1:], "0310010055")
    else:
        # Fallback: buscar todas as ocorrencias do codigo e usar primeira como qty, segunda como val
        all_matches = df_cpn[df_cpn.iloc[:, 0].astype(str).str.contains("0310010055", na=False)]
        cpn_q_vals = [0] * 12
        cpn_v_vals = [0] * 12
        if len(all_matches) >= 1:
            row = all_matches.iloc[0]
            cpn_q_vals = [pd.to_numeric(row.iloc[c], errors="coerce") or 0 for c in range(1, 13)]
        if len(all_matches) >= 2:
            row = all_matches.iloc[1]
            cpn_v_vals = [pd.to_numeric(row.iloc[c], errors="coerce") or 0 for c in range(1, 13)]

    data["cpn_proc_qty"] = pd.DataFrame([{
        "codigo": "0310010055", "descricao": "PARTO NORMAL EM CENTRO DE PARTO NORMAL (CPN)",
        **{m: v for m, v in zip(MESES, cpn_q_vals)}, "total": sum(cpn_q_vals)
    }])

    data["cpn_proc_val"] = pd.DataFrame([{
        "codigo": "0310010055", "descricao": "PARTO NORMAL EM CENTRO DE PARTO NORMAL (CPN)",
        **{m: v for m, v in zip(MESES, cpn_v_vals)}, "total": sum(cpn_v_vals)
    }])

    return data


@st.cache_data(ttl=300)
def load_isea_data():
    DB_PATH = os.path.join(DATA_DIR, "saude_real.db")
    if not os.path.exists(DB_PATH):
        return None, None, None
    conn = sqlite3.connect(DB_PATH)

    df_resumo = pd.read_sql_query("""
        SELECT r.competencia,
               COUNT(DISTINCT r.cns_paciente) as pacientes,
               COUNT(DISTINCT r.prontuario) as prontuarios,
               SUM(ap.qtd) as procedimentos,
               SUM(ap.qtd * COALESCE(sm.s_hosp, 0)) as total_sh,
               SUM(ap.qtd * COALESCE(sm.s_prof, 0)) as total_sp,
               SUM(ap.qtd * COALESCE(sm.t_hosp, 0)) as total_th
        FROM aih_records r
        LEFT JOIN aih_procedimentos ap ON r.id_aih = ap.id_aih
        LEFT JOIN sigtap_metadata sm ON sm.proc_cod = ap.proc_cod AND sm.competencia = r.competencia
        GROUP BY r.competencia
        ORDER BY SUBSTR(r.competencia, 4, 4) || SUBSTR(r.competencia, 1, 2)
    """, conn)

    df_procs = pd.read_sql_query("""
        SELECT r.competencia, ap.proc_cod,
               COALESCE(sm.nome, sm_any.nome, '') as proc_nome,
               COALESCE(sm.complexidade, sm_any.complexidade, '') as complexidade,
               sm.s_hosp, sm.s_prof, sm.t_hosp,
               SUM(ap.qtd) as qtd_total,
               SUM(ap.qtd * COALESCE(sm.s_hosp, 0)) as val_sh,
               SUM(ap.qtd * COALESCE(sm.s_prof, 0)) as val_sp,
               SUM(ap.qtd * COALESCE(sm.t_hosp, 0)) as val_th,
               COUNT(DISTINCT r.prontuario) as num_pacientes
        FROM aih_procedimentos ap
        JOIN aih_records r ON r.id_aih = ap.id_aih
        LEFT JOIN sigtap_metadata sm ON sm.proc_cod = ap.proc_cod AND sm.competencia = r.competencia
        LEFT JOIN (
            SELECT proc_cod, nome, complexidade FROM sigtap_metadata
            GROUP BY proc_cod
        ) sm_any ON sm_any.proc_cod = ap.proc_cod
        GROUP BY r.competencia, ap.proc_cod
        ORDER BY val_th DESC
    """, conn)

    df_cidades = pd.read_sql_query("""
        SELECT r.competencia,
               COALESCE(p.cidade, 'Desconhecida') as cidade,
               COUNT(DISTINCT r.prontuario) as pacientes,
               COUNT(*) as registros,
               SUM(ap.qtd) as procedimentos,
               SUM(ap.qtd * COALESCE(sm.s_hosp, 0)) as total_sh,
               SUM(ap.qtd * COALESCE(sm.s_prof, 0)) as total_sp,
               SUM(ap.qtd * COALESCE(sm.t_hosp, 0)) as total_th
        FROM aih_records r
        LEFT JOIN pacientes p ON r.cns_paciente = p.cns
        LEFT JOIN aih_procedimentos ap ON r.id_aih = ap.id_aih
        LEFT JOIN sigtap_metadata sm ON sm.proc_cod = ap.proc_cod AND sm.competencia = r.competencia
        GROUP BY r.competencia, p.cidade
        ORDER BY total_th DESC
    """, conn)

    conn.close()
    return df_resumo, df_procs, df_cidades


# ── Load all data ─────────────────────────────────────────────────────────────

pactuacao = load_pactuacao()
itens = load_itens_programacao()
data = load_excel()

clipsi_pq = data["clipsi_proc_qty"]
clipsi_pv = data["clipsi_proc_val"]
isea_pq = data["isea_proc_qty"]
isea_pv = data["isea_proc_val"]
clipsi_mq = data["clipsi_mun_qty"]
clipsi_mv = data["clipsi_mun_val"]
isea_mq = data["isea_mun_qty"]
isea_mv = data["isea_mun_val"]
cpn_pq = data["cpn_proc_qty"]
cpn_pv = data["cpn_proc_val"]

# ── Separar CPN do ISEA ───────────────────────────────────────────────────────
# 1. Remover procedimento CPN do ISEA
isea_pq = isea_pq[isea_pq["codigo"] != "0310010055"].copy()
isea_pv = isea_pv[isea_pv["codigo"] != "0310010055"].copy()

# 2. Subtrair CPN da linha de Campina Grande no ISEA Municipal (mq/mv)
# O CPN está embutido no ISEA por município como sendo de Campina Grande
mask_cg_q = isea_mq["municipio"] == "CAMPINA GRANDE"
mask_cg_v = isea_mv["municipio"] == "CAMPINA GRANDE"

if mask_cg_q.any():
    for m in MESES + ["total"]:
        isea_mq.loc[mask_cg_q, m] -= cpn_pq[m].values[0]

if mask_cg_v.any():
    for m in MESES + ["total"]:
        isea_mv.loc[mask_cg_v, m] -= cpn_pv[m].values[0]

# CPN municipal data: como vamos excluir o CPN do "Por Municipio", 
# criamos dfs vazios ou com zeros apenas para não quebrar a lógica do selectbox
cpn_mq = isea_mq.iloc[:0].copy()
cpn_mv = isea_mv.iloc[:0].copy()

# ── Derived data ──────────────────────────────────────────────────────────────

clipsi_mq_h = clipsi_mq.copy(); clipsi_mq_h["hospital"] = "CLIPSI"
isea_mq_h = isea_mq.copy(); isea_mq_h["hospital"] = "ISEA"
all_mun_qty = pd.concat([clipsi_mq_h, isea_mq_h], ignore_index=True)

clipsi_mv_h = clipsi_mv.copy(); clipsi_mv_h["hospital"] = "CLIPSI"
isea_mv_h = isea_mv.copy(); isea_mv_h["hospital"] = "ISEA"
all_mun_val = pd.concat([clipsi_mv_h, isea_mv_h], ignore_index=True)

CG_NORM = "CAMPINA GRANDE"

pactuacao["mun_norm"] = pactuacao["municipio"].apply(normalize_name)
pact_agg = pactuacao.groupby("mun_norm").agg(
    pactuado=("pactuado", "sum"),
    valor_pactuado=("valor_pactuado", "sum"),
).reset_index()

real_qty = (
    all_mun_qty.groupby("municipio")[MESES + ["total"]].sum().reset_index()
)
real_qty["mun_norm"] = real_qty["municipio"].apply(normalize_name)

real_val = (
    all_mun_val.groupby("municipio")[MESES + ["total"]].sum().reset_index()
)
real_val["mun_norm"] = real_val["municipio"].apply(normalize_name)

comp = pact_agg.merge(
    real_qty[["mun_norm", "municipio", "total"]].rename(columns={"total": "realizado"}),
    on="mun_norm", how="outer",
)
comp["municipio"] = comp["municipio"].fillna(comp["mun_norm"])
comp["pactuado"] = comp["pactuado"].fillna(0).astype(int)
comp["realizado"] = comp["realizado"].fillna(0).astype(int)

real_val_total = real_val[["mun_norm", "total"]].rename(columns={"total": "valor_realizado"})
comp = comp.merge(real_val_total, on="mun_norm", how="left")
comp["valor_realizado"] = comp["valor_realizado"].fillna(0)
comp["valor_pactuado"] = comp["valor_pactuado"].fillna(0)

comp_sem_cg = comp[comp["mun_norm"] != CG_NORM].copy()
comp_sem_cg["pct_execucao"] = (
    comp_sem_cg["realizado"] / comp_sem_cg["pactuado"].replace(0, 1) * 100
).round(1)
comp_sem_cg = comp_sem_cg.sort_values("pactuado", ascending=False)

cg_qty = real_qty[real_qty["mun_norm"] == CG_NORM]["total"].sum()
cg_val = real_val[real_val["mun_norm"] == CG_NORM]["total"].sum()

comp["custo_producao"] = comp["valor_realizado"]

cidades_nao_pactuadas = comp[(comp["pactuado"] == 0) & (comp["realizado"] > 0) & (comp["mun_norm"] != CG_NORM)]
custo_nao_pactuadas = cidades_nao_pactuadas["custo_producao"].sum()

cidades_pactuadas = comp[(comp["pactuado"] > 0) & (comp["mun_norm"] != CG_NORM)].copy()
cidades_pactuadas["pct_execucao"] = (
    cidades_pactuadas["realizado"] / cidades_pactuadas["pactuado"].replace(0, 1) * 100
).round(1)
cidades_pactuadas["qtde_acima"] = (cidades_pactuadas["realizado"] - cidades_pactuadas["pactuado"]).clip(lower=0)
cidades_pactuadas["custo_excedente"] = 0.0
mask_acima = cidades_pactuadas["realizado"] > 0
cidades_pactuadas.loc[mask_acima, "custo_excedente"] = (
    (cidades_pactuadas.loc[mask_acima, "qtde_acima"] / cidades_pactuadas.loc[mask_acima, "realizado"]) * 
    cidades_pactuadas.loc[mask_acima, "valor_realizado"]
)
custo_excedente_pactuadas = cidades_pactuadas["custo_excedente"].sum()

custo_cg_interno = comp[comp["mun_norm"] == CG_NORM]["custo_producao"].sum()


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

st.sidebar.markdown(f"**Logado como:** {st.session_state.get('user', '')}")
if st.sidebar.button("Sair"):
    st.session_state["authenticated"] = False
    st.session_state.pop("user", None)
    st.rerun()

st.sidebar.title("Navegação - CG 2025")
view = st.sidebar.radio(
    "Secao",
    [
        "Visao Geral",
        "Por Hospital",
        "Por Procedimento",
        "Por Municipio",
        "Pactuacao vs Realizado",
        "Custos Detalhados (SUS)",
        "Custos Reais (SIGTAP)",
        "ISEA - Gastos Mensal",
        "ISEA - Procedimentos",
        "ISEA - Pacientes e Cidades",
        "ISEA - Consulta Prontuario",
        "Tabela SIGTAP",
    ],
)

components.html(
    """
    <script>
        var doc = window.parent.document;
        var main = doc.querySelector('.main');
        if (main) main.scrollTo(0, 0);
    </script>
    """,
    height=0,
)


# ══════════════════════════════════════════════════════════════════════════════
# 1. VISAO GERAL
# ══════════════════════════════════════════════════════════════════════════════

if view == "Visao Geral":
    st.title("Dashboard Obstetricia - Campina Grande 2025")
    st.caption("Visao Geral Financeira e de Producao de AIH's Aprovadas - ISEA e CLIPSI")

    isea_total_qty = isea_pq[MESES].sum().sum()
    clipsi_total_qty = clipsi_pq[MESES].sum().sum()
    cpn_total_qty = cpn_pq[MESES].sum().sum()
    total_qty = isea_total_qty + clipsi_total_qty + cpn_total_qty

    isea_total_val = isea_pv[MESES].sum().sum()
    clipsi_total_val = clipsi_pv[MESES].sum().sum()
    cpn_total_val = cpn_pv[MESES].sum().sum()
    clipsi_bonus = clipsi_total_qty * BONUS_CLIPSI
    
    total_custo_sus = isea_total_val + clipsi_total_val + cpn_total_val
    total_receita_pactuacao = pactuacao["valor_pactuado"].sum()
    
    # Nova Logica: Unica receita é a pactuacao. SUS e Bonus viram custos (operacionais)
    receita_total = total_receita_pactuacao
    
    custo_operacional_sus = total_custo_sus + clipsi_bonus
    # O Custo Excedente + Nao Pactuados + Uso Interno ja era medido com base no ticket do SUS
    # Para evitar dupla contagem, o custo_total será a soma de todo SUS + Bonificacao.
    # Mas a visualizacao vai poder quebrar isso entre (Interno, Excedente, Nao Pactuados, Auxilio CLIPSI).
    custo_total = custo_operacional_sus

    st.subheader("Resumo Executivo Financeiro")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.markdown(f"**Receita Total (Pactuacao)**<br><h2 style='color: #28a745; margin-top: 0;'>{fmt_brl(receita_total)}</h2>", unsafe_allow_html=True)
    col2.markdown(f"**Custo Total Estimado (SUS + Bonif.)**<br><h2 style='color: #dc3545; margin-top: 0;'>{fmt_brl(custo_total)}</h2>", unsafe_allow_html=True)
    col3.markdown(f"**Custo Producao SUS**<br><h2 style='color: #dc3545; margin-top: 0;'>{fmt_brl(total_custo_sus)}</h2>", unsafe_allow_html=True)
    col4.markdown(f"**Custo c/ Bonificacao CLIPSI**<br><h2 style='color: #dc3545; margin-top: 0;'>{fmt_brl(clipsi_bonus)}</h2>", unsafe_allow_html=True)
    
    st.markdown("---")
    
    st.subheader("Detalhamento dos Custos de Producao")
    cc1, cc2, cc3, cc4 = st.columns(4)
    cc1.markdown(f"**Custo Municípios Pactuados (Estimado)**<br><h3 style='color: #dc3545; margin-top: 0;'>{fmt_brl(custo_total - (custo_excedente_pactuadas + custo_nao_pactuadas + custo_cg_interno))}</h3>", unsafe_allow_html=True)
    cc2.markdown(f"**Uso Interno (CG)**<br><h3 style='color: #dc3545; margin-top: 0;'>{fmt_brl(custo_cg_interno)}</h3>", unsafe_allow_html=True)
    cc3.markdown(f"**Nao Pactuadas (Deficitario)**<br><h3 style='color: #dc3545; margin-top: 0;'>{fmt_brl(custo_nao_pactuadas)}</h3>", unsafe_allow_html=True)
    cc4.markdown(f"**Uso Acima da Meta (Deficitario)**<br><h3 style='color: #dc3545; margin-top: 0;'>{fmt_brl(custo_excedente_pactuadas)}</h3>", unsafe_allow_html=True)
    
    st.markdown("---")
    
    saldo = receita_total - custo_total
    cor_saldo = "🟢 Ganho (Superavit)" if saldo >= 0 else "🔴 Perda (Deficit)"
    st.subheader(f"Resultado Financeiro: {cor_saldo}")
    cor_hexa = "#28a745" if saldo >= 0 else "#dc3545"
    st.markdown(f"**Saldo Liquido (Receitas - Custos Estimados)**<br><h1 style='color: {cor_hexa}; margin-top: 0;'>{fmt_brl(saldo)}</h1>", unsafe_allow_html=True)
    
    st.divider()

    col_tabela, col_grafico = st.columns(2)
    
    with col_grafico:
        # Composicao do custo operacional (SUS + Bonif)
        df_custo_geral = pd.DataFrame({
            "Categoria": ["ISEA (SUS)", "CLIPSI (SUS)", "CPN (SUS)", "Bonificacao CLIPSI"],
            "Valor": [isea_total_val, clipsi_total_val, cpn_total_val, clipsi_bonus]
        })
        fig_rec = px.pie(df_custo_geral, values="Valor", names="Categoria", title="Composicao do Custo Operacional", hole=0.4,
                         color_discrete_sequence=["#1976D2", "#FF9800", "#4CAF50", "#FFC107"])
        fig_rec.update_traces(textinfo="percent+value", texttemplate="%{percent}<br>R$ %{value:,.0f}")
        st.plotly_chart(fig_rec, use_container_width=True)
        
        df_custo_exec = pd.DataFrame({
            "Categoria": ["Coberto (Pactuado)", "Uso Interno (CG)", "Nao Pactuadas", "Excedente Pactuadas"],
            "Valor": [custo_total - (custo_excedente_pactuadas + custo_nao_pactuadas + custo_cg_interno), custo_cg_interno, custo_nao_pactuadas, custo_excedente_pactuadas]
        })
        fig_custo = px.pie(df_custo_exec, values="Valor", names="Categoria", title="Distribuicao do Custo por Perfil de Atendimento",
                           hole=0.4, color_discrete_sequence=["#4CAF50", "#2196F3", "#9C27B0", "#E91E63"])
        fig_custo.update_traces(textinfo="percent+value", texttemplate="%{percent}<br>R$ %{value:,.0f}")
        st.plotly_chart(fig_custo, use_container_width=True)

    with col_tabela:
        st.write("##### Top 10 Cidades Não Pactuadas (Maiores Custos)")
        df_np = cidades_nao_pactuadas.sort_values("custo_producao", ascending=False).head(10)
        df_np_show = df_np[["municipio", "realizado", "custo_producao"]].copy()
        df_np_show["custo_producao"] = df_np_show["custo_producao"].apply(fmt_brl)
        df_np_show.columns = ["Municipio", "Qtde Utilizada", "Custo Gerado"]
        st.dataframe(df_np_show, use_container_width=True, hide_index=True)
        
        st.write("##### Top 10 Cidades Pactuadas com Maior Excedente")
        df_pe = cidades_pactuadas.sort_values("custo_excedente", ascending=False).head(10)
        df_pe_show = df_pe[["municipio", "pactuado", "realizado", "qtde_acima", "custo_excedente"]].copy()
        df_pe_show["custo_excedente"] = df_pe_show["custo_excedente"].apply(fmt_brl)
        df_pe_show.columns = ["Municipio", "Pactuado", "Realizado", "Excedente Qtde", "Custo Excedente"]
        st.dataframe(df_pe_show, use_container_width=True, hide_index=True)
        
        st.write("##### Uso Interno - Campina Grande")
        df_cg = comp[comp["mun_norm"] == CG_NORM][["municipio", "realizado", "custo_producao"]].copy()
        df_cg["custo_producao"] = df_cg["custo_producao"].apply(fmt_brl)
        df_cg.columns = ["Municipio", "Qtde Utilizada", "Custo Producao"]
        st.dataframe(df_cg, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# 2. POR HOSPITAL
# ══════════════════════════════════════════════════════════════════════════════

elif view == "Por Hospital":
    st.title("Comparativo por Hospital - Campina Grande 2025")

    col_i, col_c, col_cpn = st.columns(3)

    isea_qty_total = isea_pq[MESES].sum().sum()
    clipsi_qty_total = clipsi_pq[MESES].sum().sum()
    cpn_qty_total = cpn_pq[MESES].sum().sum()
    
    isea_val_total = isea_pv[MESES].sum().sum()
    clipsi_val_total = clipsi_pv[MESES].sum().sum()
    cpn_val_total = cpn_pv[MESES].sum().sum()

    with col_i:
        st.subheader("ISEA")
        st.metric("Procedimentos", fmt_int(isea_qty_total))
        st.metric("Custo SUS", fmt_brl(isea_val_total))
        st.metric("Ticket Medio", fmt_brl(isea_val_total / isea_qty_total if isea_qty_total else 0))
        st.metric("Tipos de Procedimento", len(isea_pq))
        st.metric("Municipios Atendidos", len(isea_mq))

    with col_c:
        st.subheader("CLIPSI")
        st.metric("Procedimentos", fmt_int(clipsi_qty_total))
        st.metric("Custo SUS", fmt_brl(clipsi_val_total))
        st.metric("Bonificacao CLIPSI", fmt_brl(clipsi_qty_total * BONUS_CLIPSI))
        st.metric("Custo SUS + Bonificacao", fmt_brl(clipsi_val_total + clipsi_qty_total * BONUS_CLIPSI))
        st.metric("Ticket Medio (SUS)", fmt_brl(clipsi_val_total / clipsi_qty_total if clipsi_qty_total else 0))
        st.metric("Ticket Medio (SUS + Bonif.)", fmt_brl((clipsi_val_total / clipsi_qty_total if clipsi_qty_total else 0) + BONUS_CLIPSI))
        st.metric("Tipos de Procedimento", len(clipsi_pq))
    with col_cpn:
        st.subheader("CPN")
        st.metric("Procedimentos", fmt_int(cpn_qty_total))
        st.metric("Custo SUS Estimado", fmt_brl(cpn_val_total), delta_color="inverse")
        st.metric("Ticket Medio (Custo)", fmt_brl(cpn_val_total / cpn_qty_total if cpn_qty_total else 0), delta_color="inverse")
        st.metric("Tipos de Procedimento", len(cpn_pq))

    st.divider()

    st.subheader("Parto Normal vs Cesariano")
    isea_normais = isea_pq[isea_pq["codigo"].isin(["0310010039", "0310010047", "0310010055"])]["total"].sum()
    isea_cesarianos = isea_pq[isea_pq["codigo"].isin(["0411010026", "0411010034", "0411010042"])]["total"].sum()
    isea_outros = isea_qty_total - isea_normais - isea_cesarianos

    clipsi_normais = clipsi_pq[clipsi_pq["codigo"] == "0310010039"]["total"].sum()
    clipsi_cesarianos = clipsi_pq[clipsi_pq["codigo"] == "0411010034"]["total"].sum()
    clipsi_outros = clipsi_qty_total - clipsi_normais - clipsi_cesarianos

    col_a, col_b = st.columns(2)
    with col_a:
        df_pie_isea = pd.DataFrame({
            "Tipo": ["Parto Normal", "Parto Cesariano", "Outros"],
            "Quantidade": [isea_normais, isea_cesarianos, isea_outros],
        })
        fig = px.pie(df_pie_isea, values="Quantidade", names="Tipo",
                     title=f"ISEA - Mix de Procedimentos",
                     color="Tipo",
                     color_discrete_map={
                         "Parto Normal": "#4CAF50",
                         "Parto Cesariano": "#F44336",
                         "Outros": "#9E9E9E"
                     }, hole=0.4)
        st.plotly_chart(fig, use_container_width=True)

        # Detalhamento de Outros ISEA
        st.write("###### Principais em 'Outros' (ISEA)")
        isea_outros_rows = isea_pq[~isea_pq["codigo"].isin(["0310010039", "0310010047", "0310010055", "0411010026", "0411010034", "0411010042"])].sort_values("total", ascending=True).tail(5)
        # Usando uma paleta variada que evita tons de vermelho, verde e cinza puros
        fig_oi = px.bar(isea_outros_rows, x="total", y="descricao", orientation="h", height=250, 
                        color="descricao",
                        color_discrete_sequence=["#1976D2", "#FF9800", "#9C27B0", "#00BCD4", "#E91E63"])
        fig_oi.update_layout(xaxis_title="", yaxis_title="", showlegend=False, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig_oi, use_container_width=True)

    with col_b:
        df_pie_clipsi = pd.DataFrame({
            "Tipo": ["Parto Normal", "Parto Cesariano", "Outros"],
            "Quantidade": [clipsi_normais, clipsi_cesarianos, clipsi_outros],
        })
        fig = px.pie(df_pie_clipsi, values="Quantidade", names="Tipo",
                     title=f"CLIPSI - Mix de Procedimentos",
                     color="Tipo",
                     color_discrete_map={
                         "Parto Normal": "#4CAF50",
                         "Parto Cesariano": "#F44336",
                         "Outros": "#9E9E9E"
                     }, hole=0.4)
        st.plotly_chart(fig, use_container_width=True)

        # Detalhamento de Outros CLIPSI
        st.write("###### Principais em 'Outros' (CLIPSI)")
        clipsi_outros_rows = clipsi_pq[~clipsi_pq["codigo"].isin(["0310010039", "0310010047", "0310010055", "0411010026", "0411010034", "0411010042"])].sort_values("total", ascending=True).tail(5)
        # Usando uma paleta variada que evita tons de vermelho, verde e cinza puros
        fig_oc = px.bar(clipsi_outros_rows, x="total", y="descricao", orientation="h", height=250, 
                        color="descricao",
                        color_discrete_sequence=["#1976D2", "#FF9800", "#9C27B0", "#00BCD4", "#E91E63"])
        fig_oc.update_layout(xaxis_title="", yaxis_title="", showlegend=False, margin=dict(l=0, r=0, t=30, b=0))
        st.plotly_chart(fig_oc, use_container_width=True)

    st.subheader("Evolucao Mensal Comparativa")
    isea_m = isea_pq[MESES].sum()
    clipsi_m = clipsi_pq[MESES].sum()
    cpn_m = cpn_pq[MESES].sum()
    df_comp_h = pd.DataFrame({"Mes": MESES, "ISEA": isea_m.values, "CLIPSI": clipsi_m.values, "CPN": cpn_m.values})

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_comp_h["Mes"], y=df_comp_h["ISEA"], name="ISEA",
                             mode="lines+markers", line=dict(color="#1976D2", width=3)))
    fig.add_trace(go.Scatter(x=df_comp_h["Mes"], y=df_comp_h["CLIPSI"], name="CLIPSI",
                             mode="lines+markers", line=dict(color="#FF9800", width=3)))
    fig.add_trace(go.Scatter(x=df_comp_h["Mes"], y=df_comp_h["CPN"], name="CPN",
                             mode="lines+markers", line=dict(color="#4CAF50", width=3)))
    fig.update_layout(title="Quantidade de Procedimentos - Mes a Mes", height=400)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Procedimentos por Hospital")
    col_a, col_b, col_cpn_r = st.columns(3)
    with col_a:
        df_r = isea_pq[["descricao", "total"]].sort_values("total", ascending=True)
        fig = px.bar(df_r, x="total", y="descricao", orientation="h",
                     title="ISEA - Ranking de Procedimentos", height=500,
                     color="total", color_continuous_scale="Blues")
        fig.update_layout(yaxis_title="", xaxis_title="Quantidade", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        df_r = clipsi_pq[["descricao", "total"]].sort_values("total", ascending=True)
        fig = px.bar(df_r, x="total", y="descricao", orientation="h",
                     title="CLIPSI - Ranking de Procedimentos", height=500,
                     color="total", color_continuous_scale="Oranges")
        fig.update_layout(yaxis_title="", xaxis_title="Quantidade", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with col_cpn_r:
        df_r = cpn_pq[["descricao", "total"]].sort_values("total", ascending=True)
        fig = px.bar(df_r, x="total", y="descricao", orientation="h",
                     title="CPN - Ranking de Procedimentos", height=500,
                     color="total", color_continuous_scale="Greens")
        fig.update_layout(yaxis_title="", xaxis_title="Quantidade", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# 3. POR PROCEDIMENTO
# ══════════════════════════════════════════════════════════════════════════════

elif view == "Por Procedimento":
    st.title("Analise por Procedimento - Campina Grande 2025")

    hospital = st.sidebar.selectbox("Hospital", ["Ambos", "ISEA", "CLIPSI", "CPN"])
    
    if hospital == "Ambos":
        # Concatenar e agrupar para somar estatisticas de todos os hospitais
        pq_merged = pd.concat([isea_pq, clipsi_pq, cpn_pq])
        pq = pq_merged.groupby("codigo").agg({
            "descricao": "first",
            "total": "sum",
            **{m: "sum" for m in MESES}
        }).reset_index()
        
        pv_merged = pd.concat([isea_pv, clipsi_pv, cpn_pv])
        pv = pv_merged.groupby("codigo").agg({
            "descricao": "first",
            "total": "sum",
            **{m: "sum" for m in MESES}
        }).reset_index()
    else:
        if hospital == "ISEA":
            pq = isea_pq; pv = isea_pv
        elif hospital == "CLIPSI":
            pq = clipsi_pq; pv = clipsi_pv
        else:
            pq = cpn_pq; pv = cpn_pv

    selected = st.selectbox("Procedimento", pq["descricao"].tolist())
    row_q = pq[pq["descricao"] == selected].iloc[0]

    # Buscar valor correspondente
    row_v = pv[pv["codigo"] == row_q["codigo"]]
    has_val = len(row_v) > 0

    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Anual", fmt_int(row_q["total"]))
    c2.metric("Media Mensal", fmt_int(row_q["total"] / 12))
    if has_val:
        rv = row_v.iloc[0]
        c3.metric("Custo Total SUS", fmt_brl(rv["total"]))
        ticket = rv["total"] / row_q["total"] if row_q["total"] > 0 else 0
        c4.metric("Custo Medio/Proc", fmt_brl(ticket))

    # Trend mensal (qty + valor)
    df_trend = pd.DataFrame({
        "Mes": MESES,
        "Quantidade": [row_q[m] for m in MESES],
    })
    if has_val:
        df_trend["Custo (R$)"] = [rv[m] for m in MESES]

    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_trend["Mes"], y=df_trend["Quantidade"], name="Quantidade", marker_color="#1976D2"))
    if has_val:
        fig.add_trace(go.Scatter(x=df_trend["Mes"], y=df_trend["Custo (R$)"], name="Custo (R$)",
                                 yaxis="y2", mode="lines+markers", line=dict(color="#E91E63", width=2)))
        fig.update_layout(yaxis2=dict(title="Custo (R$)", overlaying="y", side="right"))
    fig.update_layout(title=f"{selected}", height=400, yaxis_title="Quantidade")
    st.plotly_chart(fig, use_container_width=True)

    # Comparativo todos os procedimentos
    st.subheader("Evolucao de Todos os Procedimentos")
    melted = pq.melt(id_vars=["descricao"], value_vars=MESES, var_name="Mes", value_name="Quantidade")
    fig2 = px.line(melted, x="Mes", y="Quantidade", color="descricao", height=500,
                   title=f"Todos os Procedimentos - {hospital}")
    fig2.update_layout(legend=dict(orientation="h", yanchor="top", y=-0.2))
    st.plotly_chart(fig2, use_container_width=True)

    # Valor medio por procedimento
    if has_val:
        st.subheader("Custo Medio por Procedimento")
        merged_pv = pq[["codigo", "descricao", "total"]].merge(
            pv[["codigo", "total"]].rename(columns={"total": "valor_total"}),
            on="codigo", how="inner",
        )
        merged_pv["valor_medio"] = merged_pv["valor_total"] / merged_pv["total"].replace(0, 1)
        merged_pv = merged_pv.sort_values("valor_medio", ascending=True)
        fig3 = px.bar(merged_pv, x="valor_medio", y="descricao", orientation="h",
                      title=f"Custo Medio por Procedimento - {hospital}", height=500,
                      color="valor_medio", color_continuous_scale="Viridis")
        fig3.update_layout(yaxis_title="", xaxis_title="Custo Medio (R$)")
        st.plotly_chart(fig3, use_container_width=True)

    # Tabela itens de programacao
    with st.expander("Itens de Programacao (MC/Obstetricia)"):
        st.dataframe(itens, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# 4. POR MUNICIPIO
# ══════════════════════════════════════════════════════════════════════════════

elif view == "Por Municipio":
    st.title("Producao por Municipio - Campina Grande 2025")

    hospital = st.sidebar.selectbox("Hospital", ["Ambos", "ISEA", "CLIPSI", "CPN"])
    excluir_cg = st.sidebar.checkbox("Excluir Campina Grande", value=True)
    top_n = st.sidebar.slider("Top N municipios", 10, 50, 20)

    if hospital == "CPN":
        st.warning("Dados por municipio nao disponiveis separadamente para o CPN (integrados no ISEA na planilha original). Selecionando ISEA...")
        hospital = "ISEA"

    # Selecionar dataset
    if hospital == "ISEA":
        mq = isea_mq.copy(); mv = isea_mv.copy()
    elif hospital == "CLIPSI":
        mq = clipsi_mq.copy(); mv = clipsi_mv.copy()
    else: # Ambos
        mq = all_mun_qty.groupby("municipio")[MESES + ["total"]].sum().reset_index()
        mv = all_mun_val.groupby("municipio")[MESES + ["total"]].sum().reset_index()

    # Adicionar pactuacao para comparativo
    mv["mun_norm"] = mv["municipio"].apply(normalize_name)
    mv = mv.merge(pact_agg[["mun_norm", "valor_pactuado"]], on="mun_norm", how="left").fillna(0)

    if excluir_cg:
        mq = mq[mq["municipio"] != "CAMPINA GRANDE"]
        mv = mv[mv["municipio"] != "CAMPINA GRANDE"]

    mq = mq.sort_values("total", ascending=False)

    # Destaque CG
    cg_row = all_mun_qty[all_mun_qty["municipio"] == "CAMPINA GRANDE"]
    if not excluir_cg and len(cg_row) > 0:
        cg_total = cg_row["total"].sum()
        demais = mq[mq["municipio"] != "CAMPINA GRANDE"]["total"].sum()
        st.info(
            f"Campina Grande (municipio executor): {fmt_int(cg_total)} procedimentos "
            f"({cg_total/((cg_total+demais) or 1)*100:.1f}% do total) - demanda propria de residentes"
        )

    # Top N rankings
    df_top_q = mq.head(top_n)
    fig_q = px.bar(df_top_q, x="municipio", y="total",
                 title=f"Top {top_n} Municipios - Quantidade AIH's",
                 color="total", color_continuous_scale="Blues", height=450)
    fig_q.update_layout(xaxis_tickangle=-45, xaxis_title="", yaxis_title="Quantidade")
    st.plotly_chart(fig_q, use_container_width=True)

    mv_sorted_p = mv.sort_values("valor_pactuado", ascending=False).head(top_n)
    fig_p = px.bar(mv_sorted_p, x="municipio", y="valor_pactuado",
                  title=f"Top {top_n} Municipios - Receita Pactuado (R$)",
                  color="valor_pactuado", color_continuous_scale="Greens", height=450)
    fig_p.update_layout(xaxis_tickangle=-45, xaxis_title="", yaxis_title="Receita (R$)")
    st.plotly_chart(fig_p, use_container_width=True)

    mv_sorted_c = mv.sort_values("total", ascending=False).head(top_n)
    fig_c = px.bar(mv_sorted_c, x="municipio", y="total",
                  title=f"Top {top_n} Municipios - Custo SUS (R$)",
                  color="total", color_continuous_scale="Reds", height=450)
    fig_c.update_layout(xaxis_tickangle=-45, xaxis_title="", yaxis_title="Custo (R$)")
    st.plotly_chart(fig_c, use_container_width=True)

    # Detalhamento mensal financeiro comparativo
    st.subheader("Evolucao Mensal: Custo Real vs Receita Pactuacao")
    mun_list = sorted(mq["municipio"].unique())
    default_idx = mun_list.index("CAMPINA GRANDE") if "CAMPINA GRANDE" in mun_list else 0
    selected_mun = st.selectbox("Municipio para Analise Financeira", mun_list, index=default_idx)

    # Dados de custo
    m_row_v = mv[mv["municipio"] == selected_mun].iloc[0]
    custo_mensal = [m_row_v[m] for m in MESES]
    pacto_anual = m_row_v["valor_pactuado"]
    pacto_mensal = [pacto_anual / 12] * 12

    df_fin_comp = pd.DataFrame({
        "Mes": MESES,
        "Custo Real (Producao)": custo_mensal,
        "Receita Estimada (Pactuacao)": pacto_mensal
    })

    fig_fin = go.Figure()
    fig_fin.add_trace(go.Bar(x=df_fin_comp["Mes"], y=df_fin_comp["Custo Real (Producao)"], 
                             name="Custo Real (Producao)", marker_color="#dc3545"))
    fig_fin.add_trace(go.Scatter(x=df_fin_comp["Mes"], y=df_fin_comp["Receita Estimada (Pactuacao)"], 
                                 name="Receita Mensal (Pacto/12)", mode="lines+markers", 
                                 line=dict(color="#28a745", width=3, dash="dash")))
    
    fig_fin.update_layout(title=f"Comparativo Financeiro Mensal - {selected_mun}",
                          yaxis_title="R$", height=400)
    st.plotly_chart(fig_fin, use_container_width=True)

    st.divider()

    # Detalhamento mensal (Produtivo - Antigo)
    st.subheader("Evolucao Mensal de Producao (AIH's)")
    if hospital == "Ambos":
        m_isea = isea_mq[isea_mq["municipio"] == selected_mun][MESES].sum()
        m_clipsi = clipsi_mq[clipsi_mq["municipio"] == selected_mun][MESES].sum()
        df_det = pd.DataFrame({"Mes": MESES, "ISEA": m_isea.values, "CLIPSI": m_clipsi.values})
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(x=df_det["Mes"], y=df_det["ISEA"], name="ISEA", marker_color="#1976D2"))
        fig2.add_trace(go.Bar(x=df_det["Mes"], y=df_det["CLIPSI"], name="CLIPSI", marker_color="#FF9800"))
        fig2.update_layout(title=f"Producao Mensal - {selected_mun}", barmode="stack", height=400)
    else:
        m_data = mq[mq["municipio"] == selected_mun][MESES].sum()
        df_det = pd.DataFrame({"Mes": MESES, "Quantidade": m_data.values})
        fig2 = px.bar(df_det, x="Mes", y="Quantidade", title=f"Producao Mensal - {selected_mun}", height=400)
    st.plotly_chart(fig2, use_container_width=True)

    

    # Tabela completa
    with st.expander("Tabela Completa - Quantitativo"):
        st.dataframe(mq[["municipio"] + MESES + ["total"]], use_container_width=True, hide_index=True)
    with st.expander("Tabela Completa - Valores (R$)"):
        st.dataframe(mv[["municipio"] + MESES + ["total"]], use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# 5. PACTUACAO VS REALIZADO
# ══════════════════════════════════════════════════════════════════════════════

elif view == "Pactuacao vs Realizado":
    st.title("Pactuacao vs Realizado - Campina Grande 2025")
    st.caption(
        "Comparacao entre a quantidade pactuada por municipio encaminhador e a producao real (ISEA + CLIPSI). "
        "Campina Grande e o municipio executor e nao consta na pactuacao."
    )

    show_only_pact = st.sidebar.checkbox("Apenas com pactuacao", value=True)
    top_n = st.sidebar.slider("Top N municipios", 10, 50, 25)

    df_c = comp_sem_cg.copy()
    if show_only_pact:
        df_c = df_c[df_c["pactuado"] > 0]

    # KPIs
    total_pact = df_c["pactuado"].sum()
    total_real = df_c["realizado"].sum()
    pct_geral = (total_real / total_pact * 100) if total_pact > 0 else 0
    mun_acima = len(df_c[df_c["pct_execucao"] > 100])
    mun_abaixo = len(df_c[(df_c["pct_execucao"] <= 100) & (df_c["pactuado"] > 0)])

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Pactuado", fmt_int(total_pact))
    c2.metric("Total Realizado", fmt_int(total_real))
    c3.metric("% Execucao", f"{pct_geral:.1f}%")
    c4.metric("Acima da Meta", mun_acima)
    c5.metric("Abaixo da Meta", mun_abaixo)

    # Demanda propria CG
    st.info(f"Campina Grande (demanda propria): {fmt_int(cg_qty)} procedimentos / {fmt_brl(cg_val)} em custo base SUS")

    st.divider()

    # Barras agrupadas pactuado vs realizado
    df_top = df_c[df_c["pactuado"] > 0].sort_values("pactuado", ascending=False).head(top_n)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_top["municipio"], y=df_top["pactuado"], name="Pactuado", marker_color="#90CAF9"))
    fig.add_trace(go.Bar(x=df_top["municipio"], y=df_top["realizado"], name="Realizado", marker_color="#1976D2"))
    fig.update_layout(
        title=f"Top {top_n} Municipios - Pactuado vs Realizado",
        barmode="group", height=500, xaxis_tickangle=-45,
        xaxis_title="", yaxis_title="Quantidade",
    )
    st.plotly_chart(fig, use_container_width=True)

    # % execucao horizontal
    df_pct = df_c[df_c["pactuado"] > 0].sort_values("pct_execucao", ascending=True)
    fig2 = px.bar(
        df_pct, x="pct_execucao", y="municipio", orientation="h",
        title="% Execucao da Pactuacao por Municipio",
        color="pct_execucao", color_continuous_scale="RdYlGn",
        height=max(400, len(df_pct) * 22),
        text="pct_execucao",
        hover_data={"pct_execucao": ":.1f", "pactuado": True, "realizado": True}
    )
    fig2.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
    fig2.add_vline(x=100, line_dash="dash", line_color="red", annotation_text="Meta 100%")
    fig2.update_layout(xaxis_title="% Execucao", yaxis_title="", hovermode="y unified")
    st.plotly_chart(fig2, use_container_width=True)

    # Tabelas acima/abaixo
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Acima da Meta (>100%)")
        above = cidades_pactuadas[cidades_pactuadas["pct_execucao"] > 100][["municipio", "pactuado", "realizado", "pct_execucao", "custo_excedente"]].sort_values("pct_execucao", ascending=False)
        above["custo_excedente"] = above["custo_excedente"].apply(fmt_brl)
        above.columns = ["Municipio", "Pactuado", "Realizado", "% Exec.", "Custo Excedente (R$)"]
        st.dataframe(above, use_container_width=True, hide_index=True)

    with col_b:
        st.subheader("Abaixo da Meta")
        below = cidades_pactuadas[cidades_pactuadas["pct_execucao"] < 100][["municipio", "pactuado", "realizado", "pct_execucao"]].sort_values("pct_execucao")
        below.columns = ["Municipio", "Pactuado", "Realizado", "% Exec."]
        st.dataframe(below, use_container_width=True, hide_index=True)

    # Municipios sem pactuacao com producao
    if len(cidades_nao_pactuadas) > 0:
        st.subheader(f"Municipios SEM Pactuacao com Producao ({len(cidades_nao_pactuadas)})")
        st.caption("Demanda espontanea - municipios que encaminharam pacientes sem pactuacao formal")
        sem_pact_show = cidades_nao_pactuadas[["municipio", "realizado", "custo_producao"]].sort_values("realizado", ascending=False).copy()
        
        # Grafico dos nao pactuados
        fig_np = px.bar(
            sem_pact_show.head(15), x="municipio", y="realizado",
            title="Top 15 Cidades Não Pactuadas por Quantidade Realizada",
            color="realizado", color_continuous_scale="Reds"
        )
        fig_np.update_layout(xaxis_title="", yaxis_title="Quantidade", xaxis_tickangle=-45)
        st.plotly_chart(fig_np, use_container_width=True)
        
        sem_pact_show["custo_producao"] = sem_pact_show["custo_producao"].apply(fmt_brl)
        sem_pact_show.columns = ["Municipio", "Realizado", "Custo Gerado (R$)"]
        st.dataframe(sem_pact_show, use_container_width=True, hide_index=True)

    # Tabela completa
    with st.expander("Tabela Completa (Cidades Pactuadas)"):
        df_show = cidades_pactuadas[["municipio", "pactuado", "realizado", "pct_execucao", "custo_excedente"]].sort_values("pct_execucao", ascending=False).copy()
        df_show["custo_excedente"] = df_show["custo_excedente"].apply(fmt_brl)
        df_show.columns = ["Municipio", "Pactuado", "Realizado", "% Execucao", "Custo Excedente (R$)"]
        st.dataframe(df_show, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# 6. FATURAMENTO SUS DETALHADO
# ══════════════════════════════════════════════════════════════════════════════

elif view == "Custos Detalhados (SUS)":
    st.title("Detalhamento dos Custos (SUS) - Campina Grande 2025")
    st.caption("Custo SUS Estimado + Bonificacao CLIPSI (R$ 800 por procedimento)")

    excluir_cg_fin = st.sidebar.checkbox("Excluir Campina Grande", value=True)
    top_n = st.sidebar.slider("Top N municipios", 10, 50, 20)

    isea_val_total = isea_pv[MESES].sum().sum()
    clipsi_val_total = clipsi_pv[MESES].sum().sum()
    clipsi_qty_total = clipsi_pq[MESES].sum().sum()
    clipsi_bonus_total = clipsi_qty_total * BONUS_CLIPSI
    receita_total = isea_val_total + clipsi_val_total + clipsi_bonus_total

    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"**Custo Total (SUS + Bonif.)**<br><h2 style='color: #dc3545; margin-top: 0;'>{fmt_brl(receita_total)}</h2>", unsafe_allow_html=True)
    c2.markdown(f"**ISEA (Custo SUS)**<br><h2 style='color: #dc3545; margin-top: 0;'>{fmt_brl(isea_val_total)}</h2>", unsafe_allow_html=True)
    c3.markdown(f"**CLIPSI (Custo SUS)**<br><h2 style='color: #dc3545; margin-top: 0;'>{fmt_brl(clipsi_val_total)}</h2>", unsafe_allow_html=True)
    c4.markdown(f"**CLIPSI (Custo Bonificacao)**<br><h2 style='color: #dc3545; margin-top: 0;'>{fmt_brl(clipsi_bonus_total)}</h2>", unsafe_allow_html=True)

    st.divider()

    # Composicao dos custos
    st.subheader("Composicao dos Custos")
    df_comp_rec = pd.DataFrame({
        "Fonte": ["ISEA (SUS)", "CLIPSI (SUS)", "CLIPSI (Bonificacao R$800)"],
        "Valor": [isea_val_total, clipsi_val_total, clipsi_bonus_total],
    })
    fig = px.pie(df_comp_rec, values="Valor", names="Fonte",
                 title="Composicao dos Custos Gerais",
                 color_discrete_sequence=["#1976D2", "#FF9800", "#FFC107"],
                 hole=0.4)
    fig.update_traces(textinfo="percent+value", texttemplate="%{percent}<br>R$ %{value:,.0f}")
    st.plotly_chart(fig, use_container_width=True)

    # Custo mensal detalhado
    st.subheader("Custo Mensal Detalhado")
    isea_vm = isea_pv[MESES].sum()
    clipsi_vm = clipsi_pv[MESES].sum()
    clipsi_qm = clipsi_pq[MESES].sum()
    clipsi_bm = clipsi_qm * BONUS_CLIPSI

    df_fin = pd.DataFrame({
        "Mes": MESES,
        "ISEA_SUS": isea_vm.values,
        "CLIPSI_SUS": clipsi_vm.values,
        "CLIPSI_Bonif": clipsi_bm.values,
    })
    df_fin["Total"] = df_fin["ISEA_SUS"] + df_fin["CLIPSI_SUS"] + df_fin["CLIPSI_Bonif"]

    fig2 = go.Figure()
    fig2.add_trace(go.Bar(x=df_fin["Mes"], y=df_fin["ISEA_SUS"], name="ISEA (SUS)", marker_color="#1976D2"))
    fig2.add_trace(go.Bar(x=df_fin["Mes"], y=df_fin["CLIPSI_SUS"], name="CLIPSI (SUS)", marker_color="#FF9800"))
    fig2.add_trace(go.Bar(x=df_fin["Mes"], y=df_fin["CLIPSI_Bonif"], name="CLIPSI (Bonif.)", marker_color="#FFC107"))
    fig2.add_trace(go.Scatter(x=df_fin["Mes"], y=df_fin["Total"], name="Total",
                              mode="lines+markers", line=dict(color="#E91E63", width=3)))
    fig2.update_layout(title="Custo Mensal por Fonte", barmode="stack", height=450)
    st.plotly_chart(fig2, use_container_width=True)

    # Ticket medio comparativo
    st.subheader("Ticket Medio por Procedimento")
    col_a, col_b = st.columns(2)

    with col_a:
        merged = isea_pq[["codigo", "descricao", "total"]].merge(
            isea_pv[["codigo", "total"]].rename(columns={"total": "valor"}), on="codigo")
        merged["ticket"] = merged["valor"] / merged["total"].replace(0, 1)
        merged = merged.sort_values("ticket", ascending=True)
        fig3 = px.bar(merged, x="ticket", y="descricao", orientation="h",
                      title="ISEA - Ticket Medio por Procedimento", height=500,
                      color="ticket", color_continuous_scale="Blues")
        fig3.update_layout(yaxis_title="", xaxis_title="R$ por Procedimento")
        st.plotly_chart(fig3, use_container_width=True)

    with col_b:
        merged = clipsi_pq[["codigo", "descricao", "total"]].merge(
            clipsi_pv[["codigo", "total"]].rename(columns={"total": "valor"}), on="codigo")
        merged["ticket_sus"] = merged["valor"] / merged["total"].replace(0, 1)
        merged["ticket_total"] = merged["ticket_sus"] + BONUS_CLIPSI
        merged = merged.sort_values("ticket_total", ascending=True)

        fig4 = go.Figure()
        fig4.add_trace(go.Bar(y=merged["descricao"], x=merged["ticket_sus"],
                              name="SUS", orientation="h", marker_color="#FF9800"))
        fig4.add_trace(go.Bar(y=merged["descricao"], x=[BONUS_CLIPSI]*len(merged),
                              name="Bonificacao (R$800)", orientation="h", marker_color="#FFC107"))
        fig4.update_layout(title="CLIPSI - Ticket Medio (SUS + Bonificacao)", barmode="stack",
                           height=500, yaxis_title="", xaxis_title="R$ por Procedimento")
        st.plotly_chart(fig4, use_container_width=True)

    isea_mun_sus = isea_mv.groupby("municipio")["total"].sum().reset_index(name="isea_sus")
    clipsi_mun_sus = clipsi_mv.groupby("municipio")["total"].sum().reset_index(name="clipsi_sus")
    clipsi_mun_qty = clipsi_mq.groupby("municipio")["total"].sum().reset_index(name="clipsi_qty")
    
    fin_mun = isea_mun_sus.merge(clipsi_mun_sus, on="municipio", how="outer").fillna(0)
    fin_mun = fin_mun.merge(clipsi_mun_qty, on="municipio", how="outer").fillna(0)
    fin_mun["clipsi_bonus"] = fin_mun["clipsi_qty"] * BONUS_CLIPSI
    fin_mun["custo_total"] = fin_mun["isea_sus"] + fin_mun["clipsi_sus"] + fin_mun["clipsi_bonus"]

    if excluir_cg_fin:
        fin_mun = fin_mun[fin_mun["municipio"] != "CAMPINA GRANDE"]

    fin_mun = fin_mun.sort_values("custo_total", ascending=False).head(top_n)

    fig5 = go.Figure()
    fig5.add_trace(go.Bar(x=fin_mun["municipio"], y=fin_mun["isea_sus"], name="ISEA (SUS)", marker_color="#1976D2"))
    fig5.add_trace(go.Bar(x=fin_mun["municipio"], y=fin_mun["clipsi_sus"], name="CLIPSI (SUS)", marker_color="#FF9800"))
    fig5.add_trace(go.Bar(x=fin_mun["municipio"], y=fin_mun["clipsi_bonus"], name="CLIPSI (Bonif.)", marker_color="#FFC107"))
    fig5.update_layout(
        title="Custo por Municipio (SUS + Bonificacao)", barmode="stack",
        height=500, xaxis_tickangle=-45, xaxis_title="", yaxis_title="R$",
    )
    st.plotly_chart(fig5, use_container_width=True)

    # Tabela financeira
    with st.expander("Tabela Financeira Completa"):
        fin_show = fin_mun[["municipio", "isea_sus", "clipsi_sus", "clipsi_bonus", "custo_total"]].copy()
        fin_show.columns = ["Municipio", "ISEA (SUS)", "CLIPSI (SUS)", "CLIPSI (Bonif.)", "Custo Total"]
        st.dataframe(fin_show, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# 7. CUSTOS REAIS (SIGTAP) - Dados do web scraping
# ══════════════════════════════════════════════════════════════════════════════

elif view == "Custos Reais (SIGTAP)":
    st.title("Custos Reais - Tabela SIGTAP")
    st.caption("Custos extraidos diretamente do SIGTAP/DataSUS com detalhamento por procedimento")

    DB_PATH = "saude_real.db"
    if not os.path.exists(DB_PATH):
        st.error("Banco de dados saude_real.db nao encontrado. Execute o scraper primeiro.")
        st.stop()

    conn = sqlite3.connect(DB_PATH)

    # Load data
    df_aih = pd.read_sql_query("""
        SELECT r.id_aih, r.prontuario, r.cns_paciente, r.data_ent, r.data_sai,
               r.cid_principal, r.competencia, r.data_atendimento,
               p.nome as paciente, p.cidade, p.estado
        FROM aih_records r
        LEFT JOIN pacientes p ON r.cns_paciente = p.cns
    """, conn)

    df_procs = pd.read_sql_query("""
        SELECT ap.id_aih, ap.proc_cod, ap.qtd, ap.custo_unitario, ap.custo_total,
               COALESCE(s.nome, '') as proc_nome
        FROM aih_procedimentos ap
        LEFT JOIN aih_records r ON ap.id_aih = r.id_aih
        LEFT JOIN sigtap_metadata s ON ap.proc_cod = s.proc_cod AND r.competencia = s.competencia
    """, conn)

    df_sigtap = pd.read_sql_query("SELECT * FROM sigtap_metadata", conn)
    conn.close()

    if df_aih.empty:
        st.warning("Nenhum dado encontrado no banco. Execute o scraper primeiro.")
        st.stop()

    # Compute total cost per AIH
    aih_costs = df_procs.groupby("id_aih").agg(
        custo_aih=("custo_total", "sum"),
        num_procs=("proc_cod", "count")
    ).reset_index()
    df_aih = df_aih.merge(aih_costs, on="id_aih", how="left").fillna({"custo_aih": 0, "num_procs": 0})

    # Data quality
    total_aihs = len(df_aih)
    total_procs = len(df_procs)
    procs_sem_custo = (df_procs["custo_unitario"] == 0).sum() if "custo_unitario" in df_procs.columns else 0
    custo_total_geral = df_procs["custo_total"].sum() if "custo_total" in df_procs.columns else 0

    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"**Custo Total Real (SIGTAP)**<br><h2 style='color: #1976D2; margin-top: 0;'>{fmt_brl(custo_total_geral)}</h2>", unsafe_allow_html=True)
    c2.markdown(f"**Total AIHs**<br><h2 style='margin-top: 0;'>{fmt_int(total_aihs)}</h2>", unsafe_allow_html=True)
    c3.markdown(f"**Total Procedimentos**<br><h2 style='margin-top: 0;'>{fmt_int(total_procs)}</h2>", unsafe_allow_html=True)
    c4.markdown(f"**Custo Medio/AIH**<br><h2 style='margin-top: 0;'>{fmt_brl(custo_total_geral / total_aihs if total_aihs else 0)}</h2>", unsafe_allow_html=True)

    if procs_sem_custo > 0:
        st.info(f"{procs_sem_custo} procedimentos sem custo no SIGTAP (valor R$ 0,00 na tabela ou dados pendentes)")

    st.divider()

    # Custo por competencia (mes de faturamento)
    st.subheader("Custo por Competencia (Mes de Faturamento)")
    custo_comp = df_aih.groupby("competencia").agg(
        aihs=("id_aih", "count"),
        custo=("custo_aih", "sum")
    ).reset_index().sort_values("competencia")

    fig_comp = go.Figure()
    fig_comp.add_trace(go.Bar(x=custo_comp["competencia"], y=custo_comp["custo"],
                              name="Custo Real", marker_color="#1976D2",
                              text=custo_comp["custo"].apply(fmt_valor_grafico),
                              textposition="outside"))
    fig_comp.add_trace(go.Scatter(x=custo_comp["competencia"], y=custo_comp["aihs"],
                                  name="Qtd AIHs", yaxis="y2",
                                  mode="lines+markers", line=dict(color="#FF9800", width=3)))
    fig_comp.update_layout(
        title="Custo Real vs Quantidade de AIHs por Competencia",
        yaxis=dict(title="Custo (R$)"),
        yaxis2=dict(title="Qtd AIHs", overlaying="y", side="right"),
        height=450
    )
    st.plotly_chart(fig_comp, use_container_width=True)

    # Custo por cidade
    st.subheader("Custo por Cidade")
    top_n_cid = st.sidebar.slider("Top N cidades (Custos Reais)", 10, 50, 20, key="top_n_real")

    custo_cidade = df_aih.groupby("cidade").agg(
        aihs=("id_aih", "count"),
        custo=("custo_aih", "sum")
    ).reset_index().sort_values("custo", ascending=False)

    custo_cidade_top = custo_cidade.head(top_n_cid)
    fig_cid = px.bar(custo_cidade_top, x="cidade", y="custo",
                     title=f"Top {top_n_cid} Cidades - Custo Real SIGTAP",
                     color="custo", color_continuous_scale="Blues", height=500,
                     text=custo_cidade_top["custo"].apply(fmt_valor_grafico))
    fig_cid.update_layout(xaxis_tickangle=-45, xaxis_title="", yaxis_title="Custo Real (R$)")
    fig_cid.update_traces(textposition="outside")
    st.plotly_chart(fig_cid, use_container_width=True)

    # Top procedimentos por custo total
    st.subheader("Procedimentos com Maior Custo")
    proc_custo = df_procs.groupby(["proc_cod", "proc_nome"]).agg(
        qtd_total=("qtd", "sum"),
        custo_total=("custo_total", "sum"),
        ocorrencias=("id_aih", "count")
    ).reset_index().sort_values("custo_total", ascending=False)

    proc_custo["custo_medio"] = proc_custo["custo_total"] / proc_custo["qtd_total"].replace(0, 1)
    proc_custo["label"] = proc_custo["proc_cod"] + " - " + proc_custo["proc_nome"]

    col_a, col_b = st.columns(2)
    with col_a:
        top_procs = proc_custo.head(15)
        fig_procs = px.bar(top_procs, x="custo_total", y="label", orientation="h",
                          title="Top 15 Procedimentos por Custo Total",
                          color="custo_total", color_continuous_scale="Viridis", height=500)
        fig_procs.update_layout(yaxis_title="", xaxis_title="Custo Total (R$)")
        st.plotly_chart(fig_procs, use_container_width=True)

    with col_b:
        top_freq = proc_custo.sort_values("ocorrencias", ascending=False).head(15)
        fig_freq = px.bar(top_freq, x="ocorrencias", y="label", orientation="h",
                         title="Top 15 Procedimentos por Frequencia",
                         color="custo_medio", color_continuous_scale="Oranges", height=500)
        fig_freq.update_layout(yaxis_title="", xaxis_title="Ocorrencias")
        st.plotly_chart(fig_freq, use_container_width=True)

    # Comparativo: Custo Estimado (Excel) vs Custo Real (SIGTAP)
    st.divider()
    st.subheader("Comparativo: Custo Estimado vs Custo Real")

    # Custo estimado do Excel (ja calculado acima)
    custo_estimado_total = isea_pv[MESES].sum().sum() + clipsi_pv[MESES].sum().sum()
    custo_real_total = custo_total_geral

    comp_c1, comp_c2, comp_c3 = st.columns(3)
    comp_c1.markdown(f"**Custo Estimado (Excel/SUS)**<br><h2 style='color: #FF9800; margin-top: 0;'>{fmt_brl(custo_estimado_total)}</h2>", unsafe_allow_html=True)
    comp_c2.markdown(f"**Custo Real (SIGTAP Detalhado)**<br><h2 style='color: #1976D2; margin-top: 0;'>{fmt_brl(custo_real_total)}</h2>", unsafe_allow_html=True)
    diff = custo_real_total - custo_estimado_total
    cor_diff = "#dc3545" if diff > 0 else "#28a745"
    comp_c3.markdown(f"**Diferenca**<br><h2 style='color: {cor_diff}; margin-top: 0;'>{fmt_brl(diff)}</h2>", unsafe_allow_html=True)

    st.caption("O custo real inclui TODOS os procedimentos detalhados (exames, diarias, materiais, etc.) "
               "que nao estao contemplados no custo estimado baseado apenas nos procedimentos principais.")

    # Tabela detalhada de AIHs
    with st.expander("Tabela de AIHs Detalhada"):
        df_show = df_aih[["prontuario", "paciente", "cidade", "data_ent", "data_sai",
                          "cid_principal", "competencia", "num_procs", "custo_aih"]].copy()
        df_show["custo_aih"] = df_show["custo_aih"].apply(fmt_brl)
        df_show["num_procs"] = df_show["num_procs"].astype(int)
        df_show.columns = ["Prontuario", "Paciente", "Cidade", "Entrada", "Saida",
                          "CID", "Competencia", "Num Procs", "Custo Total"]
        st.dataframe(df_show.sort_values("Competencia"), use_container_width=True, hide_index=True)

    # Tabela de procedimentos SIGTAP
    with st.expander("Tabela de Custos SIGTAP"):
        sigtap_show = df_sigtap[["proc_cod", "nome", "competencia", "s_amb", "s_hosp", "s_prof", "t_hosp"]].copy()
        sigtap_show.columns = ["Codigo", "Nome", "Competencia", "Serv. Ambulatorial", "Serv. Hospitalar",
                              "Serv. Profissional", "Total Hospitalar"]
        for col in ["Serv. Ambulatorial", "Serv. Hospitalar", "Serv. Profissional", "Total Hospitalar"]:
            sigtap_show[col] = sigtap_show[col].apply(fmt_brl)
        st.dataframe(sigtap_show.sort_values(["Competencia", "Codigo"]),
                    use_container_width=True, hide_index=True)



# ══════════════════════════════════════════════════════════════════════════════
# 8. ISEA - PRODUCAO MENSAL
# ══════════════════════════════════════════════════════════════════════════════

elif view == "ISEA - Gastos Mensal":
    st.title("ISEA - Gastos Mensal (Dados Scrapeados)")
    st.caption("Dados extraidos diretamente do sistema hospitalar ISEA com valores SIGTAP")

    df_resumo, df_procs, df_cidades = load_isea_data()
    if df_resumo is None or df_resumo.empty:
        st.error("Banco de dados nao encontrado ou vazio. Execute o scraper primeiro.")
        st.stop()

    # KPIs gerais
    tot_pac = df_resumo["pacientes"].sum()
    tot_pront = df_resumo["prontuarios"].sum()
    tot_procs = df_resumo["procedimentos"].sum()
    tot_sh = df_resumo["total_sh"].sum()
    tot_sp = df_resumo["total_sp"].sum()
    tot_th = df_resumo["total_th"].sum()

    c1, c2, c3 = st.columns(3)
    c1.markdown(f"**Total Hospitalar (SH + SP)**<br><h2 style='color: #1976D2; margin-top: 0;'>{fmt_brl(tot_th)}</h2>", unsafe_allow_html=True)
    c2.markdown(f"**Servico Hospitalar (SH)**<br><h2 style='margin-top: 0;'>{fmt_brl(tot_sh)}</h2>", unsafe_allow_html=True)
    c3.markdown(f"**Servico Profissional (SP)**<br><h2 style='margin-top: 0;'>{fmt_brl(tot_sp)}</h2>", unsafe_allow_html=True)

    c4, c5, c6, c7 = st.columns(4)
    c4.metric("Pacientes (unicos)", fmt_int(tot_pac))
    c5.metric("Prontuarios", fmt_int(tot_pront))
    c6.metric("Procedimentos", fmt_int(tot_procs))
    c7.metric("Ticket Medio/Paciente", fmt_brl(tot_th / tot_pac if tot_pac else 0))

    st.divider()

    # Grafico evolucao mensal - Custo
    st.subheader("Evolucao Mensal - Custo Total Hospitalar")
    fig_custo = go.Figure()
    fig_custo.add_trace(go.Bar(
        x=df_resumo["competencia"], y=df_resumo["total_sh"],
        name="Servico Hospitalar (SH)", marker_color="#1976D2",
    ))
    fig_custo.add_trace(go.Bar(
        x=df_resumo["competencia"], y=df_resumo["total_sp"],
        name="Servico Profissional (SP)", marker_color="#FF9800",
    ))
    fig_custo.add_trace(go.Scatter(
        x=df_resumo["competencia"], y=df_resumo["total_th"],
        name="Total Hospitalar (TH)", mode="lines+markers+text",
        line=dict(color="#E91E63", width=3),
        text=df_resumo["total_th"].apply(fmt_valor_grafico),
        textposition="top center",
    ))
    fig_custo.update_layout(barmode="stack", height=450, yaxis_title="Valor (R$)")
    st.plotly_chart(fig_custo, use_container_width=True)

    # Grafico evolucao mensal - Quantidade
    st.subheader("Evolucao Mensal - Pacientes e Procedimentos")
    fig_qty = go.Figure()
    fig_qty.add_trace(go.Bar(
        x=df_resumo["competencia"], y=df_resumo["pacientes"],
        name="Pacientes", marker_color="#4CAF50",
        text=df_resumo["pacientes"], textposition="outside",
    ))
    fig_qty.add_trace(go.Scatter(
        x=df_resumo["competencia"], y=df_resumo["procedimentos"],
        name="Procedimentos", yaxis="y2",
        mode="lines+markers", line=dict(color="#9C27B0", width=3),
    ))
    fig_qty.update_layout(
        yaxis=dict(title="Pacientes"),
        yaxis2=dict(title="Procedimentos", overlaying="y", side="right"),
        height=400,
    )
    st.plotly_chart(fig_qty, use_container_width=True)

    # Tabela resumo
    st.subheader("Tabela Resumo Mensal")
    df_tab = df_resumo.copy()
    df_tab["media_proc_pac"] = (df_tab["procedimentos"] / df_tab["pacientes"].replace(0, 1)).round(1)
    df_tab["ticket_medio"] = df_tab["total_th"] / df_tab["pacientes"].replace(0, 1)

    # Totais
    totais = pd.DataFrame([{
        "competencia": "TOTAL",
        "pacientes": tot_pac,
        "prontuarios": tot_pront,
        "procedimentos": tot_procs,
        "total_sh": tot_sh,
        "total_sp": tot_sp,
        "total_th": tot_th,
        "media_proc_pac": tot_procs / tot_pac if tot_pac else 0,
        "ticket_medio": tot_th / tot_pac if tot_pac else 0,
    }])
    df_tab = pd.concat([df_tab, totais], ignore_index=True)

    df_tab["total_sh"] = df_tab["total_sh"].apply(fmt_brl)
    df_tab["total_sp"] = df_tab["total_sp"].apply(fmt_brl)
    df_tab["total_th"] = df_tab["total_th"].apply(fmt_brl)
    df_tab["ticket_medio"] = df_tab["ticket_medio"].apply(fmt_brl)
    df_tab.columns = ["Competencia", "Pacientes", "Prontuarios", "Procedimentos",
                       "Serv. Hospitalar", "Serv. Profissional", "Total Hospitalar",
                       "Media Proc/Pac", "Ticket Medio"]
    st.dataframe(df_tab, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# 9. ISEA - PROCEDIMENTOS
# ══════════════════════════════════════════════════════════════════════════════

elif view == "ISEA - Procedimentos":
    st.title("ISEA - Analise de Procedimentos (SIGTAP)")
    st.caption("Procedimentos realizados no ISEA com valores da tabela SIGTAP")

    df_resumo, df_procs, df_cidades = load_isea_data()
    if df_procs is None or df_procs.empty:
        st.error("Banco de dados nao encontrado ou vazio.")
        st.stop()

    # Filtro de competencia
    competencias = ["Todas"] + sorted(df_procs["competencia"].unique().tolist(),
                                       key=lambda c: c[3:] + c[:2])
    comp_sel = st.selectbox("Competencia", competencias)

    if comp_sel != "Todas":
        df_p = df_procs[df_procs["competencia"] == comp_sel].copy()
    else:
        df_p = df_procs.groupby(["proc_cod", "proc_nome", "complexidade"]).agg(
            s_hosp=("s_hosp", "first"),
            s_prof=("s_prof", "first"),
            t_hosp=("t_hosp", "first"),
            qtd_total=("qtd_total", "sum"),
            val_sh=("val_sh", "sum"),
            val_sp=("val_sp", "sum"),
            val_th=("val_th", "sum"),
            num_pacientes=("num_pacientes", "sum"),
        ).reset_index()

    tot_th = df_p["val_th"].sum()
    tot_qty = df_p["qtd_total"].sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"**Total Hospitalar**<br><h2 style='color: #1976D2; margin-top: 0;'>{fmt_brl(tot_th)}</h2>", unsafe_allow_html=True)
    c2.metric("Procedimentos Realizados", fmt_int(tot_qty))
    c3.metric("Tipos Distintos", fmt_int(len(df_p)))
    c4.metric("Custo Medio/Proc", fmt_brl(tot_th / tot_qty if tot_qty else 0))

    st.divider()

    # Top 20 por custo total
    st.subheader("Top 20 Procedimentos por Custo Total")
    top20 = df_p.nlargest(20, "val_th").copy()
    top20["label"] = top20["proc_cod"] + " - " + top20["proc_nome"].str[:40]

    fig = px.bar(top20, x="val_th", y="label", orientation="h",
                 color="val_th", color_continuous_scale="Blues", height=600,
                 text=top20["val_th"].apply(fmt_valor_grafico))
    fig.update_layout(yaxis_title="", xaxis_title="Custo Total Hospitalar (R$)",
                      yaxis=dict(autorange="reversed"))
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)

    # Procedimentos por quantidade e custo (todos, agrupando <= 4% como "Outros")
    st.subheader("Procedimentos")
    col_a, col_b = st.columns(2)

    with col_a:
        pie_qty = df_p[["proc_cod", "proc_nome", "qtd_total"]].copy()
        pie_qty = pie_qty.sort_values("qtd_total", ascending=False)
        # Top 10 + agrupar o resto como "Outros"
        main_qty = pie_qty.head(10).copy()
        outros_qty = pie_qty.iloc[10:]
        if not outros_qty.empty:
            outros_row = pd.DataFrame([{
                "proc_cod": ", ".join(outros_qty["proc_cod"].tolist()),
                "proc_nome": "Outros",
                "qtd_total": outros_qty["qtd_total"].sum(),
            }])
            main_qty = pd.concat([main_qty, outros_row], ignore_index=True)
        main_qty["label"] = main_qty["proc_nome"].str[:40]
        main_qty["hover"] = main_qty.apply(
            lambda r: f"{r['proc_cod']}<br>{r['proc_nome']}<br>Qtd: {r['qtd_total']:,.0f}", axis=1)
        fig = px.pie(main_qty, values="qtd_total", names="label",
                     title="Por Quantidade", hole=0.4,
                     color_discrete_sequence=px.colors.qualitative.Set3)
        fig.update_traces(textinfo="percent+value",
                          hovertemplate="%{customdata[0]}<extra></extra>",
                          customdata=main_qty[["hover"]].values)
        fig.update_layout(legend=dict(font=dict(size=9), orientation="h", y=-0.3), height=550)
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        pie_val = df_p[["proc_cod", "proc_nome", "val_th"]].copy()
        pie_val = pie_val.sort_values("val_th", ascending=False)
        # Top 10 + agrupar o resto como "Outros"
        main_val = pie_val.head(10).copy()
        outros_val = pie_val.iloc[10:]
        if not outros_val.empty:
            outros_row = pd.DataFrame([{
                "proc_cod": ", ".join(outros_val["proc_cod"].tolist()),
                "proc_nome": "Outros",
                "val_th": outros_val["val_th"].sum(),
            }])
            main_val = pd.concat([main_val, outros_row], ignore_index=True)
        main_val["label"] = main_val["proc_nome"].str[:40]
        main_val["hover"] = main_val.apply(
            lambda r: f"{r['proc_cod']}<br>{r['proc_nome']}<br>R$ {r['val_th']:,.2f}", axis=1)
        fig = px.pie(main_val, values="val_th", names="label",
                     title="Por Custo Total", hole=0.4,
                     color_discrete_sequence=px.colors.qualitative.Set3)
        fig.update_traces(textinfo="percent+value", texttemplate="%{percent}<br>R$ %{value:,.0f}",
                          hovertemplate="%{customdata[0]}<extra></extra>",
                          customdata=main_val[["hover"]].values)
        fig.update_layout(legend=dict(font=dict(size=9), orientation="h", y=-0.3), height=550)
        st.plotly_chart(fig, use_container_width=True)

    # % Execucao da Pactuacao
    st.divider()
    st.subheader("Execucao da Pactuacao por Procedimento")

    # Cruzar com itens de programacao
    pact_itens = load_itens_programacao()
    pact_df = load_pactuacao()

    # Agrupar pactuacao por procedimento (codigo esta nos itens)
    # A pactuacao tem valor_unitario por procedimento
    pact_por_proc = pact_df.groupby("municipio_encaminhador").agg(
        pactuado_total=("pactuado", "sum"),
        valor_pactuado_total=("valor_pactuado", "sum"),
    ).reset_index()

    # Para comparar com ISEA, preciso a pactuacao total (todos municipios)
    total_pactuado_qty = pact_df["pactuado"].sum()
    total_pactuado_val = pact_df["valor_pactuado"].sum()

    # Comparar procedimento a procedimento: realizado vs pactuado
    # Os itens de programacao tem codigo + descricao
    df_exec = df_p[["proc_cod", "proc_nome", "qtd_total", "val_th"]].copy()
    df_exec = df_exec.merge(pact_itens.rename(columns={"codigo": "proc_cod"}), on="proc_cod", how="left")
    df_exec["na_pactuacao"] = df_exec["descricao"].notna()

    # Procedimentos que estao na pactuacao
    df_pact_procs = df_exec[df_exec["na_pactuacao"]].copy()

    if not df_pact_procs.empty:
        # % do total realizado que cada proc representa
        df_pact_procs["pct_qty"] = (df_pact_procs["qtd_total"] / tot_qty * 100).round(1)
        df_pact_procs["pct_val"] = (df_pact_procs["val_th"] / tot_th * 100).round(1)
        df_pact_procs["label"] = df_pact_procs["proc_cod"] + " - " + df_pact_procs["proc_nome"].str[:40]
        df_pact_procs = df_pact_procs.sort_values("qtd_total", ascending=True)

        col_c, col_d = st.columns(2)
        with col_c:
            fig = px.bar(df_pact_procs, x="qtd_total", y="label", orientation="h",
                         title="Quantidade Realizada (Procedimentos Pactuados)",
                         color="qtd_total", color_continuous_scale="Blues",
                         text="qtd_total", height=max(400, len(df_pact_procs) * 30))
            fig.update_layout(yaxis_title="", xaxis_title="Quantidade")
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True)

        with col_d:
            fig = px.bar(df_pact_procs, x="val_th", y="label", orientation="h",
                         title="Custo Realizado (Procedimentos Pactuados)",
                         color="val_th", color_continuous_scale="Oranges",
                         text=df_pact_procs["val_th"].apply(fmt_valor_grafico),
                         height=max(400, len(df_pact_procs) * 30))
            fig.update_layout(yaxis_title="", xaxis_title="Custo Total (R$)")
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True)

        # Resumo
        total_pact_qty = df_pact_procs["qtd_total"].sum()
        total_pact_val = df_pact_procs["val_th"].sum()
        st.markdown(f"""
        **Resumo Pactuacao:**
        - Procedimentos pactuados encontrados: **{len(df_pact_procs)}** de {len(df_p)} tipos
        - Quantidade realizada (pactuados): **{fmt_int(total_pact_qty)}** ({total_pact_qty/tot_qty*100:.1f}% do total)
        - Custo realizado (pactuados): **{fmt_brl(total_pact_val)}** ({total_pact_val/tot_th*100:.1f}% do total)
        """)
    else:
        st.info("Nenhum procedimento da pactuacao encontrado nos dados do ISEA.")

    # Tabela completa
    with st.expander("Tabela Completa de Procedimentos"):
        df_show = df_p[["proc_cod", "proc_nome", "qtd_total", "num_pacientes",
                        "val_sh", "val_sp", "val_th"]].copy()
        df_show = df_show.sort_values("val_th", ascending=False)
        df_show["val_sh"] = df_show["val_sh"].apply(fmt_brl)
        df_show["val_sp"] = df_show["val_sp"].apply(fmt_brl)
        df_show["val_th"] = df_show["val_th"].apply(fmt_brl)
        df_show.columns = ["Codigo", "Nome", "Qtd Total", "Pacientes",
                           "Serv. Hospitalar", "Serv. Profissional", "Total Hospitalar"]
        st.dataframe(df_show, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# 10. ISEA - PACIENTES E CIDADES
# ══════════════════════════════════════════════════════════════════════════════

elif view == "ISEA - Pacientes e Cidades":
    st.title("ISEA - Pacientes por Cidade")
    st.caption("Distribuicao de pacientes e custos por cidade de origem")

    df_resumo, df_procs, df_cidades = load_isea_data()
    if df_cidades is None or df_cidades.empty:
        st.error("Banco de dados nao encontrado ou vazio.")
        st.stop()

    # Filtros
    col_f1, col_f2 = st.columns([3, 1])
    with col_f1:
        competencias = ["Todas"] + sorted(df_cidades["competencia"].unique().tolist(),
                                           key=lambda c: c[3:] + c[:2])
        comp_sel = st.selectbox("Competencia", competencias, key="cidade_comp")
    with col_f2:
        excluir_cg = st.checkbox("Excluir Campina Grande", key="excluir_cg_cidades")

    df_filt = df_cidades.copy()
    if excluir_cg:
        df_filt = df_filt[~df_filt["cidade"].str.upper().str.contains("CAMPINA GRANDE", na=False)]

    if comp_sel != "Todas":
        df_c = df_filt[df_filt["competencia"] == comp_sel].copy()
    else:
        df_c = df_filt.groupby("cidade").agg(
            pacientes=("pacientes", "sum"),
            registros=("registros", "sum"),
            procedimentos=("procedimentos", "sum"),
            total_sh=("total_sh", "sum"),
            total_sp=("total_sp", "sum"),
            total_th=("total_th", "sum"),
        ).reset_index()

    tot_pac = df_c["pacientes"].sum()
    tot_th = df_c["total_th"].sum()
    tot_cidades = len(df_c[df_c["pacientes"] > 0])

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"**Custo Total**<br><h2 style='color: #1976D2; margin-top: 0;'>{fmt_brl(tot_th)}</h2>", unsafe_allow_html=True)
    c2.metric("Total Pacientes", fmt_int(tot_pac))
    c3.metric("Cidades Atendidas", fmt_int(tot_cidades))
    c4.metric("Custo Medio/Paciente", fmt_brl(tot_th / tot_pac if tot_pac else 0))

    st.divider()

    # Top 20 cidades por custo
    st.subheader("Top 20 Cidades por Custo Total")
    top20_c = df_c.nlargest(20, "total_th")
    fig = px.bar(top20_c, x="cidade", y="total_th",
                 color="total_th", color_continuous_scale="Blues", height=500,
                 text=top20_c["total_th"].apply(fmt_valor_grafico))
    fig.update_layout(xaxis_tickangle=-45, xaxis_title="", yaxis_title="Custo Total (R$)")
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)

    # Top 20 cidades por pacientes
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Top 15 Cidades por Pacientes")
        top15_pac = df_c.nlargest(15, "pacientes")
        fig = px.bar(top15_pac, x="pacientes", y="cidade", orientation="h",
                     color="pacientes", color_continuous_scale="Greens", height=500,
                     text="pacientes")
        fig.update_layout(yaxis_title="", xaxis_title="Pacientes",
                          yaxis=dict(autorange="reversed"))
        fig.update_traces(textposition="outside")
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        st.subheader("Ticket Medio por Cidade (Top 15)")
        df_ticket = df_c[df_c["pacientes"] >= 5].copy()
        df_ticket["ticket"] = df_ticket["total_th"] / df_ticket["pacientes"]
        top15_ticket = df_ticket.nlargest(15, "ticket")
        fig = px.bar(top15_ticket, x="ticket", y="cidade", orientation="h",
                     color="ticket", color_continuous_scale="Oranges", height=500,
                     text=top15_ticket["ticket"].apply(lambda v: fmt_brl(v)))
        fig.update_layout(yaxis_title="", xaxis_title="Ticket Medio (R$)",
                          yaxis=dict(autorange="reversed"))
        fig.update_traces(textposition="outside")
        st.plotly_chart(fig, use_container_width=True)

    # Heatmap cidade x mes (se "Todas" selecionado)
    if comp_sel == "Todas":
        st.subheader("Mapa de Calor - Pacientes por Cidade x Mes")
        top10_cidades = df_filt.groupby("cidade")["pacientes"].sum().nlargest(10).index.tolist()
        df_heat = df_filt[df_filt["cidade"].isin(top10_cidades)].pivot_table(
            index="cidade", columns="competencia", values="pacientes", aggfunc="sum", fill_value=0
        )
        # Ordenar colunas por data
        cols_sorted = sorted(df_heat.columns, key=lambda c: c[3:] + c[:2])
        df_heat = df_heat[cols_sorted]
        fig = px.imshow(df_heat, aspect="auto", color_continuous_scale="YlOrRd",
                        title="Top 10 Cidades - Pacientes por Competencia", height=400)
        fig.update_layout(xaxis_title="Competencia", yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

    # Tabela completa
    with st.expander("Tabela Completa por Cidade"):
        df_show = df_c.sort_values("total_th", ascending=False).copy()
        df_show["ticket_medio"] = df_show["total_th"] / df_show["pacientes"].replace(0, 1)
        df_show["total_sh"] = df_show["total_sh"].apply(fmt_brl)
        df_show["total_sp"] = df_show["total_sp"].apply(fmt_brl)
        df_show["total_th"] = df_show["total_th"].apply(fmt_brl)
        df_show["ticket_medio"] = df_show["ticket_medio"].apply(fmt_brl)
        df_show.columns = ["Cidade", "Pacientes", "Registros", "Procedimentos",
                           "Serv. Hospitalar", "Serv. Profissional", "Total Hospitalar", "Ticket Medio"]
        st.dataframe(df_show, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# 11. ISEA - CONSULTA PRONTUARIO
# ══════════════════════════════════════════════════════════════════════════════

elif view == "ISEA - Consulta Prontuario":
    st.title("ISEA - Consulta por Prontuario")
    st.caption("Consulte os gastos detalhados de um prontuario especifico")

    DB_PATH = os.path.join(DATA_DIR, "saude_real.db")
    if not os.path.exists(DB_PATH):
        st.error("Banco de dados nao encontrado. Execute o scraper primeiro.")
        st.stop()

    conn = sqlite3.connect(DB_PATH)

    # Carregar competencias disponiveis
    competencias = pd.read_sql_query(
        "SELECT DISTINCT competencia FROM aih_records ORDER BY SUBSTR(competencia, 4, 4) || SUBSTR(competencia, 1, 2)",
        conn
    )["competencia"].tolist()

    if not competencias:
        st.warning("Nenhuma competencia encontrada no banco.")
        conn.close()
        st.stop()

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        comp_sel = st.selectbox("Competencia", competencias, key="pront_comp")
    with col_f2:
        # Carregar prontuarios com nome do paciente para facilitar a busca
        df_pront = pd.read_sql_query("""
            SELECT DISTINCT r.prontuario, COALESCE(p.nome, 'N/A') as nome
            FROM aih_records r
            LEFT JOIN pacientes p ON r.cns_paciente = p.cns
            WHERE r.competencia = ?
            ORDER BY p.nome, r.prontuario
        """, conn, params=[comp_sel])
        opcoes = [f"{row['prontuario']} - {row['nome']}" for _, row in df_pront.iterrows()]
        sel = st.selectbox("Prontuario", opcoes, key="pront_sel")
        pront_sel = sel.split(" - ")[0] if sel else None

    if not pront_sel:
        st.info("Selecione um prontuario para consultar.")
        conn.close()
        st.stop()

    # Dados do paciente e AIH
    df_aih = pd.read_sql_query("""
        SELECT r.prontuario, r.competencia, r.id_aih, r.data_ent, r.data_sai,
               r.cid_principal, r.motivo_saida, r.medico_solic, r.medico_resp,
               r.cns_paciente, r.observacao,
               p.nome, p.dt_nasc, p.sexo, p.cidade, p.estado, p.nome_mae
        FROM aih_records r
        LEFT JOIN pacientes p ON r.cns_paciente = p.cns
        WHERE r.prontuario = ? AND r.competencia = ?
    """, conn, params=[pront_sel, comp_sel])

    if df_aih.empty:
        st.warning("Nenhum registro encontrado para este prontuario/competencia.")
        conn.close()
        st.stop()

    # Dados do paciente (primeiro registro)
    pac = df_aih.iloc[0]
    st.subheader("Dados do Paciente")
    cp1, cp2, cp3 = st.columns(3)
    cp1.markdown(f"**Nome:** {pac['nome'] or 'N/A'}")
    cp1.markdown(f"**CNS:** {pac['cns_paciente'] or 'N/A'}")
    cp2.markdown(f"**Data Nascimento:** {pac['dt_nasc'] or 'N/A'}")
    cp2.markdown(f"**Sexo:** {pac['sexo'] or 'N/A'}")
    cp3.markdown(f"**Cidade:** {pac['cidade'] or 'N/A'} - {pac['estado'] or ''}")
    cp3.markdown(f"**Mae:** {pac['nome_mae'] or 'N/A'}")

    st.divider()

    # Para cada AIH do prontuario nessa competencia
    for idx, aih in df_aih.iterrows():
        st.subheader(f"AIH: {aih['id_aih']}")

        ca1, ca2, ca3, ca4 = st.columns(4)
        ca1.markdown(f"**Entrada:** {aih['data_ent'] or 'N/A'}")
        ca2.markdown(f"**Saida:** {aih['data_sai'] or 'N/A'}")
        ca3.markdown(f"**CID:** {aih['cid_principal'] or 'N/A'}")
        ca4.markdown(f"**Motivo Saida:** {aih['motivo_saida'] or 'N/A'}")

        if aih['observacao']:
            st.warning(f"Observacao: {aih['observacao']}")

        # Procedimentos desta AIH
        df_proc = pd.read_sql_query("""
            SELECT ap.proc_cod as "Codigo",
                   COALESCE(sm.nome, sm_any.nome, ap.proc_cod) as "Procedimento",
                   ap.qtd as "Qtde",
                   COALESCE(sm.s_hosp, 0) as sh_unit,
                   COALESCE(sm.s_prof, 0) as sp_unit,
                   COALESCE(sm.t_hosp, 0) as th_unit,
                   ap.qtd * COALESCE(sm.s_hosp, 0) as "Serv. Hospitalar",
                   ap.qtd * COALESCE(sm.s_prof, 0) as "Serv. Profissional",
                   ap.qtd * COALESCE(sm.t_hosp, 0) as "Total Hospitalar"
            FROM aih_procedimentos ap
            LEFT JOIN sigtap_metadata sm ON sm.proc_cod = ap.proc_cod AND sm.competencia = ?
            LEFT JOIN (
                SELECT proc_cod, nome FROM sigtap_metadata GROUP BY proc_cod
            ) sm_any ON sm_any.proc_cod = ap.proc_cod
            WHERE ap.id_aih = ?
            ORDER BY "Total Hospitalar" DESC
        """, conn, params=[comp_sel, aih['id_aih']])

        if df_proc.empty:
            st.info("Nenhum procedimento registrado para esta AIH.")
            continue

        total_sh = df_proc["Serv. Hospitalar"].sum()
        total_sp = df_proc["Serv. Profissional"].sum()
        total_th = df_proc["Total Hospitalar"].sum()

        # KPIs da AIH
        ck1, ck2, ck3, ck4 = st.columns(4)
        ck1.metric("Procedimentos", int(df_proc["Qtde"].sum()))
        ck2.markdown(f"**Serv. Hospitalar**<br><span style='font-size:1.3em;'>{fmt_brl(total_sh)}</span>", unsafe_allow_html=True)
        ck3.markdown(f"**Serv. Profissional**<br><span style='font-size:1.3em;'>{fmt_brl(total_sp)}</span>", unsafe_allow_html=True)
        ck4.markdown(f"**Total Hospitalar**<br><span style='font-size:1.3em; color:#1976D2; font-weight:bold;'>{fmt_brl(total_th)}</span>", unsafe_allow_html=True)

        # Tabela de procedimentos
        df_show = df_proc.copy()
        df_show["Valor Unit."] = df_show["th_unit"].apply(fmt_brl)
        df_show["Serv. Hospitalar"] = df_show["Serv. Hospitalar"].apply(fmt_brl)
        df_show["Serv. Profissional"] = df_show["Serv. Profissional"].apply(fmt_brl)
        df_show["Total Hospitalar"] = df_show["Total Hospitalar"].apply(fmt_brl)
        df_show = df_show[["Codigo", "Procedimento", "Qtde", "Valor Unit.", "Serv. Hospitalar", "Serv. Profissional", "Total Hospitalar"]]
        st.dataframe(df_show, use_container_width=True, hide_index=True)

        st.divider()

    # Resumo geral do prontuario
    df_all_procs = pd.read_sql_query("""
        SELECT ap.qtd,
               ap.qtd * COALESCE(sm.s_hosp, 0) as val_sh,
               ap.qtd * COALESCE(sm.s_prof, 0) as val_sp,
               ap.qtd * COALESCE(sm.t_hosp, 0) as val_th
        FROM aih_records r
        JOIN aih_procedimentos ap ON r.id_aih = ap.id_aih
        LEFT JOIN sigtap_metadata sm ON sm.proc_cod = ap.proc_cod AND sm.competencia = r.competencia
        WHERE r.prontuario = ? AND r.competencia = ?
    """, conn, params=[pront_sel, comp_sel])

    if len(df_aih) > 1:
        st.subheader("Resumo Geral do Prontuario")
        rk1, rk2, rk3, rk4, rk5 = st.columns(5)
        rk1.metric("AIHs", len(df_aih))
        rk2.metric("Total Procedimentos", int(df_all_procs["qtd"].sum()))
        rk3.markdown(f"**Total SH**<br><h3 style='margin-top:0;'>{fmt_brl(df_all_procs['val_sh'].sum())}</h3>", unsafe_allow_html=True)
        rk4.markdown(f"**Total SP**<br><h3 style='margin-top:0;'>{fmt_brl(df_all_procs['val_sp'].sum())}</h3>", unsafe_allow_html=True)
        rk5.markdown(f"**Total Geral**<br><h2 style='margin-top:0; color:#1976D2;'>{fmt_brl(df_all_procs['val_th'].sum())}</h2>", unsafe_allow_html=True)

    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# 12. TABELA SIGTAP
# ══════════════════════════════════════════════════════════════════════════════

elif view == "Tabela SIGTAP":
    st.title("Tabela SIGTAP - Valores de Procedimentos SUS")
    st.caption("Valores oficiais da tabela unificada do SUS (DATASUS) por procedimento e competencia")

    DB_PATH = os.path.join(DATA_DIR, "saude_real.db")
    if not os.path.exists(DB_PATH):
        st.error("Banco de dados nao encontrado.")
        st.stop()

    conn_sigtap = sqlite3.connect(DB_PATH)

    df_sigtap = pd.read_sql_query("""
        SELECT proc_cod, competencia, nome, complexidade, financiamento,
               s_hosp, s_prof, t_hosp, s_amb, t_amb,
               idade_min, idade_max, sexo, permanencia_media
        FROM sigtap_metadata
        ORDER BY nome, SUBSTR(competencia, 4, 4) || SUBSTR(competencia, 1, 2)
    """, conn_sigtap)
    conn_sigtap.close()

    if df_sigtap.empty:
        st.warning("Nenhum procedimento SIGTAP encontrado no banco.")
        st.stop()

    # Filtros
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        competencias_sig = sorted(df_sigtap["competencia"].unique().tolist(),
                                  key=lambda c: c[3:] + c[:2])
        comp_sel_sig = st.selectbox("Competencia", ["Todas"] + competencias_sig, key="sigtap_comp")
    with col_f2:
        complexidades = ["Todas"] + sorted(df_sigtap["complexidade"].dropna().unique().tolist())
        complex_sel = st.selectbox("Complexidade", complexidades, key="sigtap_complex")

    # Selecao de procedimento especifico
    procs_unicos = df_sigtap.drop_duplicates("proc_cod")[["proc_cod", "nome"]].sort_values("nome")
    opcoes_proc = ["Todos"] + [f"{row['proc_cod']} - {row['nome']}" for _, row in procs_unicos.iterrows()]
    proc_sel = st.selectbox("Procedimento", opcoes_proc, key="sigtap_proc")

    df_filt = df_sigtap.copy()
    if comp_sel_sig != "Todas":
        df_filt = df_filt[df_filt["competencia"] == comp_sel_sig]
    if complex_sel != "Todas":
        df_filt = df_filt[df_filt["complexidade"] == complex_sel]
    if proc_sel != "Todos":
        cod_sel = proc_sel.split(" - ")[0]
        df_filt = df_filt[df_filt["proc_cod"] == cod_sel]

    # KPIs
    n_procs = df_filt["proc_cod"].nunique()
    n_comps = df_filt["competencia"].nunique()
    media_th = df_filt["t_hosp"].mean() if not df_filt.empty else 0
    max_th = df_filt["t_hosp"].max() if not df_filt.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Procedimentos", fmt_int(n_procs))
    c2.metric("Competencias", fmt_int(n_comps))
    c3.markdown(f"**Valor Medio (TH)**<br><h3 style='margin-top:0;'>{fmt_brl(media_th)}</h3>", unsafe_allow_html=True)
    c4.markdown(f"**Maior Valor (TH)**<br><h3 style='margin-top:0; color:#dc3545;'>{fmt_brl(max_th)}</h3>", unsafe_allow_html=True)

    st.divider()

    # Grafico top 15 procedimentos por valor
    if comp_sel_sig != "Todas":
        df_top = df_filt.nlargest(15, "t_hosp")
    else:
        df_top = df_filt.groupby(["proc_cod", "nome"]).agg(t_hosp=("t_hosp", "mean")).reset_index().nlargest(15, "t_hosp")

    titulo_grafico = f"Top 15 Procedimentos por Valor Total Hospitalar ({comp_sel_sig})" if comp_sel_sig != "Todas" else "Top 15 Procedimentos por Valor Medio Total Hospitalar"
    fig = px.bar(df_top, x="t_hosp", y="nome", orientation="h",
                 color="t_hosp", color_continuous_scale="Blues", height=500,
                 text=df_top["t_hosp"].apply(fmt_brl),
                 title=titulo_grafico)
    fig.update_layout(yaxis_title="", xaxis_title="Valor (R$)", yaxis=dict(autorange="reversed"))
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)

    # Composicao SH vs SP dos top procedimentos
    if comp_sel_sig != "Todas":
        df_comp_sig = df_filt.nlargest(10, "t_hosp")[["nome", "s_hosp", "s_prof"]].copy()
    else:
        df_comp_sig = df_filt.groupby("nome").agg(s_hosp=("s_hosp", "mean"), s_prof=("s_prof", "mean")).reset_index()
        df_comp_sig["t_hosp"] = df_comp_sig["s_hosp"] + df_comp_sig["s_prof"]
        df_comp_sig = df_comp_sig.nlargest(10, "t_hosp")[["nome", "s_hosp", "s_prof"]]

    fig2 = go.Figure()
    fig2.add_trace(go.Bar(x=df_comp_sig["nome"], y=df_comp_sig["s_hosp"], name="Serv. Hospitalar (SH)", marker_color="#1976D2"))
    fig2.add_trace(go.Bar(x=df_comp_sig["nome"], y=df_comp_sig["s_prof"], name="Serv. Profissional (SP)", marker_color="#FF9800"))
    fig2.update_layout(barmode="stack", title="Composicao SH vs SP - Top 10 Procedimentos",
                       xaxis_tickangle=-45, yaxis_title="Valor (R$)", height=450)
    st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    # Evolucao de valor ao longo das competencias (se "Todas")
    if comp_sel_sig == "Todas" and n_procs <= 20:
        st.subheader("Evolucao de Valores por Competencia")
        fig3 = go.Figure()
        for proc in df_filt["proc_cod"].unique():
            df_p = df_filt[df_filt["proc_cod"] == proc].sort_values("competencia", key=lambda s: s.str[3:] + s.str[:2])
            nome_proc = df_p["nome"].iloc[0] if not df_p.empty else proc
            fig3.add_trace(go.Scatter(x=df_p["competencia"], y=df_p["t_hosp"],
                                      mode="lines+markers", name=nome_proc[:40]))
        fig3.update_layout(height=450, yaxis_title="Total Hospitalar (R$)", xaxis_title="Competencia")
        st.plotly_chart(fig3, use_container_width=True)
        st.divider()

    # Tabela completa
    st.subheader("Tabela de Valores")
    df_show = df_filt.copy()
    df_show["s_hosp"] = df_show["s_hosp"].apply(fmt_brl)
    df_show["s_prof"] = df_show["s_prof"].apply(fmt_brl)
    df_show["t_hosp"] = df_show["t_hosp"].apply(fmt_brl)
    df_show["s_amb"] = df_show["s_amb"].apply(fmt_brl)
    df_show["t_amb"] = df_show["t_amb"].apply(fmt_brl)
    df_show.columns = ["Codigo", "Competencia", "Procedimento", "Complexidade", "Financiamento",
                        "Serv. Hosp.", "Serv. Prof.", "Total Hosp.", "Serv. Amb.", "Total Amb.",
                        "Idade Min", "Idade Max", "Sexo", "Perm. Media (dias)"]
    st.dataframe(df_show, use_container_width=True, hide_index=True)
