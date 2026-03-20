"""
Scraper do módulo Diretoria do sistema hospitalar (177.10.203.220).
Extrai dados de:
- Relatórios Analíticos: Internação e Urgência
- Relatórios NAQ: Taxa de Ocupação, Censo Geral, Tempo de Espera, Classificação de Risco

Usage:
    python scraper_diretoria.py                           # Mês atual
    python scraper_diretoria.py --inicio 2026-01-01 --fim 2026-01-31
    python scraper_diretoria.py --only internacao
    python scraper_diretoria.py --only urgencia
    python scraper_diretoria.py --only qualidade
"""
import asyncio
import sys
import re
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
import db_manager

# Credentials & URLs
LOGIN = "ItaloCunha"
PASSWORD = "10208535497"
LOGIN_URL = "http://177.10.203.220/projetoisea/PAGINA%20DE%20LOGIN.php"
BASE_URL = "http://177.10.203.220/projetoisea/"

# Report URLs
URL_INTERNACAO = f"{BASE_URL}relainternamento.php"
URL_URGENCIA = f"{BASE_URL}relaurgencia.php"
URL_QUALIDADE = f"{BASE_URL}relanaqarquivo.php"

# Quality report radio values
NAQ_TAXA_OCUPACAO = "1"
NAQ_TAXA_OCUPACAO_CLINICA = "4"  # value=4 is "TAXA DE OCUPAÇÃO/CLÍNICA/ENFER" which showed clinic data
NAQ_CENSO_GERAL = "2"
NAQ_CENSO_GERAL_CIDADE = "18"
NAQ_TEMPO_ESPERA = "10"
NAQ_TEMPO_ATENDIMENTO_CR = "11"


async def login_diretoria(page, log=print):
    """Login to the hospital system and select Diretoria module."""
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
    await page.fill('input[name="usuario"]', LOGIN)
    await page.fill('input[name="senha"]', PASSWORD)
    await page.click('input[name="grau"][value="5"]')
    await page.wait_for_selector('select#setor')
    await page.select_option('select#setor', value="Direção")
    await page.click('.login100-form-btn')
    await page.wait_for_load_state("networkidle")
    log("Login Diretoria OK!")


async def extract_table_rows(page):
    """Extract all rows from the first data table on the page."""
    return await page.evaluate("""
        () => {
            const table = document.querySelector('table');
            if (!table) return {headers: [], rows: []};
            const headerRow = table.querySelector('tr');
            const headers = headerRow
                ? Array.from(headerRow.querySelectorAll('th, td')).map(c => c.textContent.trim())
                : [];
            const allRows = Array.from(table.querySelectorAll('tr')).slice(1);
            const rows = allRows.map(tr =>
                Array.from(tr.querySelectorAll('td')).map(td => td.textContent.trim())
            );
            return {headers, rows};
        }
    """)


async def extract_all_tables(page):
    """Extract all tables from the page."""
    return await page.evaluate("""
        () => {
            const tables = document.querySelectorAll('table');
            return Array.from(tables).map(table => {
                const allRows = Array.from(table.querySelectorAll('tr'));
                const headers = allRows.length > 0
                    ? Array.from(allRows[0].querySelectorAll('th, td')).map(c => c.textContent.trim())
                    : [];
                const rows = allRows.slice(1).map(tr =>
                    Array.from(tr.querySelectorAll('td')).map(td => td.textContent.trim())
                );
                return {headers, rows};
            });
        }
    """)


def parse_date_br(date_str):
    """Convert DD/MM/YYYY to YYYY-MM-DD for SQLite sorting."""
    if not date_str or date_str == '-':
        return ''
    try:
        parts = date_str.strip().split('/')
        if len(parts) == 3:
            return f"{parts[2]}-{parts[1]}-{parts[0]}"
    except Exception:
        pass
    return date_str


# ============================================================
# INTERNAÇÃO
# ============================================================

INTERNACAO_HEADERS = [
    'prontuario', 'paciente', 'cpf', 'cns', 'nome_mae', 'dt_nascimento',
    'dt_internacao', 'hora_internacao', 'cidade', 'medico', 'clinica',
    'enfermaria', 'leito', 'especialidade', 'cid', 'sexo', 'idade',
    'atendente_responsavel'
]


