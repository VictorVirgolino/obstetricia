"""
Teste diagnóstico: Prontuário 368677 (RN de Cleane Luciely Silva dos Santos)
Competência: 06/2025

Extrai os procedimentos direto do site do hospital e compara com o banco.
O objetivo é mostrar que o banco tem MAIS procedimentos do que deveria,
porque pacientes SEM AIH (id_aih='') compartilham o mesmo pool de procedimentos.
"""

import asyncio
import sqlite3
import sys
import os
import re
from playwright.async_api import async_playwright

sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = "saude_real.db"
PRONTUARIO = "368677"
COMPETENCIA = "06/2025"
MONTH, YEAR = "06", "2025"

LOGIN = "ItaloCunha"
PASSWORD = "10208535497"
LOGIN_URL = "http://177.10.203.220/projetoisea/PAGINA%20DE%20LOGIN.php"
REPORT_URL = "http://177.10.203.220/projetoisea/relasisaih.php?operacao=R"
BASE_URL = "http://177.10.203.220/projetoisea/"


async def safe_get_value(page, selector, default=""):
    try:
        el = await page.query_selector(selector)
        if el:
            tag = await el.evaluate("el => el.tagName")
            if tag == "SELECT":
                return await el.evaluate("el => el.options[el.selectedIndex]?.text || ''")
            return await el.input_value()
        return default
    except:
        return default


