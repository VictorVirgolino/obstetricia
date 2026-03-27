"""
Página de Abrangência e Pactuação para o dashboard Streamlit.
Mostra rede de referência, pactuação vs realizado, e itens de programação.
"""

import os
import sqlite3
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DATA_DIR, "saude_real.db")


def fmt_brl(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_int(valor):
    return f"{int(valor):,}".replace(",", ".")


def _get_conn():
    return sqlite3.connect(DB_PATH)


@st.cache_data(ttl=300)
def load_abrangencia_resumo():
    """Carrega resumo da abrangência para Campina Grande."""
    conn = _get_conn()
    df = pd.read_sql_query("""
        SELECT tipo, item_cod, item_nome, municipio_executor,
               quantidade, valor_unitario, valor_total
        FROM abrangencia
        ORDER BY tipo, item_nome
    """, conn)
    conn.close()
    return df


@st.cache_data(ttl=300)
def load_referencia():
    """Carrega dados de referência (encaminhador -> executor)."""
    conn = _get_conn()
    df = pd.read_sql_query("""
        SELECT tipo, financiamento, municipio_encaminhador, item_cod, item_nome,
               municipio_executor, quantidade, valor_unitario, valor_total
        FROM referencia
        ORDER BY municipio_encaminhador, item_nome
    """, conn)
    conn.close()
    return df


@st.cache_data(ttl=300)
def load_pactuado_vs_realizado():
    """Cruza pactuação (abrangência) com produção real (aih_procedimentos)."""
    conn = _get_conn()
    df = pd.read_sql_query("""
        SELECT
            ab.tipo,
            ab.item_cod,
            ab.item_nome,
            ab.municipio_executor,
            ab.quantidade as qtd_pactuada,
            ab.valor_total as valor_pactuado,
            COALESCE(real.qtd_realizada, 0) as qtd_realizada,
            COALESCE(real.valor_realizado, 0) as valor_realizado
        FROM abrangencia ab
        LEFT JOIN (
            SELECT ip.item_cod,
                   SUM(ap.qtd) as qtd_realizada,
                   SUM(ap.custo_total) as valor_realizado
            FROM item_procedimento ip
            INNER JOIN aih_procedimentos ap ON ip.proc_cod = ap.proc_cod
            GROUP BY ip.item_cod
        ) real ON ab.item_cod = real.item_cod
        WHERE UPPER(ab.municipio_executor) = 'CAMPINA GRANDE'
        ORDER BY COALESCE(real.qtd_realizada, 0) DESC
    """, conn)
    conn.close()
    return df


@st.cache_data(ttl=300)
def load_referencia_cg():
    """Referências que têm Campina Grande como executor, agrupadas por encaminhador."""
    conn = _get_conn()
    df = pd.read_sql_query("""
        SELECT
            ref.tipo,
            ref.municipio_encaminhador,
            COUNT(DISTINCT ref.item_cod) as itens_pactuados,
            SUM(ref.quantidade) as qtd_pactuada,
            SUM(ref.valor_total) as valor_pactuado,
            COALESCE(real.qtd_realizada, 0) as qtd_realizada,
            COALESCE(real.valor_realizado, 0) as valor_realizado
        FROM referencia ref
        LEFT JOIN (
            SELECT
                COALESCE(p.cidade, 'Desconhecida') as cidade,
                SUM(ap.qtd) as qtd_realizada,
                SUM(ap.custo_total) as valor_realizado
            FROM aih_records r
            LEFT JOIN pacientes p ON r.cns_paciente = p.cns
            LEFT JOIN aih_procedimentos ap ON r.id_aih = ap.id_aih
            GROUP BY p.cidade
        ) real ON UPPER(ref.municipio_encaminhador) = UPPER(real.cidade)
        WHERE UPPER(ref.municipio_executor) = 'CAMPINA GRANDE'
        GROUP BY ref.tipo, ref.municipio_encaminhador
        ORDER BY valor_pactuado DESC
    """, conn)
    conn.close()
    return df


@st.cache_data(ttl=300)
def load_itens_procedimentos():
    """Carrega mapeamento item -> procedimentos."""
    conn = _get_conn()
    df = pd.read_sql_query("""
        SELECT tipo, item_cod, item_nome, proc_cod, proc_nome
        FROM item_procedimento
        ORDER BY tipo, item_cod, proc_cod
    """, conn)
    conn.close()
    return df


def render():
    """Renderiza a página de Abrangência no dashboard."""
    st.title("Abrangência e Pactuação")
    st.markdown("Rede de referência SUS — pactuação vs produção real")

    # Sub-navegação
    sub = st.radio(
        "Visualização",
        ["Pactuado vs Realizado", "Rede de Referência", "Itens de Programação", "Abrangência Geral"],
        horizontal=True,
        label_visibility="collapsed",
    )

    if sub == "Pactuado vs Realizado":
        _render_pactuado_vs_realizado()
    elif sub == "Rede de Referência":
        _render_rede_referencia()
    elif sub == "Itens de Programação":
        _render_itens_programacao()
    elif sub == "Abrangência Geral":
        _render_abrangencia_geral()


def _render_pactuado_vs_realizado():
    st.subheader("Pactuado vs Realizado — Campina Grande")

    df = load_pactuado_vs_realizado()
    if df.empty:
        st.warning("Sem dados de pactuação. Execute: python import_abrangencia.py")
        return

    tipo_filter = st.sidebar.selectbox("Tipo", ["Todos", "AMBULATORIAL", "HOSPITALAR"], key="pvr_tipo")
    if tipo_filter != "Todos":
        df = df[df["tipo"].str.upper() == tipo_filter]

    mostrar_apenas_divergentes = st.sidebar.checkbox("Apenas com divergência", value=False, key="pvr_div")

    df["percentual"] = df.apply(
        lambda r: (r["qtd_realizada"] / r["qtd_pactuada"] * 100) if r["qtd_pactuada"] > 0 else 0, axis=1
    )
    df["status"] = df["percentual"].apply(
        lambda p: "Acima" if p > 110 else ("Abaixo" if p < 90 else "Adequado")
    )

    if mostrar_apenas_divergentes:
        df = df[df["status"] != "Adequado"]

    # Métricas
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Itens pactuados", fmt_int(len(df)))
    col2.metric("Acima (>110%)", fmt_int(len(df[df["status"] == "Acima"])))
    col3.metric("Adequado (90-110%)", fmt_int(len(df[df["status"] == "Adequado"])))
    col4.metric("Abaixo (<90%)", fmt_int(len(df[df["status"] == "Abaixo"])))

    # Gráfico de barras comparativo (top 20)
    df_top = df.head(20).copy()
    if not df_top.empty:
        df_top["label"] = df_top["item_cod"]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            name="Pactuado", x=df_top["label"], y=df_top["qtd_pactuada"],
            marker_color="#636EFA",
        ))
        fig.add_trace(go.Bar(
            name="Realizado", x=df_top["label"], y=df_top["qtd_realizada"],
            marker_color="#EF553B",
        ))
        fig.update_layout(
            barmode="group", title="Top 20 Itens — Pactuado vs Realizado",
            xaxis_tickangle=-45, height=500,
        )
        st.plotly_chart(fig, use_container_width=True)

    # Tabela
    st.dataframe(
        df[["tipo", "item_cod", "item_nome", "qtd_pactuada", "qtd_realizada",
            "percentual", "status"]].rename(columns={
            "tipo": "Tipo", "item_cod": "Código", "item_nome": "Item",
            "qtd_pactuada": "Pactuado", "qtd_realizada": "Realizado",
            "percentual": "% Execução", "status": "Status",
        }).style.format({"% Execução": "{:.1f}%"}),
        use_container_width=True, hide_index=True,
    )


