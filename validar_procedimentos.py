"""
Validador de Procedimentos: compara dados do site hospitalar com o banco de dados local.

Itera por todas as competencias e prontuarios no site, extrai procedimentos e compara
com o que esta em saude_real.db. Reporta discrepancias.

Uso:
    python validar_procedimentos.py                  # todas as competencias
    python validar_procedimentos.py --comp 06/2025   # competencia unica
"""

import asyncio
import argparse
import re
import sqlite3
import sys
from datetime import datetime
from collections import defaultdict

from playwright.async_api import async_playwright

# Windows UTF-8 compatibility
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# ── Credentials & URLs (same as scraper_hospital.py) ──
LOGIN = "ItaloCunha"
PASSWORD = "10208535497"
LOGIN_URL = "http://177.10.203.220/projetoisea/PAGINA%20DE%20LOGIN.php"
REPORT_URL = "http://177.10.203.220/projetoisea/relasisaih.php?operacao=R"
BASE_URL = "http://177.10.203.220/projetoisea/"
DB_NAME = "saude_real.db"

# JS to extract procedures from detail page (identical to scraper)
EXTRACT_PROCS_JS = """() => {
    const rows = [];
    const tables = document.querySelectorAll('table');
    for (const table of tables) {
        const headerRow = table.querySelector('tr');
        if (!headerRow) continue;
        const headerText = headerRow.innerText;
        if (headerText.includes('Procedimento') && headerText.includes('Qtd') && headerText.includes('CBO')) {
            const trs = Array.from(table.querySelectorAll('tr'));
            for (let i = 1; i < trs.length; i++) {
                const tds = trs[i].querySelectorAll('td');
                if (tds.length >= 7) {
                    const code = tds[1]?.innerText?.trim();
                    const desc = tds[2]?.innerText?.trim() || '';
                    const qty = tds[3]?.innerText?.trim();
                    const cbo = tds[5]?.innerText?.trim() || '';
                    const cnes = tds[6]?.innerText?.trim() || '';
                    if (code && code.match(/^[0-9]{10}$/)) {
                        rows.push({ code, desc, qty, cbo, cnes });
                    }
                }
            }
            break;
        }
    }
    return rows;
}"""


def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def get_db_procedures(conn, prontuario, competencia, data_ent, data_sai):
    """Return dict of {proc_cod: qtd} from the database for a given AIH."""
    cursor = conn.cursor()
    # Find id_aih first
    cursor.execute(
        "SELECT id_aih FROM aih_records WHERE prontuario = ? AND competencia = ? AND data_ent = ? AND data_sai = ?",
        (prontuario, competencia, data_ent, data_sai)
    )
    row = cursor.fetchone()
    if not row:
        return None, None  # record not in DB at all

    id_aih = row["id_aih"]
    cursor.execute(
        "SELECT proc_cod, qtd FROM aih_procedimentos WHERE id_aih = ?",
        (id_aih,)
    )
    procs = {}
    for r in cursor.fetchall():
        code = r["proc_cod"]
        qty = r["qtd"]
        # Handle duplicate proc_cod in DB (shouldn't happen, but sum if it does)
        procs[code] = procs.get(code, 0) + qty
    return id_aih, procs


def get_all_competencias_from_db(conn):
    """Return list of (month, year) tuples from the database."""
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT competencia FROM aih_records ORDER BY competencia")
    result = []
    for row in cursor.fetchall():
        comp = row["competencia"]
        parts = comp.split("/")
        if len(parts) == 2:
            result.append((parts[0], parts[1]))
    return result


async def safe_get_value(page, selector, default=""):
    try:
        el = await page.query_selector(selector)
        if el:
            tag = await el.evaluate("el => el.tagName")
            if tag == "SELECT":
                return await el.evaluate("el => el.options[el.selectedIndex]?.text || ''")
            return await el.input_value()
        return default
    except Exception:
        return default


