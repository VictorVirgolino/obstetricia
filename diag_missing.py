"""
Diagnostico: por que 06/2025 tem 931 links no site mas menos no banco?
Esse script faz login, extrai todos os IDs do site, compara com o banco,
e identifica exatamente quais estao faltando e por que.
"""
import asyncio
from playwright.async_api import async_playwright
import db_manager
import re
import sqlite3

LOGIN = "ItaloCunha"
PASSWORD = "10208535497"
LOGIN_URL = "http://177.10.203.220/projetoisea/PAGINA%20DE%20LOGIN.php"
REPORT_URL = "http://177.10.203.220/projetoisea/relasisaih.php?operacao=R"
BASE_URL = "http://177.10.203.220/projetoisea/"

MONTH = "06"
YEAR = "2025"
COMPETENCIA = f"{MONTH}/{YEAR}"


def get_all_db_prontuarios():
    conn = sqlite3.connect("saude_real.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT prontuario, id_aih, cns_paciente FROM aih_records WHERE competencia = ?",
        (COMPETENCIA,)
    )
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: {'id_aih': row[1], 'cns': row[2]} for row in rows}


async def run_diag():
    db_manager.create_tables()
    db_manager.migrate_db()

    # 1. Get all prontuarios from DB
    db_records = get_all_db_prontuarios()
    print(f"=== DIAGNOSTICO {COMPETENCIA} ===\n")
    print(f"Prontuarios no banco: {len(db_records)}")

    # Check for duplicates in DB
    conn = sqlite3.connect("saude_real.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT prontuario, COUNT(*) as cnt
        FROM aih_records WHERE competencia = ?
        GROUP BY prontuario HAVING cnt > 1
    """, (COMPETENCIA,))
    dupes = cursor.fetchall()
    if dupes:
        print(f"\nPRONTUARIOS DUPLICADOS NO BANCO: {len(dupes)}")
        for d in dupes:
            print(f"  {d[0]}: {d[1]}x")
    else:
        print("Sem duplicatas de prontuario no banco.")

    # Check id_aih collisions
    cursor.execute("""
        SELECT id_aih, GROUP_CONCAT(prontuario) as prontuarios, COUNT(*) as cnt
        FROM aih_records WHERE competencia = ?
        GROUP BY id_aih HAVING cnt > 1
    """, (COMPETENCIA,))
    aih_dupes = cursor.fetchall()
    if aih_dupes:
        print(f"\nid_aih COMPARTILHADO entre prontuarios: {len(aih_dupes)}")
        for d in aih_dupes[:20]:
            print(f"  id_aih={d[0]}: prontuarios=[{d[1]}] ({d[2]}x)")
    else:
        print("Sem id_aih compartilhados.")

    # Check CNS collisions (same patient, multiple prontuarios)
    cursor.execute("""
        SELECT cns_paciente, GROUP_CONCAT(prontuario) as prontuarios, COUNT(*) as cnt
        FROM aih_records WHERE competencia = ?
        GROUP BY cns_paciente HAVING cnt > 1
        ORDER BY cnt DESC
        LIMIT 20
    """, (COMPETENCIA,))
    cns_dupes = cursor.fetchall()
    if cns_dupes:
        print(f"\nMesmo CNS com multiplos prontuarios: {len(cns_dupes)} pacientes")
        for d in cns_dupes[:10]:
            print(f"  CNS={d[0]}: prontuarios=[{d[1]}] ({d[2]}x)")

    conn.close()

    # 2. Login and get all IDs from the site
    print(f"\n--- Buscando IDs no site ---")
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
            print("Login OK")

            await page.goto(REPORT_URL, wait_until="networkidle")
            await page.wait_for_selector('input[name="comp"]')
            await page.fill('input[name="comp"]', MONTH)
            await page.fill('input[name="compa"]', YEAR)
            await page.click('input[name="buscar"]')
            await page.wait_for_selector('table', timeout=300000)

            # Extract all hrefs
            all_hrefs = await page.evaluate("""() => {
                const anchors = document.querySelectorAll('a[href*="baixaaihre.php"]');
                return Array.from(anchors).map(a => a.getAttribute('href') || '');
            }""")
            print(f"Links no site: {len(all_hrefs)}")

            # Parse all IDs from site
            site_ids = []
            no_contar = []
            for href in all_hrefs:
                m = re.search(r"contar=([^&']+)", href)
                if m:
                    site_ids.append(m.group(1))
                else:
                    no_contar.append(href[:100])

            print(f"IDs extraidos do site: {len(site_ids)}")
            if no_contar:
                print(f"Links sem contar=: {len(no_contar)}")

            # Check for duplicate IDs on the site
            from collections import Counter
            id_counts = Counter(site_ids)
            site_dupes = {k: v for k, v in id_counts.items() if v > 1}
            if site_dupes:
                print(f"\nIDs DUPLICADOS NO SITE: {len(site_dupes)}")
                for pid, cnt in sorted(site_dupes.items(), key=lambda x: -x[1])[:20]:
                    in_db = "SIM" if pid in db_records else "NAO"
                    print(f"  {pid}: aparece {cnt}x no site | no banco: {in_db}")
                total_duped_extra = sum(v - 1 for v in site_dupes.values())
                print(f"  Total de entradas extras por duplicatas: {total_duped_extra}")
            else:
                print("Sem IDs duplicados no site.")

            unique_site_ids = set(site_ids)
            db_ids = set(db_records.keys())

            # 3. Compare
            missing_from_db = unique_site_ids - db_ids
            extra_in_db = db_ids - unique_site_ids

            print(f"\n=== COMPARACAO ===")
            print(f"IDs unicos no site:    {len(unique_site_ids)}")
            print(f"IDs unicos no banco:   {len(db_ids)}")
            print(f"Faltam no banco:       {len(missing_from_db)}")
            print(f"Extras no banco:       {len(extra_in_db)}")

            if missing_from_db:
                print(f"\n--- PRONTUARIOS FALTANDO NO BANCO ({len(missing_from_db)}) ---")
                for pid in sorted(missing_from_db):
                    print(f"  {pid}")

            if extra_in_db:
                print(f"\n--- PRONTUARIOS NO BANCO MAS NAO NO SITE ({len(extra_in_db)}) ---")
                for pid in sorted(extra_in_db):
                    print(f"  {pid}")

            # 4. For missing ones, try to understand why check_aih_exists said they exist
            if missing_from_db:
                print(f"\n--- INVESTIGANDO check_aih_exists PARA OS FALTANTES ---")
                for pid in sorted(missing_from_db)[:10]:
                    exists = db_manager.check_aih_exists(pid, COMPETENCIA)
                    print(f"  check_aih_exists('{pid}', '{COMPETENCIA}') = {exists}")

                    # Check if it exists in another competencia
                    conn2 = sqlite3.connect("saude_real.db")
                    c2 = conn2.cursor()
                    c2.execute("SELECT competencia FROM aih_records WHERE prontuario = ?", (pid,))
                    other = c2.fetchall()
                    if other:
                        comps = [r[0] for r in other]
                        print(f"    Existe em outras competencias: {comps}")
                    else:
                        print(f"    NAO existe em nenhuma competencia!")
                    conn2.close()

            # 5. Summary
            print(f"\n=== RESUMO FINAL ===")
            print(f"Site: {len(all_hrefs)} links, {len(unique_site_ids)} IDs unicos, {len(site_dupes)} IDs duplicados")
            print(f"Banco: {len(db_ids)} prontuarios")
            print(f"Faltam: {len(missing_from_db)}")
            if site_dupes:
                print(f"\nA diferenca provavelmente se deve a {len(site_dupes)} IDs que aparecem")
                print(f"mais de uma vez no site ({total_duped_extra} entradas extras).")
                print(f"Se descontarmos duplicatas do site: {len(unique_site_ids)} unicos vs {len(db_ids)} no banco = faltam {len(missing_from_db)}")

        except Exception as e:
            print(f"Erro: {e}")
            await page.screenshot(path="diag_missing_error.png")
        finally:
            await browser.close()

    # Save report
    print("\nDiagnostico concluido.")


if __name__ == "__main__":
    asyncio.run(run_diag())