async def scrape_internacao(page, data_inicio, data_fim, log=print):
    """Scrape internação report for the given date range."""
    log(f"Internação: {data_inicio} a {data_fim}")
    await page.goto(URL_INTERNACAO, wait_until="networkidle", timeout=60000)

    await page.fill('input[name="matricula"]', data_inicio)
    await page.fill('input[name="matricula1"]', data_fim)
    await page.click('input[name="buscar"]')
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(2)

    table_data = await extract_table_rows(page)
    rows = table_data['rows']
    log(f"  Internação: {len(rows)} registros encontrados")

    records = []
    for row in rows:
        if len(row) < 18:
            continue
        record = {}
        for i, key in enumerate(INTERNACAO_HEADERS):
            record[key] = row[i] if i < len(row) else ''
        # Convert dates to sortable format
        record['dt_nascimento'] = parse_date_br(record['dt_nascimento'])
        record['dt_internacao'] = parse_date_br(record['dt_internacao'])
        records.append(record)

    if records:
        saved = db_manager.save_estat_internacao_batch(records, data_inicio, data_fim)
        log(f"  Internação: {saved} registros salvos no banco")

    return len(records)


# ============================================================
# URGÊNCIA
# ============================================================

URGENCIA_HEADERS = [
    'prontuario', 'paciente', 'cpf', 'cns', 'nome_mae', 'dt_nascimento',
    'dt_atendimento', 'hora_atendimento', 'cidade', 'motivo', 'gerador_ficha',
    'cid', 'atendido_por', 'especialidade', 'status_final', 'hora_status_final'
]


async def scrape_urgencia(page, data_inicio, data_fim, log=print):
    """Scrape urgência report for the given date range."""
    log(f"Urgência: {data_inicio} a {data_fim}")
    await page.goto(URL_URGENCIA, wait_until="networkidle", timeout=60000)

    await page.fill('input[name="matricula"]', data_inicio)
    await page.fill('input[name="matricula1"]', data_fim)
    await page.click('input[name="buscar"]')
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(2)

    table_data = await extract_table_rows(page)
    rows = table_data['rows']
    log(f"  Urgência: {len(rows)} registros encontrados")

    records = []
    for row in rows:
        if len(row) < 13:
            continue
        record = {}
        for i, key in enumerate(URGENCIA_HEADERS):
            record[key] = row[i] if i < len(row) else ''
        record['dt_nascimento'] = parse_date_br(record['dt_nascimento'])
        record['dt_atendimento'] = parse_date_br(record['dt_atendimento'])
        records.append(record)

    if records:
        saved = db_manager.save_estat_urgencia_batch(records, data_inicio, data_fim)
        log(f"  Urgência: {saved} registros salvos no banco")

    return len(records)


# ============================================================
# QUALIDADE (NAQ)
# ============================================================

async def _click_radio_and_submit(page, radio_value, data_inicio, data_fim):
    """Navigate to quality page, click radio, fill dates, submit."""
    await page.goto(URL_QUALIDADE, wait_until="networkidle", timeout=60000)

    # Click the specific radio button by value
    all_radios = await page.query_selector_all('input[name="caso"]')
    clicked = False
    for radio in all_radios:
        val = await radio.get_attribute('value')
        if val == radio_value:
            await radio.click()
            clicked = True
            break

    if not clicked:
        return False

    await asyncio.sleep(0.5)

    # Fill visible date inputs
    date_inputs = await page.query_selector_all('input[type="date"]')
    filled = 0
    for di in date_inputs:
        visible = await di.evaluate("el => el.offsetParent !== null")
        if visible:
            if filled == 0:
                await di.fill(data_inicio)
            elif filled == 1:
                await di.fill(data_fim)
            filled += 1
            if filled >= 2:
                break

    # Click visible submit button
    submits = await page.query_selector_all('input[type="submit"]')
    for sub in submits:
        vis = await sub.evaluate("el => el.offsetParent !== null")
        if vis:
            try:
                await sub.click(timeout=60000)
            except Exception:
                # Fallback: click via JS to bypass navigation wait
                await sub.evaluate("el => el.click()")
            try:
                await page.wait_for_load_state("networkidle", timeout=300000)
            except Exception:
                try:
                    await page.wait_for_selector('table', timeout=120000)
                except Exception:
                    pass
            await asyncio.sleep(2)
            return True

    return False