async def run_validator(comp_filter=None, max_concurrent=5):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = f"validacao_{timestamp}.log"
    log_file = open(log_path, "w", encoding="utf-8")
    log_lock = asyncio.Lock()

    conn = get_db_connection()

    # Determine competencias to validate
    if comp_filter:
        parts = comp_filter.split("/")
        competencias = [(parts[0], parts[1])]
    else:
        # Use the same default list as scraper
        competencias = [
            ("06", "2025"), ("07", "2025"), ("08", "2025"), ("09", "2025"),
            ("10", "2025"), ("11", "2025"), ("12", "2025"),
            ("01", "2026"), ("02", "2026"), ("03", "2026")
        ]

    async def log(msg):
        async with log_lock:
            print(msg)
            log_file.write(msg + "\n")
            log_file.flush()

    await log(f"Validacao de Procedimentos - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    await log(f"Competencias: {', '.join(f'{m}/{y}' for m, y in competencias)}")
    await log(f"Concorrencia: {max_concurrent} abas simultaneas")
    await log(f"Log: {log_path}")
    await log("=" * 70)

    # Global stats
    global_stats = {
        "total_checked": 0,
        "total_ok": 0,
        "total_mismatch": 0,
        "total_missing_in_db": 0,  # record not in DB at all
        "total_falta_no_db": 0,    # proc on site but not in DB
        "total_extra_no_db": 0,    # proc in DB but not on site
        "total_qtd_errada": 0,
        "total_errors": 0,
    }
    comp_stats = {}  # per-competencia stats
    all_discrepancies = []  # detailed list

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # ── Login ──
            await log("Fazendo login...")
            await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)

            is_logged_in = await page.query_selector('a[href*="relasisaih.php"]')
            if not is_logged_in:
                await page.fill('input[name="usuario"]', LOGIN)
                await page.fill('input[name="senha"]', PASSWORD)
                await page.click('input[name="grau"][value="5"]')
                await page.wait_for_selector('select#setor')
                await page.select_option('select#setor', value="Contas")
                await page.click('.login100-form-btn')
                await page.wait_for_load_state("networkidle")
            await log("Login OK!")

            for month, year in competencias:
                comp_key = f"{month}/{year}"
                await log(f"\n{'='*70}")
                await log(f"COMPETENCIA {comp_key}")
                await log(f"{'='*70}")

                cstats = {
                    "checked": 0,
                    "ok": 0,
                    "mismatch": 0,
                    "missing_in_db": 0,
                    "falta_no_db": 0,
                    "extra_no_db": 0,
                    "qtd_errada": 0,
                    "errors": 0,
                }
                comp_stats[comp_key] = cstats
                cstats_lock = asyncio.Lock()

                # Navigate to report for this competencia
                await page.goto(REPORT_URL, wait_until="networkidle")
                await page.wait_for_selector('input[name="comp"]')
                await page.fill('input[name="comp"]', month)
                await page.fill('input[name="compa"]', year)
                await page.click('input[name="buscar"]')

                try:
                    await page.wait_for_selector('table', timeout=300000)
                except Exception:
                    await log(f"  Sem resultados ou timeout para {comp_key}")
                    continue

                # Extract all links
                links_data = await page.evaluate("""() => {
                    const results = [];
                    const anchors = document.querySelectorAll('a[href*="baixaaihre.php"]');
                    anchors.forEach(a => {
                        const href = a.getAttribute('href') || '';
                        results.push(href);
                    });
                    return results;
                }""")

                await log(f"  Links encontrados no site: {len(links_data)}")

                # Parse tasks
                tasks = []
                for i, href in enumerate(links_data):
                    contar_match = re.search(r"contar=([^&']+)", href)
                    ent_match = re.search(r"dataent=([^&']+)", href)
                    sai_match = re.search(r"datasai=([^&']+)", href)

                    if not contar_match:
                        continue

                    record_id = contar_match.group(1)
                    data_ent_url = ent_match.group(1) if ent_match else ""
                    data_sai_url = sai_match.group(1) if sai_match else ""

                    url_match = re.search(r"location\.href='([^']+)'", href)
                    if url_match:
                        detail_path = url_match.group(1)
                    else:
                        detail_path = f"baixaaihre.php?contar={record_id}&datasai={data_sai_url}&dataent={data_ent_url}"

                    tasks.append({
                        "index": i,
                        "record_id": record_id,
                        "data_ent": data_ent_url,
                        "data_sai": data_sai_url,
                        "detail_url": f"{BASE_URL}{detail_path}",
                        "total": len(links_data),
                        "comp": comp_key,
                        "month": month,
                        "year": year,
                    })

                await log(f"  Prontuarios a validar: {len(tasks)}")
                await log(f"  {'-'*66}")

                semaphore = asyncio.Semaphore(max_concurrent)

                async def validate_record(task):
                    async with semaphore:
                        idx = task["index"]
                        record_id = task["record_id"]
                        total = task["total"]
                        data_ent = task["data_ent"]
                        data_sai = task["data_sai"]
                        comp = task["comp"]
                        label = f"[{idx+1}/{total}]"

                        detail_page = await context.new_page()
                        try:
                            await detail_page.goto(task["detail_url"], wait_until="networkidle", timeout=60000)
                            await asyncio.sleep(0.5)

                            # Extract procedures from site
                            procs_raw = await detail_page.evaluate(EXTRACT_PROCS_JS)

                            site_procs = {}
                            if procs_raw:
                                for proc in procs_raw:
                                    code = proc["code"]
                                    qty = int(proc["qty"]) if proc["qty"].isdigit() else 1
                                    site_procs[code] = site_procs.get(code, 0) + qty
                            else:
                                # Fallback: single main procedure
                                main_proc = await safe_get_value(detail_page, 'input#AIH_PROC_REA')
                                if main_proc and re.match(r'^\d{10}$', main_proc.strip()):
                                    site_procs[main_proc.strip()] = 1

                            # Get DB procedures
                            id_aih, db_procs = get_db_procedures(conn, record_id, comp, data_ent, data_sai)

                            async with cstats_lock:
                                cstats["checked"] += 1

                            if db_procs is None:
                                # Record not in DB at all
                                async with cstats_lock:
                                    cstats["missing_in_db"] += 1
                                disc = {
                                    "comp": comp,
                                    "prontuario": record_id,
                                    "data_ent": data_ent,
                                    "data_sai": data_sai,
                                    "tipo": "REGISTRO_AUSENTE_NO_DB",
                                    "detalhe": f"Site tem {len(site_procs)} proc(s), registro nao existe no banco",
                                    "site_procs": site_procs,
                                    "db_procs": {},
                                }
                                all_discrepancies.append(disc)
                                await log(f"  {label} REGISTRO_AUSENTE_NO_DB: pront={record_id} ent={data_ent} sai={data_sai} | site={len(site_procs)} procs")
                                return

                            # Compare
                            all_codes = set(site_procs.keys()) | set(db_procs.keys())
                            record_ok = True
                            record_issues = []

                            for code in sorted(all_codes):
                                in_site = code in site_procs
                                in_db = code in db_procs

                                if in_site and not in_db:
                                    record_issues.append(f"FALTA_NO_DB: {code} (site qty={site_procs[code]})")
                                    async with cstats_lock:
                                        cstats["falta_no_db"] += 1
                                    record_ok = False
                                elif in_db and not in_site:
                                    record_issues.append(f"EXTRA_NO_DB: {code} (db qty={db_procs[code]})")
                                    async with cstats_lock:
                                        cstats["extra_no_db"] += 1
                                    record_ok = False
                                else:
                                    # Both exist, compare qty
                                    if site_procs[code] != db_procs[code]:
                                        record_issues.append(f"QTD_ERRADA: {code} (site={site_procs[code]}, db={db_procs[code]})")
                                        async with cstats_lock:
                                            cstats["qtd_errada"] += 1
                                        record_ok = False

                            if record_ok:
                                async with cstats_lock:
                                    cstats["ok"] += 1
                                # Only log every 50th OK to reduce noise
                                if (idx + 1) % 50 == 0:
                                    await log(f"  {label} OK: pront={record_id} ({len(site_procs)} procs)")
                            else:
                                async with cstats_lock:
                                    cstats["mismatch"] += 1
                                disc = {
                                    "comp": comp,
                                    "prontuario": record_id,
                                    "data_ent": data_ent,
                                    "data_sai": data_sai,
                                    "id_aih": id_aih,
                                    "tipo": "DIVERGENCIA",
                                    "issues": record_issues,
                                    "site_procs": site_procs,
                                    "db_procs": db_procs,
                                }
                                all_discrepancies.append(disc)
                                issues_str = " | ".join(record_issues)
                                await log(f"  {label} DIVERGENCIA: pront={record_id} | {issues_str}")

                        except Exception as e:
                            async with cstats_lock:
                                cstats["errors"] += 1
                            await log(f"  {label} ERRO: pront={record_id} - {e}")
                        finally:
                            await detail_page.close()

                # Process all records with concurrency
                if tasks:
                    start_time = datetime.now()
                    await asyncio.gather(*[validate_record(t) for t in tasks])
                    elapsed = (datetime.now() - start_time).total_seconds()
                    await log(f"\n  Tempo: {elapsed:.0f}s ({elapsed/max(len(tasks),1):.1f}s/registro)")

                # Per-competencia summary
                await log(f"\n  --- Resumo {comp_key} ---")
                await log(f"  Verificados:          {cstats['checked']}")
                await log(f"  OK (identicos):       {cstats['ok']}")
                await log(f"  Com divergencia:      {cstats['mismatch']}")
                await log(f"  Ausentes no banco:    {cstats['missing_in_db']}")
                await log(f"  Procs faltando no DB: {cstats['falta_no_db']}")
                await log(f"  Procs extras no DB:   {cstats['extra_no_db']}")
                await log(f"  Qtd errada:           {cstats['qtd_errada']}")
                await log(f"  Erros:                {cstats['errors']}")

                # Accumulate global stats
                global_stats["total_checked"] += cstats["checked"]
                global_stats["total_ok"] += cstats["ok"]
                global_stats["total_mismatch"] += cstats["mismatch"]
                global_stats["total_missing_in_db"] += cstats["missing_in_db"]
                global_stats["total_falta_no_db"] += cstats["falta_no_db"]
                global_stats["total_extra_no_db"] += cstats["extra_no_db"]
                global_stats["total_qtd_errada"] += cstats["qtd_errada"]
                global_stats["total_errors"] += cstats["errors"]

        except Exception as e:
            await log(f"\nERRO CRITICO: {e}")
            import traceback
            await log(traceback.format_exc())
        finally:
            await browser.close()

    conn.close()

    # ── Final summary ──
    await log(f"\n\n{'='*70}")
    await log("RESUMO GERAL DA VALIDACAO")
    await log(f"{'='*70}")
    await log(f"Total verificados:      {global_stats['total_checked']}")
    await log(f"OK (identicos):         {global_stats['total_ok']}")
    await log(f"Com divergencia:        {global_stats['total_mismatch']}")
    await log(f"Ausentes no banco:      {global_stats['total_missing_in_db']}")
    await log(f"Procs faltando no DB:   {global_stats['total_falta_no_db']}")
    await log(f"Procs extras no DB:     {global_stats['total_extra_no_db']}")
    await log(f"Qtd errada:             {global_stats['total_qtd_errada']}")
    await log(f"Erros:                  {global_stats['total_errors']}")

    # Summary table per competencia
    await log(f"\n{'='*70}")
    await log("TABELA POR COMPETENCIA")
    await log(f"{'='*70}")
    header = f"{'Comp':<10} {'Verif':>6} {'OK':>6} {'Diverg':>7} {'Ausente':>8} {'Falta':>6} {'Extra':>6} {'QtdErr':>7} {'Erros':>6}"
    await log(header)
    await log("-" * len(header))

    for comp_key in sorted(comp_stats.keys(), key=lambda x: x.split("/")[1] + x.split("/")[0]):
        cs = comp_stats[comp_key]
        line = (
            f"{comp_key:<10} "
            f"{cs['checked']:>6} "
            f"{cs['ok']:>6} "
            f"{cs['mismatch']:>7} "
            f"{cs['missing_in_db']:>8} "
            f"{cs['falta_no_db']:>6} "
            f"{cs['extra_no_db']:>6} "
            f"{cs['qtd_errada']:>7} "
            f"{cs['errors']:>6}"
        )
        await log(line)

    # Detailed discrepancies at the end of the log
    if all_discrepancies:
        await log(f"\n\n{'='*70}")
        await log(f"DETALHAMENTO DAS DIVERGENCIAS ({len(all_discrepancies)} registros)")
        await log(f"{'='*70}")

        for i, disc in enumerate(all_discrepancies, 1):
            await log(f"\n--- Divergencia #{i} ---")
            await log(f"  Competencia: {disc['comp']}")
            await log(f"  Prontuario:  {disc['prontuario']}")
            await log(f"  Data Ent:    {disc['data_ent']}")
            await log(f"  Data Sai:    {disc['data_sai']}")
            await log(f"  Tipo:        {disc['tipo']}")

            if disc["tipo"] == "REGISTRO_AUSENTE_NO_DB":
                await log(f"  Detalhe:     {disc['detalhe']}")
                if disc["site_procs"]:
                    await log(f"  Procs no site:")
                    for code, qty in sorted(disc["site_procs"].items()):
                        await log(f"    {code}  qty={qty}")
            else:
                if "id_aih" in disc:
                    await log(f"  ID AIH:      {disc['id_aih']}")
                for issue in disc.get("issues", []):
                    await log(f"  -> {issue}")
                await log(f"  Procs SITE: {dict(sorted(disc['site_procs'].items()))}")
                await log(f"  Procs DB:   {dict(sorted(disc['db_procs'].items()))}")

    await log(f"\nValidacao finalizada em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    await log(f"Log salvo em: {log_path}")

    log_file.close()
    print(f"\nLog salvo em: {log_path}")


def main():
    parser = argparse.ArgumentParser(description="Valida procedimentos do site vs banco de dados")
    parser.add_argument("--comp", type=str, default=None,
                        help="Competencia unica para validar (ex: 06/2025)")
    parser.add_argument("--concurrent", type=int, default=5,
                        help="Numero de abas simultaneas (padrao: 5)")
    args = parser.parse_args()

    asyncio.run(run_validator(comp_filter=args.comp, max_concurrent=args.concurrent))


if __name__ == "__main__":
    main()
