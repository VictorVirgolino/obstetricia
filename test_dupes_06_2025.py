"""
Teste 06/2025 - Investiga todos os duplicados e diferenças entre site e banco.
Gera log detalhado: test_dupes_06_2025.log
"""
import asyncio
from playwright.async_api import async_playwright
import sqlite3
import re
from datetime import datetime
from collections import defaultdict

LOGIN = "ItaloCunha"
PASSWORD = "10208535497"
LOGIN_URL = "http://177.10.203.220/projetoisea/PAGINA%20DE%20LOGIN.php"
REPORT_URL = "http://177.10.203.220/projetoisea/relasisaih.php?operacao=R"

MONTH = "06"
YEAR = "2025"
COMPETENCIA = f"{MONTH}/{YEAR}"
LOG_PATH = "test_dupes_06_2025.log"


def get_db_data():
    """Pega todos os dados do banco para 06/2025."""
    conn = sqlite3.connect("saude_real.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.prontuario, r.id_aih, r.cns_paciente, r.data_ent, r.data_sai,
               p.nome, p.cidade
        FROM aih_records r
        LEFT JOIN pacientes p ON r.cns_paciente = p.cns
        WHERE r.competencia = ?
        ORDER BY r.prontuario
    """, (COMPETENCIA,))
    rows = cursor.fetchall()
    conn.close()

    result = {}
    for row in rows:
        result[row[0]] = {
            'prontuario': row[0],
            'id_aih': row[1],
            'cns': row[2],
            'data_ent': row[3],
            'data_sai': row[4],
            'nome': row[5] or '',
            'cidade': row[6] or '',
        }
    return result


async def run_test():
    log_file = open(LOG_PATH, "w", encoding="utf-8")

    def log(msg=""):
        print(msg)
        log_file.write(msg + "\n")
        log_file.flush()

    log(f"TESTE DUPLICADOS - {COMPETENCIA}")
    log(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 70)

    # 1. Dados do banco
    db_data = get_db_data()
    log(f"\nProntuarios no banco: {len(db_data)}")

    # 2. Buscar links no site
    log("\nConectando ao site...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
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
            log("Login OK")

            await page.goto(REPORT_URL, wait_until="networkidle")
            await page.wait_for_selector('input[name="comp"]')
            await page.fill('input[name="comp"]', MONTH)
            await page.fill('input[name="compa"]', YEAR)
            await page.click('input[name="buscar"]')
            await page.wait_for_selector('table', timeout=300000)

            # Extrair TODOS os hrefs com texto visivel da linha
            site_data = await page.evaluate("""() => {
                const results = [];
                const anchors = document.querySelectorAll('a[href*="baixaaihre.php"]');
                anchors.forEach((a, idx) => {
                    const href = a.getAttribute('href') || '';
                    // Pegar texto da linha (tr pai)
                    const tr = a.closest('tr');
                    const rowText = tr ? tr.innerText.trim() : '';
                    results.push({ href, rowText, index: idx + 1 });
                });
                return results;
            }""")

            log(f"Links encontrados no site: {len(site_data)}")

        except Exception as e:
            log(f"ERRO ao buscar site: {e}")
            await page.screenshot(path="test_dupes_error.png")
            await browser.close()
            log_file.close()
            return
        finally:
            await browser.close()

    # 3. Parsear todos os links
    all_entries = []
    no_contar = []
    for item in site_data:
        href = item['href']
        contar_match = re.search(r"contar=([^&']+)", href)
        ent_match = re.search(r"dataent=([^&']+)", href)
        sai_match = re.search(r"datasai=([^&']+)", href)

        if not contar_match:
            no_contar.append(item)
            continue

        all_entries.append({
            'index': item['index'],
            'prontuario': contar_match.group(1),
            'data_ent': ent_match.group(1) if ent_match else '',
            'data_sai': sai_match.group(1) if sai_match else '',
            'href': href,
            'row_text': item['rowText'][:200],
        })

    # 4. Agrupar por prontuario
    by_prontuario = defaultdict(list)
    for entry in all_entries:
        by_prontuario[entry['prontuario']].append(entry)

    unique_ids = set(by_prontuario.keys())
    db_ids = set(db_data.keys())
    duplicados = {k: v for k, v in by_prontuario.items() if len(v) > 1}

    # 5. Log de todos os prontuarios (marcando duplicados e status no banco)
    log(f"\n{'='*70}")
    log("LISTAGEM COMPLETA DE TODOS OS LINKS DO SITE")
    log(f"{'='*70}")

    for entry in all_entries:
        pid = entry['prontuario']
        is_dupe = len(by_prontuario[pid]) > 1
        in_db = pid in db_data

        status_parts = []
        if in_db:
            status_parts.append("BANCO:SIM")
        else:
            status_parts.append("BANCO:NAO")
        if is_dupe:
            status_parts.append(f"DUPE:{len(by_prontuario[pid])}x")
        status = " | ".join(status_parts)

        log(f"  [{entry['index']:>3}/931] Pront={pid} | ent={entry['data_ent']} | sai={entry['data_sai']} | {status}")

    # 6. Detalhes dos duplicados
    log(f"\n{'='*70}")
    log(f"DUPLICADOS NO SITE: {len(duplicados)} prontuarios ({sum(len(v) for v in duplicados.values())} links)")
    log(f"{'='*70}")

    for pid, entries in sorted(duplicados.items()):
        log(f"\n  PRONTUARIO: {pid}")
        in_db = db_data.get(pid)
        if in_db:
            log(f"    NO BANCO: SIM - nome={in_db['nome']} | id_aih={in_db['id_aih']} | ent={in_db['data_ent']} | sai={in_db['data_sai']}")
        else:
            log(f"    NO BANCO: NAO")

        for j, entry in enumerate(entries):
            log(f"    Link {j+1} (pos {entry['index']}): ent={entry['data_ent']} | sai={entry['data_sai']}")
            log(f"      href: {entry['href'][:150]}")
            log(f"      linha: {entry['row_text'][:150]}")

        # Comparar se os duplicados tem dados diferentes
        ents = set(e['data_ent'] for e in entries)
        sais = set(e['data_sai'] for e in entries)
        if len(ents) > 1 or len(sais) > 1:
            log(f"    >> DADOS DIFERENTES entre links: ent={ents} sai={sais}")
        else:
            log(f"    >> Links identicos (mesmo ent/sai)")

    # 7. Prontuarios faltando no banco
    missing = unique_ids - db_ids
    extra = db_ids - unique_ids

    log(f"\n{'='*70}")
    log("COMPARACAO SITE vs BANCO")
    log(f"{'='*70}")
    log(f"  Links totais no site:    {len(all_entries)}")
    log(f"  Sem contar= no href:     {len(no_contar)}")
    log(f"  IDs unicos no site:      {len(unique_ids)}")
    log(f"  Prontuarios no banco:    {len(db_ids)}")
    log(f"  Duplicados no site:      {len(duplicados)} ({sum(len(v)-1 for v in duplicados.values())} links extras)")
    log(f"  Faltam no banco:         {len(missing)}")
    log(f"  Extras no banco:         {len(extra)}")

    if missing:
        log(f"\n  FALTANDO NO BANCO ({len(missing)}):")
        for pid in sorted(missing):
            entries = by_prontuario[pid]
            log(f"    {pid} - {len(entries)} link(s) no site | ent={entries[0]['data_ent']} sai={entries[0]['data_sai']}")

    if extra:
        log(f"\n  NO BANCO MAS NAO NO SITE ({len(extra)}):")
        for pid in sorted(extra):
            rec = db_data[pid]
            log(f"    {pid} - nome={rec['nome']} | ent={rec['data_ent']} sai={rec['data_sai']}")

    if not missing and not extra:
        log(f"\n  BANCO COMPLETO: todos os {len(unique_ids)} prontuarios unicos estao no banco.")

    # 8. Resumo final
    log(f"\n{'='*70}")
    log("RESUMO FINAL")
    log(f"{'='*70}")
    log(f"  931 links no site = {len(unique_ids)} prontuarios unicos + {sum(len(v)-1 for v in duplicados.values())} duplicatas")
    log(f"  {len(db_ids)} prontuarios no banco")
    if len(db_ids) == len(unique_ids):
        log(f"  STATUS: OK - banco completo!")
    else:
        log(f"  STATUS: INCOMPLETO - faltam {len(unique_ids) - len(db_ids)}")

    log_file.close()
    print(f"\nLog salvo em: {LOG_PATH}")


if __name__ == "__main__":
    asyncio.run(run_test())
