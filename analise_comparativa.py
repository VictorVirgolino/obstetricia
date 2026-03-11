import pandas as pd
import os
import re
import unicodedata
import openpyxl

# --- CONFIGURAÇÃO DE CAMINHOS ---
DATA_DIR = os.path.dirname(os.path.abspath(__file__))
EXCEL_FILE = os.path.join(DATA_DIR, "Produção AIH's Obstetricia CG_ISEA_CLIPSI_2025.xlsx")
CSV_PAES = os.path.join(DATA_DIR, "pactuacao_paes_2025.csv")
MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

# --- FUNÇÕES DE UTILIDADE ---
def normalize_name(name: str) -> str:
    name = str(name).upper().strip()
    name = unicodedata.normalize("NFKD", name)
    return "".join(c for c in name if not unicodedata.combining(c))

def fmt_brl(valor):
    return f"R$ {valor:,.2f}"

def _parse_mun_sheet(df):
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

# --- 1. CARREGAR PACTUAÇÃO (CSV) ---
print("Carregando Pactuação (PAES 2025)...")
pact = pd.read_csv(CSV_PAES, sep=";")
pact["municipio"] = pact["municipio_encaminhador"].astype(str).str.upper().str.strip()
pact["pactuado_qty"] = pd.to_numeric(pact["quantidade_pactuada"], errors="coerce").fillna(0).astype(int)
val = pact["valor_total"].astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
pact["valor_pactuado"] = pd.to_numeric(val, errors="coerce").fillna(0.0)
pact["mun_norm"] = pact["municipio"].apply(normalize_name)

# Agrupar por município
pact_agg = pact.groupby("mun_norm").agg({
    "municipio": "first",
    "pactuado_qty": "sum",
    "valor_pactuado": "sum"
}).reset_index()

# --- 2. CARREGAR PRODUÇÃO REAL (EXCEL) ---
print("Carregando Produção Real (Excel)...")
df_clipsi = pd.read_excel(EXCEL_FILE, sheet_name=1, header=None) # Clipsi Mun
df_isea = pd.read_excel(EXCEL_FILE, sheet_name=3, header=None)   # Isea Mun

_, clipsi_val = _parse_mun_sheet(df_clipsi)
_, isea_val = _parse_mun_sheet(df_isea)

# Adicionar flag de hospital e concatenar
clipsi_val["hospital"] = "CLIPSI"
isea_val["hospital"] = "ISEA"
real_val = pd.concat([clipsi_val, isea_val], ignore_index=True)

# Agrupar produção real por município
real_agg = real_val.groupby("municipio")["total"].sum().reset_index(name="custo_real_producao")
real_agg["mun_norm"] = real_agg["municipio"].apply(normalize_name)

# --- 3. MERGE E COMPARAÇÃO ---
print("Cruzando dados...")
df_comp = pd.merge(pact_agg, real_agg[["mun_norm", "custo_real_producao"]], on="mun_norm", how="outer").fillna(0)

# Cálculos de diferença
df_comp["saldo_financeiro"] = df_comp["valor_pactuado"] - df_comp["custo_real_producao"]
df_comp["situacao"] = df_comp["saldo_financeiro"].apply(lambda x: "Superavit (Sobrou)" if x > 0 else "Deficit (Custo > Pacto)")

# Ordenar por maior déficit (onde Campina Grande está perdendo mais dinheiro)
df_comp = df_comp.sort_values("saldo_financeiro", ascending=True)

# --- 4. EXIBIÇÃO DOS RESULTADOS ---
print("\n" + "="*80)
print("RESUMO COMPARATIVO: PACTUAÇÃO (PAES 2025) VS PRODUÇÃO REAL (ISEA + CLIPSI)")
print("="*80)

total_pactuado = df_comp["valor_pactuado"].sum()
total_producao = df_comp["custo_real_producao"].sum()
saldo_total = total_pactuado - total_producao

print(f"Total Arrecadado (Pactuação):      {fmt_brl(total_pactuado)}")
print(f"Custo Real de Produção (Excel):    {fmt_brl(total_producao)}")
print(f"Saldo Global (Diferença):          {fmt_brl(saldo_total)}")
print("-" * 80)

# Excluir Campina Grande da tabela de municípios (pois CG é quem paga/arrecada)
df_mun = df_comp[df_comp["mun_norm"] != "CAMPINA GRANDE"].copy()

print("\nTOP 10 MUNICÍPIOS COM MAIOR DÉFICIT (CUSTO > PACTUAÇÃO):")
cols_show = ["municipio", "valor_pactuado", "custo_real_producao", "saldo_financeiro"]
top_deficit = df_mun.head(10)[cols_show].copy()
for col in ["valor_pactuado", "custo_real_producao", "saldo_financeiro"]:
    top_deficit[col] = top_deficit[col].apply(fmt_brl)
print(top_deficit)

print("\nMUNICÍPIOS QUE NÃO TEM PACTUAÇÃO MAS GERARAM CUSTO (TOP 5):")
nao_pact = df_mun[df_mun["valor_pactuado"] == 0].sort_values("custo_real_producao", ascending=False).head(5)
if not nao_pact.empty:
    top_nao_pact = nao_pact[cols_show].copy()
    for col in ["valor_pactuado", "custo_real_producao", "saldo_financeiro"]:
        top_nao_pact[col] = top_nao_pact[col].apply(fmt_brl)
    print(top_nao_pact)
else:
    print("Nenhum município sem pactuação identificado.")

# Exportar para CSV para abrir no Excel se necessário
df_comp.to_csv(os.path.join(DATA_DIR, "comparativo_financeiro_completo.csv"), sep=";", index=False, encoding="latin1")
print("\nArquivo completo exportado para: comparativo_financeiro_completo.csv")
