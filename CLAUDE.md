# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Healthcare analytics dashboard for obstetric care production in Campina Grande, Brazil. Integrates three data sources:
- **Hospital system (ISEA/CLIPSI)**: Web-scraped AIH records and procedures from `http://177.10.203.220/projetoisea/`
- **SIGTAP (DATASUS)**: SUS unified procedure pricing table
- **Contractual data (PAES)**: Municipal agreements via CSV/Excel files

## Commands

```bash
# Run the Streamlit dashboard (port 8502, login: admin / obstetricia2026)
streamlit run app.py --server.port=8502

# Initialize/migrate the SQLite database
python db_manager.py

# Full sync: scrape hospital data + fetch SIGTAP costs + propagate
python run_sync.py
python run_sync.py --comp 03/2026        # single competence
python run_sync.py --hospital-only        # only hospital scraping
python run_sync.py --sigtap-only          # only SIGTAP cost fetch

# Re-extract all months with problem flagging
python run_scraper_todos_meses.py

# Docker deployment
docker-compose up
```

There is no formal test runner. Test/diagnostic scripts (`test_*.py`, `diag_*.py`) are standalone and run individually with `python <script>.py`.

## Architecture

```
scraper_hospital.py  ──┐
scraper_sigtap.py    ──┼──▶  saude_real.db (SQLite)  ──▶  app.py (Streamlit dashboard)
run_sync.py (orchestrator)    db_manager.py (schema/queries)
```

**Data flow**: Playwright scrapers extract hospital records and SIGTAP costs → stored in SQLite via db_manager → dashboard loads DB + Excel + CSV for rendering.

### Key files

- **app.py** (~1700 lines): Main dashboard with 8 views (Resumo Executivo, Comparativo por Hospital, Análise por Procedimento, Produção por Município, Pactuação vs Realizado, Detalhamento de Custos, Pacientes e Cidades, Database Integration). Handles login, Excel/CSV parsing, and all Plotly visualizations.
- **db_manager.py**: Schema definitions, migrations, and query helpers. Tables: `pacientes`, `aih_records`, `aih_procedimentos`, `sigtap_metadata`.
- **scraper_hospital.py**: Async Playwright scraper with concurrent tabs (5-10). Extracts patient info, AIH records, and procedures. Flags problems (missing AIH/CNS/CID/dates) in the `observacao` field.
- **scraper_sigtap.py**: Fetches procedure costs from DATASUS. Prefers `t_hosp` (hospitalization), falls back to `t_amb` (ambulatorial).
- **run_sync.py**: Orchestrates hospital scraping → SIGTAP sync → cost propagation pipeline.

### Database schema (SQLite: saude_real.db)

- `pacientes` — PK: `cns`. Patient demographics.
- `aih_records` — PK: `(prontuario, competencia, data_ent, data_sai)`. Hospital internment records, FK to pacientes.
- `aih_procedimentos` — PK: `id`. Procedures per AIH with costs. FK to aih_records via `id_aih`.
- `sigtap_metadata` — PK: `(proc_cod, competencia)`. Official SUS procedure pricing.
- `sigtap_custo_atual` — View returning latest cost per procedure.

### Data sources (local files)

- `Produção AIH's Obstetricia CG_ISEA_CLIPSI_2025.xlsx` — 5 sheets with CLIPSI/ISEA procedure quantities and values, municipal distribution, CPN data.
- `pactuacao_paes_2025.csv` — Municipal contracts (encaminhador, quantity, unit price, total).
- `itens_programacao.csv` — SIGTAP code-to-description mapping.

## Key Domain Constants

- `BONUS_CLIPSI = R$ 800.00` per procedure (contractual bonus added to CLIPSI costs)
- Procedure codes are 10-digit SIGTAP codes; city codes are 6-digit IBGE codes
- Procedure `0310010055` is excluded from ISEA when CPN data exists (avoid double-counting)
- Competences format: `MM/YYYY` (e.g., `06/2025`)
- Cost propagation: `t_hosp` preferred, fallback `t_amb` when `t_hosp = 0`

## Tech Stack

Python 3.11+, Streamlit, Playwright (async), SQLite3, Pandas, Plotly, openpyxl. Deployed via Docker (python:3.11-slim).

## Documentation

`documentacao_dashboard.md` contains the full specification of all metrics, formulas, and chart definitions used in the dashboard.
