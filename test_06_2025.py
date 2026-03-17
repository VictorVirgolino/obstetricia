import asyncio
from playwright.async_api import async_playwright
import db_manager
import re

LOGIN = "ItaloCunha"
PASSWORD = "10208535497"
LOGIN_URL = "http://177.10.203.220/projetoisea/PAGINA%20DE%20LOGIN.php"
REPORT_URL = "http://177.10.203.220/projetoisea/relasisaih.php?operacao=R"
BASE_URL = "http://177.10.203.220/projetoisea/"

MONTH = "06"
YEAR = "2025"

# Tracking
found_ids = []
skipped_exists = []
skipped_no_contar = []
skipped_no_name = []
failed_records = []  # (record_id, error_message)
saved_ok = []


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


async def extract_and_save(detail_page, record_id, data_ent_url, data_sai_url):
    # Wait for page to fully load
    await detail_page.wait_for_load_state("networkidle")
    await asyncio.sleep(2)

    # 1. Patient Data
    p_cns = await safe_get_value(detail_page, 'input#cns')
    if not p_cns:
        p_cns = await safe_get_value(detail_page, 'input[name="cns"]')

    p_name = await safe_get_value(detail_page, 'input#AIH_PAC_NOME')
    if not p_name:
        p_name = await safe_get_value(detail_page, 'input[name="AIH_PAC_NOME"]')

    if not p_name:
        skipped_no_name.append(record_id)
        print(f"  SKIP (sem nome): {record_id}")
        return

    cidade = ""
    estado = ""
    try:
        cidade = await detail_page.evaluate(
            "() => { const el = document.querySelector('select#cidade'); return el ? el.options[el.selectedIndex]?.text || '' : ''; }"
        )
        estado = await safe_get_value(detail_page, 'input#AIH_PAC_UF')
        if not estado:
            estado = await detail_page.evaluate(
                "() => { const el = document.querySelector('select#estado'); return el ? el.options[el.selectedIndex]?.text || '' : ''; }"
            )
    except:
        pass

    patient_data = {
        'cns': p_cns.strip(),
        'nome': p_name.strip(),
        'dt_nasc': await safe_get_value(detail_page, 'input#AIH_PAC_DT_NASC'),
        'sexo': await safe_get_value(detail_page, 'select#AIH_PAC_SEXO'),
        'raca': await safe_get_value(detail_page, 'select#AIH_PAC_RACA_COR'),
        'nome_mae': await safe_get_value(detail_page, 'input#AIH_PAC_NOME_MAE'),
        'cidade': cidade.strip(),
        'estado': estado.strip()
    }
    db_manager.save_paciente(patient_data)

    # 2. AIH Record
    id_aih = await safe_get_value(detail_page, 'input#AIH_NUM_AIH', "")
    data_ent = await safe_get_value(detail_page, 'input#AIH_DT_INT')
    data_sai = await safe_get_value(detail_page, 'input#AIH_DT_SAI')
    if not data_ent:
        data_ent = data_ent_url
    if not data_sai:
        data_sai = data_sai_url

    # Generate synthetic id_aih when empty (e.g. RN patients without AIH)
    id_aih_clean = id_aih.strip()
    if not id_aih_clean:
        id_aih_clean = f"SEM_AIH_{record_id}_{data_ent}_{data_sai}"

    aih_data = {
        'id_aih': id_aih_clean,
        'prontuario': record_id,
        'cns_paciente': p_cns.strip(),
        'data_ent': data_ent,
        'data_sai': data_sai,
        'cid_principal': await safe_get_value(detail_page, 'select#AIH_CID_PRI'),
        'motivo_saida': await safe_get_value(detail_page, 'select#AIH_MOT_COB'),
        'medico_solic': await safe_get_value(detail_page, 'input#CADMED_NOME'),
        'medico_resp': await safe_get_value(detail_page, 'input#CADMED_NOME2'),
        'competencia': f"{MONTH}/{YEAR}",
        'data_atendimento': data_ent
    }
    db_manager.save_aih_record(aih_data)

    # 3. Procedures
    procs = await detail_page.evaluate("""() => {
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
                        const qty = tds[3]?.innerText?.trim();
                        const cbo = tds[5]?.innerText?.trim() || '';
                        const cnes = tds[6]?.innerText?.trim() || '';
                        if (code && code.match(/^[0-9]{10}$/)) {
                            rows.push({ code, qty, cbo, cnes });
                        }
                    }
                }
                break;
            }
        }
        return rows;
    }""")

    if not procs:
        main_proc = await safe_get_value(detail_page, 'input#AIH_PROC_REA')
        if main_proc and re.match(r'^\d{10}$', main_proc.strip()):
            db_manager.save_procedimento(id_aih_clean, main_proc.strip(), 1, "", "")
    else:
        for proc in procs:
            qty = int(proc['qty']) if proc['qty'].isdigit() else 1
            db_manager.save_procedimento(id_aih_clean, proc['code'], qty, proc['cbo'], proc['cnes'])

    saved_ok.append(record_id)
    print(f"  OK: {record_id} - {p_name.strip()} ({len(procs)} procs)")