async def extract_from_site():
    """Acessa o site do hospital e extrai os procedimentos do prontuário 368677."""
    print("=" * 70)
    print(f"EXTRAINDO DO SITE - Prontuario {PRONTUARIO} | Comp {COMPETENCIA}")
    print("=" * 70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Login
        print("\n[1] Fazendo login no sistema...")
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
        print("  Login OK!")

        # Navegar para a competência
        print(f"\n[2] Buscando competencia {MONTH}/{YEAR}...")
        await page.goto(REPORT_URL, wait_until="networkidle")
        await page.wait_for_selector('input[name="comp"]')
        await page.fill('input[name="comp"]', MONTH)
        await page.fill('input[name="compa"]', YEAR)
        await page.click('input[name="buscar"]')
        await page.wait_for_selector('table', timeout=300000)
        print("  Resultados carregados!")

        # Encontrar link do prontuario 368677
        print(f"\n[3] Procurando link do prontuario {PRONTUARIO}...")
        links_data = await page.evaluate("""() => {
            const results = [];
            const anchors = document.querySelectorAll('a[href*="baixaaihre.php"]');
            anchors.forEach(a => {
                const href = a.getAttribute('href') || '';
                results.push(href);
            });
            return results;
        }""")

        target_links = [h for h in links_data if f"contar={PRONTUARIO}" in h]
        print(f"  Links encontrados para {PRONTUARIO}: {len(target_links)}")

        if not target_links:
            print(f"  ERRO: Prontuario {PRONTUARIO} nao encontrado na competencia {COMPETENCIA}!")
            await browser.close()
            return None, None

        # Extrair dados de cada ocorrencia do prontuario
        all_site_procs = []
        aih_info = None

        for link_idx, href in enumerate(target_links):
            print(f"\n[4.{link_idx+1}] Abrindo detalhe (ocorrencia {link_idx+1}/{len(target_links)})...")

            ent_match = re.search(r"dataent=([^&']+)", href)
            sai_match = re.search(r"datasai=([^&']+)", href)
            data_ent_url = ent_match.group(1) if ent_match else ""
            data_sai_url = sai_match.group(1) if sai_match else ""

            url_match = re.search(r"location\.href='([^']+)'", href)
            if url_match:
                detail_path = url_match.group(1)
            else:
                detail_path = f"baixaaihre.php?contar={PRONTUARIO}&datasai={data_sai_url}&dataent={data_ent_url}"

            detail_url = f"{BASE_URL}{detail_path}"
            detail_page = await context.new_page()

            try:
                await detail_page.goto(detail_url, wait_until="networkidle", timeout=60000)
                await asyncio.sleep(1)

                # Dados do paciente/AIH
                p_name = await safe_get_value(detail_page, 'input#AIH_PAC_NOME')
                p_cns = await safe_get_value(detail_page, 'input#cns')
                id_aih = await safe_get_value(detail_page, 'input#AIH_NUM_AIH', '')
                data_ent_page = await safe_get_value(detail_page, 'input#AIH_DT_INT')
                data_sai_page = await safe_get_value(detail_page, 'input#AIH_DT_SAI')

                print(f"  Paciente: {p_name.strip()}")
                print(f"  CNS: {p_cns.strip()}")
                print(f"  AIH: '{id_aih.strip()}' {'(VAZIO - SEM AIH)' if not id_aih.strip() else ''}")
                print(f"  Entrada: {data_ent_url or data_ent_page}")
                print(f"  Saida:   {data_sai_url or data_sai_page}")

                aih_info = {
                    'id_aih': id_aih.strip(),
                    'data_ent': data_ent_url or data_ent_page,
                    'data_sai': data_sai_url or data_sai_page,
                }

                # Extrair procedimentos (mesma logica do scraper)
                procs_raw = await detail_page.evaluate("""() => {
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
                }""")

                print(f"\n  Procedimentos encontrados no site: {len(procs_raw)}")
                print(f"  {'Codigo':<12} {'Qtd':>4}  {'Descricao'}")
                print(f"  {'-'*12} {'-'*4}  {'-'*45}")
                for proc in procs_raw:
                    qty = int(proc['qty']) if proc['qty'].isdigit() else 1
                    all_site_procs.append({
                        'code': proc['code'],
                        'desc': proc.get('desc', ''),
                        'qty': qty,
                        'cbo': proc['cbo'],
                        'cnes': proc['cnes'],
                    })
                    print(f"  {proc['code']:<12} {qty:>4}  {proc.get('desc', '')[:45]}")

            finally:
                await detail_page.close()

        await browser.close()
        return aih_info, all_site_procs


def compare_with_db(aih_info, site_procs):
    """Compara procedimentos do site com os do banco de dados."""
    print("\n" + "=" * 70)
    print("COMPARACAO: SITE vs BANCO DE DADOS")
    print("=" * 70)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Buscar o id_aih usado no banco para este prontuario
    aih_record = conn.execute(
        "SELECT * FROM aih_records WHERE prontuario = ? AND competencia = ?",
        (PRONTUARIO, COMPETENCIA),
    ).fetchone()

    if not aih_record:
        print("  ERRO: Registro AIH nao encontrado no banco!")
        conn.close()
        return False

    id_aih_db = aih_record['id_aih']
    print(f"\n  id_aih no banco: '{id_aih_db}'")

    # Buscar TODOS os procedimentos vinculados a esse id_aih
    db_procs = conn.execute(
        "SELECT * FROM aih_procedimentos WHERE id_aih = ?",
        (id_aih_db,)
    ).fetchall()

    # Quantos AIH records compartilham esse id_aih?
    shared_count = conn.execute(
        "SELECT COUNT(*) as cnt FROM aih_records WHERE id_aih = ?",
        (id_aih_db,)
    ).fetchone()['cnt']

    print(f"  Registros AIH compartilhando id_aih='{id_aih_db}': {shared_count}")

    # --- Resumo do site ---
    print(f"\n  SITE DO HOSPITAL:")
    print(f"  Total de procedimentos: {len(site_procs)}")
    site_total_qty = sum(p['qty'] for p in site_procs)
    print(f"  Soma das quantidades:   {site_total_qty}")

    # Buscar custos do SIGTAP para calcular valor total esperado
    site_total_custo = 0.0
    for sp in site_procs:
        custo_row = conn.execute("""
            SELECT t_hosp, t_amb FROM sigtap_metadata
            WHERE proc_cod = ? AND competencia = ?
        """, (sp['code'], COMPETENCIA)).fetchone()
        if custo_row:
            custo = custo_row['t_hosp'] if custo_row['t_hosp'] and custo_row['t_hosp'] > 0 else (custo_row['t_amb'] or 0)
            site_total_custo += custo * sp['qty']

    print(f"  Custo total estimado (SIGTAP): R$ {site_total_custo:,.2f}")

    # --- Resumo do banco ---
    print(f"\n  BANCO DE DADOS (id_aih='{id_aih_db}'):")
    print(f"  Total de procedimentos: {len(db_procs)}")
    db_total_qty = sum(p['qtd'] for p in db_procs)
    print(f"  Soma das quantidades:   {db_total_qty}")
    db_total_custo = sum(p['custo_total'] or 0 for p in db_procs)
    print(f"  Custo total no banco:   R$ {db_total_custo:,.2f}")

    # --- Comparacao detalhada ---
    print(f"\n  {'='*66}")
    print(f"  DIFERENCA:")
    print(f"  {'='*66}")

    diff_procs = len(db_procs) - len(site_procs)
    diff_qty = db_total_qty - site_total_qty
    diff_custo = db_total_custo - site_total_custo

    print(f"  Procedimentos a mais no banco: {diff_procs} ({len(db_procs)} no DB vs {len(site_procs)} no site)")
    print(f"  Quantidade total a mais:       {diff_qty} ({db_total_qty} no DB vs {site_total_qty} no site)")
    print(f"  Custo a mais no banco:         R$ {diff_custo:,.2f}")

    # --- Tabela comparativa proc a proc ---
    site_map = {}
    for sp in site_procs:
        site_map[sp['code']] = sp

    db_map = {}
    for dp in db_procs:
        db_map[dp['proc_cod']] = {'qtd': dp['qtd'], 'custo_total': dp['custo_total'] or 0}

    all_codes = sorted(set(list(site_map.keys()) + list(db_map.keys())))

    print(f"\n  {'Codigo':<12} {'Site':>6} {'DB':>6} {'Diff':>6}  {'Status'}")
    print(f"  {'-'*12} {'-'*6} {'-'*6} {'-'*6}  {'-'*25}")

    only_in_db = 0
    only_in_site = 0
    qty_mismatch = 0
    ok_count = 0

    for code in all_codes:
        in_site = code in site_map
        in_db = code in db_map
        site_qty = site_map[code]['qty'] if in_site else 0
        db_qty = db_map[code]['qtd'] if in_db else 0
        diff = db_qty - site_qty

        if in_site and in_db and site_qty == db_qty:
            status = "OK"
            ok_count += 1
        elif in_db and not in_site:
            status = "EXTRA NO DB (nao deveria existir)"
            only_in_db += 1
        elif in_site and not in_db:
            status = "FALTA NO DB"
            only_in_site += 1
        else:
            status = f"QTD ERRADA (site={site_qty})"
            qty_mismatch += 1

        print(f"  {code:<12} {site_qty:>6} {db_qty:>6} {diff:>+6}  {status}")

    # --- Resumo final ---
    print(f"\n  {'='*66}")
    print(f"  RESUMO FINAL")
    print(f"  {'='*66}")
    print(f"  Procedimentos corretos:               {ok_count}")
    print(f"  Procedimentos com quantidade errada:   {qty_mismatch}")
    print(f"  Procedimentos extras no DB:            {only_in_db}")
    print(f"  Procedimentos faltando no DB:          {only_in_site}")
    print(f"")
    print(f"  Custo total segundo o SITE:    R$ {site_total_custo:,.2f}")
    print(f"  Custo total segundo o BANCO:   R$ {db_total_custo:,.2f}")
    print(f"  Diferenca (banco - site):      R$ {diff_custo:,.2f}")

    if shared_count > 1:
        print(f"\n  CAUSA RAIZ:")
        print(f"  O id_aih esta vazio ('') e {shared_count} pacientes SEM AIH")
        print(f"  compartilham o mesmo pool de {len(db_procs)} procedimentos.")
        print(f"  Pacientes RN (recem-nascidos) nao tem AIH ainda.")
        print(f"  O banco tem {diff_procs} procedimentos a mais que pertencem")
        print(f"  a OUTROS pacientes, inflando os valores deste prontuario.")

    conn.close()

    has_errors = (only_in_db > 0 or only_in_site > 0 or qty_mismatch > 0)
    return not has_errors


async def main():
    aih_info, site_procs = await extract_from_site()
    if site_procs is None:
        print("\nFalha ao extrair dados do site.")
        sys.exit(1)

    ok = compare_with_db(aih_info, site_procs)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