def _render_rede_referencia():
    st.subheader("Rede de Referência — Encaminhamentos para Campina Grande")

    df = load_referencia_cg()
    if df.empty:
        st.warning("Sem dados de referência.")
        return

    tipo_filter = st.sidebar.selectbox("Tipo", ["Todos", "AMBULATORIAL", "HOSPITALAR"], key="ref_tipo")
    if tipo_filter != "Todos":
        df = df[df["tipo"].str.upper() == tipo_filter]

    excluir_cg = st.sidebar.checkbox("Excluir Campina Grande", value=False, key="ref_excl_cg")
    if excluir_cg:
        df = df[df["municipio_encaminhador"].str.upper() != "CAMPINA GRANDE"]

    top_n = st.sidebar.slider("Top N municípios", 10, 50, 20, key="ref_topn")

    # Métricas
    col1, col2, col3 = st.columns(3)
    col1.metric("Municípios encaminhadores", fmt_int(df["municipio_encaminhador"].nunique()))
    col2.metric("Qtd total pactuada", fmt_int(int(df["qtd_pactuada"].sum())))
    col3.metric("Valor total pactuado", fmt_brl(df["valor_pactuado"].sum()))

    # Top municípios por valor pactuado
    df_top = df.groupby("municipio_encaminhador").agg({
        "qtd_pactuada": "sum",
        "valor_pactuado": "sum",
        "qtd_realizada": "sum",
        "valor_realizado": "sum",
        "itens_pactuados": "sum",
    }).sort_values("valor_pactuado", ascending=False).head(top_n).reset_index()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Valor Pactuado", x=df_top["municipio_encaminhador"], y=df_top["valor_pactuado"],
        marker_color="#636EFA",
    ))
    fig.add_trace(go.Bar(
        name="Valor Realizado", x=df_top["municipio_encaminhador"], y=df_top["valor_realizado"],
        marker_color="#EF553B",
    ))
    fig.update_layout(
        barmode="group", title=f"Top {top_n} Municípios — Valor Pactuado vs Realizado",
        xaxis_tickangle=-45, height=500,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Tabela
    st.dataframe(
        df_top.rename(columns={
            "municipio_encaminhador": "Município", "itens_pactuados": "Itens",
            "qtd_pactuada": "Qtd Pactuada", "valor_pactuado": "Valor Pactuado",
            "qtd_realizada": "Qtd Realizada", "valor_realizado": "Valor Realizado",
        }),
        use_container_width=True, hide_index=True,
    )


def _render_itens_programacao():
    st.subheader("Itens de Programação — Mapeamento para Procedimentos SIGTAP")

    df = load_itens_procedimentos()
    if df.empty:
        st.warning("Sem dados de itens de programação.")
        return

    tipo_filter = st.sidebar.selectbox("Tipo", ["Todos", "AMBULATORIAL", "HOSPITALAR"], key="ip_tipo")
    if tipo_filter != "Todos":
        df = df[df["tipo"].str.upper() == tipo_filter]

    # Resumo
    col1, col2, col3 = st.columns(3)
    col1.metric("Itens de Programação", fmt_int(df["item_cod"].nunique()))
    col2.metric("Procedimentos SIGTAP", fmt_int(df["proc_cod"].nunique()))
    col3.metric("Mapeamentos", fmt_int(len(df)))

    # Busca
    busca = st.text_input("Buscar item ou procedimento", "", key="ip_busca")
    if busca:
        mask = (
            df["item_nome"].str.contains(busca, case=False, na=False)
            | df["proc_nome"].str.contains(busca, case=False, na=False)
            | df["item_cod"].str.contains(busca, na=False)
            | df["proc_cod"].str.contains(busca, na=False)
        )
        df = df[mask]

    # Agrupado por item
    itens = df["item_cod"].unique()
    st.markdown(f"**{len(itens)} itens encontrados**")

    for item_cod in itens[:50]:
        df_item = df[df["item_cod"] == item_cod]
        item_nome = df_item["item_nome"].iloc[0]
        with st.expander(f"{item_cod} — {item_nome} ({len(df_item)} procedimentos)"):
            st.dataframe(
                df_item[["proc_cod", "proc_nome"]].rename(columns={
                    "proc_cod": "Código SIGTAP", "proc_nome": "Procedimento",
                }),
                use_container_width=True, hide_index=True,
            )


def _render_abrangencia_geral():
    st.subheader("Abrangência Geral — Itens por Município Executor")

    df = load_abrangencia_resumo()
    if df.empty:
        st.warning("Sem dados de abrangência.")
        return

    tipo_filter = st.sidebar.selectbox("Tipo", ["Todos", "AMBULATORIAL", "HOSPITALAR"], key="ab_tipo")
    if tipo_filter != "Todos":
        df = df[df["tipo"].str.upper() == tipo_filter]

    executor_filter = st.sidebar.selectbox(
        "Município Executor",
        ["Todos"] + sorted(df["municipio_executor"].unique().tolist()),
        key="ab_exec",
    )
    if executor_filter != "Todos":
        df = df[df["municipio_executor"] == executor_filter]

    # Métricas
    col1, col2, col3 = st.columns(3)
    col1.metric("Executores", fmt_int(df["municipio_executor"].nunique()))
    col2.metric("Itens pactuados", fmt_int(df["item_cod"].nunique()))
    col3.metric("Valor total", fmt_brl(df["valor_total"].sum()))

    # Por executor
    df_exec = df.groupby("municipio_executor").agg({
        "item_cod": "nunique",
        "quantidade": "sum",
        "valor_total": "sum",
    }).sort_values("valor_total", ascending=False).reset_index()
    df_exec.columns = ["Município Executor", "Itens", "Quantidade", "Valor Total"]

    fig = px.bar(
        df_exec.head(20), x="Município Executor", y="Valor Total",
        title="Top 20 Executores por Valor Pactuado",
        color="Quantidade", color_continuous_scale="Blues",
    )
    fig.update_layout(xaxis_tickangle=-45, height=500)
    st.plotly_chart(fig, use_container_width=True)

    # Tabela detalhada
    st.dataframe(
        df[["tipo", "item_cod", "item_nome", "municipio_executor",
            "quantidade", "valor_unitario", "valor_total"]].rename(columns={
            "tipo": "Tipo", "item_cod": "Código", "item_nome": "Item",
            "municipio_executor": "Executor", "quantidade": "Qtd",
            "valor_unitario": "Vl. Unit.", "valor_total": "Vl. Total",
        }),
        use_container_width=True, hide_index=True,
    )