async def run_test():
    db_manager.create_tables()
    db_manager.migrate_db()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # Login
            print("Fazendo login...")
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
            print("Login OK!")

            # Go to report page
            print(f"\nBuscando competencia {MONTH}/{YEAR}...")
            await page.goto(REPORT_URL, wait_until="networkidle")
            await page.wait_for_selector('input[name="comp"]')
            await page.fill('input[name="comp"]', MONTH)
            await page.fill('input[name="compa"]', YEAR)
            await page.click('input[name="buscar"]')

            try:
                await page.wait_for_selector('table', timeout=300000)
            except:
                print("Timeout ou sem resultados!")
                return

            # Extract ALL hrefs from results
            all_hrefs = await page.evaluate("""() => {
                const anchors = document.querySelectorAll('a[href*="baixaaihre.php"]');
                return Array.from(anchors).map(a => a.getAttribute('href') || '');
            }""")

            print(f"Total de links encontrados na pagina: {len(all_hrefs)}")

            # Also save the raw HTML of the page for debugging
            html_content = await page.content()
            # Count total rows in the table
            total_table_rows = await page.evaluate("""() => {
                const tables = document.querySelectorAll('table');
                let maxRows = 0;
                for (const t of tables) {
                    const rows = t.querySelectorAll('tr');
                    if (rows.length > maxRows) maxRows = rows.length;
                }
                return maxRows;
            }""")
            print(f"Total de linhas na maior tabela: {total_table_rows}")

            # Process each link
            for i, href in enumerate(all_hrefs):
                contar_match = re.search(r"contar=([^&']+)", href)
                ent_match = re.search(r"dataent=([^&']+)", href)
                sai_match = re.search(r"datasai=([^&']+)", href)

                if not contar_match:
                    skipped_no_contar.append(href[:100])
                    continue

                record_id = contar_match.group(1)
                data_ent_url = ent_match.group(1) if ent_match else ""
                data_sai_url = sai_match.group(1) if sai_match else ""

                found_ids.append(record_id)

                # Skip if already exists
                if db_manager.check_aih_exists(record_id, f"{MONTH}/{YEAR}"):
                    skipped_exists.append(record_id)
                    continue

                # Build URL
                url_match = re.search(r"location\.href='([^']+)'", href)
                if url_match:
                    detail_path = url_match.group(1)
                else:
                    detail_path = f"baixaaihre.php?contar={record_id}&datasai={data_sai_url}&dataent={data_ent_url}"

                detail_url = f"{BASE_URL}{detail_path}"

                print(f"[{i+1}/{len(all_hrefs)}] ", end="")
                detail_page = await context.new_page()
                try:
                    await detail_page.goto(detail_url, wait_until="networkidle", timeout=60000)
                    await extract_and_save(detail_page, record_id, data_ent_url, data_sai_url)
                except Exception as e:
                    error_msg = str(e)
                    failed_records.append((record_id, error_msg))
                    print(f"  ERRO: {record_id} - {error_msg[:100]}")
                finally:
                    await detail_page.close()

                if i % 10 == 0 and i > 0:
                    await asyncio.sleep(1)

        except Exception as e:
            print(f"Erro critico: {e}")
            await page.screenshot(path="test_06_error.png")
        finally:
            await browser.close()

    # ===== RELATORIO FINAL =====
    print("\n" + "=" * 60)
    print("RELATORIO FINAL - COMPETENCIA 06/2025")
    print("=" * 60)
    print(f"Links na pagina:           {len(all_hrefs)}")
    print(f"IDs extraidos (contar=):   {len(found_ids)}")
    print(f"Ja existiam no banco:      {len(skipped_exists)}")
    print(f"Salvos com sucesso:        {len(saved_ok)}")
    print(f"Sem nome (pulados):        {len(skipped_no_name)}")
    print(f"Sem contar= no href:       {len(skipped_no_contar)}")
    print(f"Erros ao carregar:         {len(failed_records)}")

    total_no_banco = len(skipped_exists) + len(saved_ok)
    esperado = 931
    faltando = esperado - total_no_banco
    print(f"\nTotal no banco agora:      {total_no_banco}")
    print(f"Esperado:                  {esperado}")
    print(f"Faltando:                  {faltando}")

    if skipped_no_name:
        print(f"\n--- PRONTUARIOS SEM NOME ({len(skipped_no_name)}) ---")
        for rid in skipped_no_name:
            print(f"  {rid}")

    if skipped_no_contar:
        print(f"\n--- HREFS SEM CONTAR= ({len(skipped_no_contar)}) ---")
        for h in skipped_no_contar:
            print(f"  {h}")

    if failed_records:
        print(f"\n--- PRONTUARIOS COM ERRO ({len(failed_records)}) ---")
        for rid, err in failed_records:
            print(f"  {rid}: {err[:150]}")

    # Save report to file
    with open("relatorio_06_2025.txt", "w", encoding="utf-8") as f:
        f.write(f"RELATORIO - COMPETENCIA 06/2025\n")
        f.write(f"Links na pagina: {len(all_hrefs)}\n")
        f.write(f"IDs extraidos: {len(found_ids)}\n")
        f.write(f"Ja existiam: {len(skipped_exists)}\n")
        f.write(f"Salvos OK: {len(saved_ok)}\n")
        f.write(f"Sem nome: {len(skipped_no_name)}\n")
        f.write(f"Sem contar: {len(skipped_no_contar)}\n")
        f.write(f"Erros: {len(failed_records)}\n")
        f.write(f"Total no banco: {total_no_banco}\n\n")

        if skipped_no_name:
            f.write("PRONTUARIOS SEM NOME:\n")
            for rid in skipped_no_name:
                f.write(f"  {rid}\n")

        if skipped_no_contar:
            f.write("\nHREFS SEM CONTAR=:\n")
            for h in skipped_no_contar:
                f.write(f"  {h}\n")

        if failed_records:
            f.write("\nPRONTUARIOS COM ERRO:\n")
            for rid, err in failed_records:
                f.write(f"  {rid}: {err}\n")

        # All found IDs for reference
        f.write(f"\nTODOS OS IDS ENCONTRADOS ({len(found_ids)}):\n")
        for rid in sorted(found_ids):
            f.write(f"  {rid}\n")

    print("\nRelatorio salvo em: relatorio_06_2025.txt")


if __name__ == "__main__":
    asyncio.run(run_test())