async def scrape_naq_taxa_ocupacao(page, data_inicio, data_fim, log=print):
    """Scrape Taxa de Ocupação (radio value=1)."""
    log(f"NAQ Taxa de Ocupação: {data_inicio} a {data_fim}")

    if not await _click_radio_and_submit(page, NAQ_TAXA_OCUPACAO, data_inicio, data_fim):
        log("  ERRO: Não conseguiu submeter formulário")
        return 0

    tables = await extract_all_tables(page)
    if not tables:
        log("  Sem tabelas retornadas")
        return 0

    # First table: patient details
    detalhes = []
    detail_headers = ['prontuario', 'paciente', 'nome_mae', 'dt_nascimento',
                      'dt_internacao', 'alta', 'cidade', 'medico', 'especialidade',
                      'clinica', 'enfermaria', 'leito', 'tempo_perm_periodo', 'tempo_perm_total']

    if tables[0]['rows']:
        for row in tables[0]['rows']:
            if len(row) < 12:
                continue
            record = {}
            for i, key in enumerate(detail_headers):
                record[key] = row[i] if i < len(row) else ''
            record['dt_nascimento'] = parse_date_br(record['dt_nascimento'])
            record['dt_internacao'] = parse_date_br(record['dt_internacao'])
            record['alta'] = parse_date_br(record['alta'])
            # Parse integer fields
            try:
                record['tempo_perm_periodo'] = int(record.get('tempo_perm_periodo', '0') or '0')
            except ValueError:
                record['tempo_perm_periodo'] = 0
            try:
                record['tempo_perm_total'] = int(record.get('tempo_perm_total', '0') or '0')
            except ValueError:
                record['tempo_perm_total'] = 0
            detalhes.append(record)

    # Second table: summary (Taxa de Ocupação, Tempo Médio, Média Pac Dia)
    resumo = None
    if len(tables) > 1 and tables[1]['rows']:
        summary_row = tables[1]['rows'][0]
        if len(summary_row) >= 3:
            try:
                taxa = float(summary_row[0].replace('%', '').replace(',', '.').strip())
            except ValueError:
                taxa = 0.0
            try:
                tempo_medio = float(summary_row[1].replace(',', '.').strip())
            except ValueError:
                tempo_medio = 0.0
            try:
                media_pac = float(summary_row[2].replace(',', '.').strip())
            except ValueError:
                media_pac = 0.0
            resumo = {
                'taxa_ocupacao': taxa,
                'tempo_medio_perm': tempo_medio,
                'media_pac_dia': media_pac
            }

    log(f"  Taxa Ocupação: {len(detalhes)} pacientes, resumo={'sim' if resumo else 'não'}")
    if resumo:
        log(f"    Taxa: {resumo['taxa_ocupacao']}%, Tempo Médio: {resumo['tempo_medio_perm']}, Média Pac/Dia: {resumo['media_pac_dia']}")

    db_manager.save_naq_taxa_ocupacao(data_inicio, data_fim, resumo, detalhes)
    return len(detalhes)


async def scrape_naq_taxa_ocupacao_clinica(page, data_inicio, data_fim, log=print):
    """Scrape Taxa de Ocupação por Clínica (radio value=4)."""
    log(f"NAQ Taxa Ocupação/Clínica: {data_inicio} a {data_fim}")

    if not await _click_radio_and_submit(page, NAQ_TAXA_OCUPACAO_CLINICA, data_inicio, data_fim):
        log("  ERRO: Não conseguiu submeter formulário")
        return 0

    tables = await extract_all_tables(page)
    if not tables or not tables[0]['rows']:
        log("  Sem dados retornados")
        return 0

    records = []
    for row in tables[0]['rows']:
        if len(row) >= 2:
            try:
                ocupados = int(row[1].strip())
            except ValueError:
                ocupados = 0
            records.append({
                'clinica': row[0].strip(),
                'ocupados': ocupados
            })

    log(f"  Taxa Ocupação/Clínica: {len(records)} clínicas")
    db_manager.save_naq_taxa_ocupacao_clinica(data_inicio, data_fim, records)
    return len(records)


async def scrape_naq_censo_geral(page, data_inicio, data_fim, log=print):
    """Scrape Censo Geral (radio value=2)."""
    log(f"NAQ Censo Geral: {data_inicio} a {data_fim}")

    if not await _click_radio_and_submit(page, NAQ_CENSO_GERAL, data_inicio, data_fim):
        log("  ERRO: Não conseguiu submeter formulário")
        return 0

    tables = await extract_all_tables(page)
    if not tables or not tables[0]['rows']:
        log("  Sem dados retornados")
        return 0

    # Censo headers: CLINICA, ENFERMARIA, LEITOS, PRONTUÁRIO, PACIENTE, IDADE,
    #                CIDADE, DIAGNÓSTICO, ESPECIALIDADE, D.I, DATA DA INTERNAÇÃO, PREVISÃO DE ALTA
    censo_keys = ['clinica', 'enfermaria', 'leitos', 'prontuario', 'paciente', 'idade',
                  'cidade', 'diagnostico', 'especialidade', 'dias_internacao',
                  'dt_internacao', 'previsao_alta']

    records = []
    for row in tables[0]['rows']:
        if len(row) < 6:
            continue
        record = {}
        for i, key in enumerate(censo_keys):
            record[key] = row[i] if i < len(row) else ''
        record['dt_internacao'] = parse_date_br(record['dt_internacao'])
        record['previsao_alta'] = parse_date_br(record['previsao_alta'])
        records.append(record)

    # Use data_fim as the census date (represents "snapshot" date)
    log(f"  Censo Geral: {len(records)} leitos/registros")
    db_manager.save_naq_censo_geral(data_fim, records)
    return len(records)


async def scrape_naq_censo_geral_cidade(page, data_inicio, data_fim, log=print):
    """Scrape Censo Geral por Cidade (radio value=18)."""
    log(f"NAQ Censo Geral por Cidade: {data_inicio} a {data_fim}")

    if not await _click_radio_and_submit(page, NAQ_CENSO_GERAL_CIDADE, data_inicio, data_fim):
        log("  ERRO: Não conseguiu submeter formulário")
        return 0

    tables = await extract_all_tables(page)
    if not tables or not tables[0]['rows']:
        log("  Sem dados retornados")
        return 0

    # The structure may vary; capture all columns dynamically
    headers = tables[0]['headers']
    records = []
    for row in tables[0]['rows']:
        if len(row) < 4:
            continue
        # Map to known fields based on header position
        record = {}
        for i, h in enumerate(headers):
            h_lower = h.lower()
            if i < len(row):
                val = row[i]
                if 'cidade' in h_lower:
                    record['cidade'] = val
                elif 'clinica' in h_lower or 'clínica' in h_lower:
                    record['clinica'] = val
                elif 'enfermaria' in h_lower:
                    record['enfermaria'] = val
                elif 'leito' in h_lower:
                    record['leitos'] = val
                elif 'prontu' in h_lower or 'número' in h_lower:
                    record['prontuario'] = val
                elif 'paciente' in h_lower:
                    record['paciente'] = val
                elif 'idade' in h_lower:
                    record['idade'] = val
                elif 'diagn' in h_lower:
                    record['diagnostico'] = val
                elif 'especialidade' in h_lower:
                    record['especialidade'] = val
                elif 'd.i' in h_lower or 'dias' in h_lower:
                    record['dias_internacao'] = val
                elif 'interna' in h_lower:
                    record['dt_internacao'] = parse_date_br(val)
                elif 'previs' in h_lower or 'alta' in h_lower:
                    record['previsao_alta'] = parse_date_br(val)
        records.append(record)

    log(f"  Censo por Cidade: {len(records)} registros")
    db_manager.save_naq_censo_geral_cidade(data_inicio, data_fim, records)
    return len(records)


async def scrape_naq_tempo_espera(page, data_inicio, data_fim, log=print):
    """Scrape Tempo de Espera para Internação (radio value=10)."""
    log(f"NAQ Tempo Espera Internação: {data_inicio} a {data_fim}")

    if not await _click_radio_and_submit(page, NAQ_TEMPO_ESPERA, data_inicio, data_fim):
        log("  ERRO: Não conseguiu submeter formulário")
        return 0

    tables = await extract_all_tables(page)
    if not tables or not tables[0]['rows']:
        log("  Sem dados retornados")
        return 0

    headers = tables[0]['headers']
    log(f"  Headers Tempo Espera: {headers}")

    records = []
    for row in tables[0]['rows']:
        if len(row) < 4:
            continue
        record = {}
        for i, h in enumerate(headers):
            h_lower = h.lower()
            if i < len(row):
                val = row[i]
                if 'prontu' in h_lower or 'número' in h_lower:
                    record['prontuario'] = val
                elif 'paciente' in h_lower:
                    record['paciente'] = val
                elif 'atendimento' in h_lower and 'data' in h_lower:
                    record['dt_atendimento'] = parse_date_br(val)
                elif 'atendimento' in h_lower and 'hora' in h_lower:
                    record['hora_atendimento'] = val
                elif 'interna' in h_lower and 'data' in h_lower:
                    record['dt_internacao'] = parse_date_br(val)
                elif 'interna' in h_lower and 'hora' in h_lower:
                    record['hora_internacao'] = val
                elif 'espera' in h_lower or 'tempo' in h_lower:
                    record['tempo_espera'] = val
                elif 'cidade' in h_lower:
                    record['cidade'] = val
                elif 'clinica' in h_lower or 'clínica' in h_lower:
                    record['clinica'] = val
                elif 'especialidade' in h_lower:
                    record['especialidade'] = val
        records.append(record)

    log(f"  Tempo Espera: {len(records)} registros")
    db_manager.save_naq_tempo_espera(data_inicio, data_fim, records)
    return len(records)


async def scrape_naq_tempo_atendimento_cr(page, data_inicio, data_fim, log=print):
    """Scrape Tempo de Atendimento - Classificação de Risco (radio value=11)."""
    log(f"NAQ Tempo Atendimento CR: {data_inicio} a {data_fim}")

    if not await _click_radio_and_submit(page, NAQ_TEMPO_ATENDIMENTO_CR, data_inicio, data_fim):
        log("  ERRO: Não conseguiu submeter formulário")
        return 0

    tables = await extract_all_tables(page)
    if not tables or not tables[0]['rows']:
        log("  Sem dados retornados")
        return 0

    headers = tables[0]['headers']
    log(f"  Headers Tempo CR: {headers}")

    # Real headers: Número do Prontuário, Paciente, Data do Atendimento,
    # Hora Ficha de Atendimento, Cor da Classificação, Hora Classificação de Risco,
    # Hora dif classificação, Enfermeiro(a)
    records = []
    for row in tables[0]['rows']:
        if len(row) < 4:
            continue
        record = {}
        for i, h in enumerate(headers):
            h_lower = h.lower()
            if i < len(row):
                val = row[i]
                if 'prontu' in h_lower or 'número' in h_lower:
                    record['prontuario'] = val
                elif 'paciente' in h_lower:
                    record['paciente'] = val
                elif 'data' in h_lower:
                    record['dt_atendimento'] = parse_date_br(val)
                elif 'hora' in h_lower and 'ficha' in h_lower:
                    record['hora_atendimento'] = val
                elif 'cor' in h_lower:
                    record['cor'] = val
                elif 'hora' in h_lower and 'classifica' in h_lower:
                    record['hora_classificacao'] = val
                elif 'dif' in h_lower:
                    record['tempo_espera'] = val
                elif 'enfermeiro' in h_lower:
                    record['hora_atendimento_medico'] = val
                elif 'cidade' in h_lower:
                    record['cidade'] = val
                elif 'motivo' in h_lower:
                    record['motivo'] = val
        records.append(record)

    log(f"  Tempo Atendimento CR: {len(records)} registros")
    db_manager.save_naq_tempo_atendimento_cr(data_inicio, data_fim, records)
    return len(records)


# ============================================================
# ORCHESTRATOR (SEQUENTIAL)
# ============================================================

def _generate_monthly_ranges(data_inicio, data_fim):
    """Generate (start, end) tuples for each month in the range."""
    from calendar import monthrange
    start = datetime.strptime(data_inicio, '%Y-%m-%d')
    end = datetime.strptime(data_fim, '%Y-%m-%d')
    ranges = []
    current = start.replace(day=1)
    while current <= end:
        month_start = max(current, start)
        last_day = monthrange(current.year, current.month)[1]
        month_end = min(current.replace(day=last_day), end)
        ranges.append((month_start.strftime('%Y-%m-%d'), month_end.strftime('%Y-%m-%d')))
        # Next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return ranges


async def _scrape_month(page, mes_inicio, mes_fim, only, log):
    """Scrape all reports for a single month."""
    results = {}

    if not only or only == 'internacao':
        try:
            results['internacao'] = await scrape_internacao(page, mes_inicio, mes_fim, log)
        except Exception as e:
            log(f"  ERRO Internação: {e}")
            results['internacao'] = 0

    if not only or only == 'urgencia':
        try:
            results['urgencia'] = await scrape_urgencia(page, mes_inicio, mes_fim, log)
        except Exception as e:
            log(f"  ERRO Urgência: {e}")
            results['urgencia'] = 0

    if not only or only == 'qualidade':
        naq_tasks = [
            ('naq_taxa_ocupacao', scrape_naq_taxa_ocupacao),
            ('naq_taxa_ocupacao_clinica', scrape_naq_taxa_ocupacao_clinica),
            ('naq_censo_geral', scrape_naq_censo_geral),
            ('naq_censo_cidade', scrape_naq_censo_geral_cidade),
            ('naq_tempo_espera', scrape_naq_tempo_espera),
            ('naq_tempo_cr', scrape_naq_tempo_atendimento_cr),
        ]
        for name, func in naq_tasks:
            try:
                results[name] = await func(page, mes_inicio, mes_fim, log)
            except Exception as e:
                log(f"  ERRO {name}: {e}")
                results[name] = 0

    return results


async def run_scraper_diretoria(data_inicio=None, data_fim=None, only=None, log=print):
    """
    Main entry point. Scrapes all Diretoria reports month by month.

    Args:
        data_inicio: Start date in YYYY-MM-DD format (default: first of current month)
        data_fim: End date in YYYY-MM-DD format (default: today)
        only: 'internacao', 'urgencia', or 'qualidade' to scrape only one section
        log: Logging function
    """
    if not data_inicio:
        today = datetime.now()
        data_inicio = today.replace(day=1).strftime('%Y-%m-%d')
    if not data_fim:
        data_fim = datetime.now().strftime('%Y-%m-%d')

    months = _generate_monthly_ranges(data_inicio, data_fim)

    log(f"\n{'='*60}")
    log(f"SCRAPER DIRETORIA: {data_inicio} a {data_fim} ({len(months)} meses)")
    log(f"{'='*60}")

    start_time = datetime.now()
    totals = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        try:
            await login_diretoria(page, log)

            for i, (mes_inicio, mes_fim) in enumerate(months, 1):
                log(f"\n{'='*60}")
                log(f"MÊS {i}/{len(months)}: {mes_inicio} a {mes_fim}")
                log(f"{'='*60}")

                month_results = await _scrape_month(page, mes_inicio, mes_fim, only, log)

                # Accumulate totals
                for key, count in month_results.items():
                    totals[key] = totals.get(key, 0) + count

                # Month summary
                month_total = sum(month_results.values())
                log(f"  >> Mês {mes_inicio[:7]}: {month_total} registros")

            # Final summary
            elapsed = (datetime.now() - start_time).total_seconds()
            log(f"\n{'='*60}")
            log(f"RESUMO FINAL ({len(months)} meses em {elapsed:.1f}s)")
            log(f"{'='*60}")
            grand_total = 0
            for key, count in totals.items():
                log(f"  {key}: {count} registros")
                grand_total += count
            log(f"  TOTAL GERAL: {grand_total} registros em {elapsed:.1f}s")

        finally:
            await browser.close()

    return totals


if __name__ == "__main__":
    args = sys.argv[1:]

    data_inicio = None
    data_fim = None
    only = None

    for i, arg in enumerate(args):
        if arg == "--inicio" and i + 1 < len(args):
            data_inicio = args[i + 1]
        elif arg == "--fim" and i + 1 < len(args):
            data_fim = args[i + 1]
        elif arg == "--only" and i + 1 < len(args):
            only = args[i + 1]

    asyncio.run(run_scraper_diretoria(data_inicio, data_fim, only))
