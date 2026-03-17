import asyncio
from playwright.async_api import async_playwright
import db_manager
import re
from datetime import datetime

# Credentials
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


async def extract_record_data(detail_page, record_id, month, year, data_ent_url, data_sai_url, index_label="", log=None):
    """Extracts data from detail page. Returns (status, patient_data, aih_data, procs_list) or (status, None, None, None) on failure."""
    async def _log(msg):
        if log:
            if asyncio.iscoroutinefunction(log):
                await log(msg)
            else:
                log(msg)

    try:
        await detail_page.wait_for_load_state("networkidle")
        await asyncio.sleep(1)

        # 1. Patient Data
        p_cns = await safe_get_value(detail_page, 'input#cns')
        if not p_cns:
            p_cns = await safe_get_value(detail_page, 'input[name="cns"]')

        p_name = await safe_get_value(detail_page, 'input#AIH_PAC_NOME')
        if not p_name:
            p_name = await safe_get_value(detail_page, 'input[name="AIH_PAC_NOME"]')

        if not p_name:
            await _log(f"  {index_label}SEM NOME: {record_id}")
            return "no_name", None, None, None

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

        # 2. AIH Record Data
        id_aih = await safe_get_value(detail_page, 'input#AIH_NUM_AIH', f"P{record_id}")

        data_ent_page = await safe_get_value(detail_page, 'input#AIH_DT_INT')
        data_sai_page = await safe_get_value(detail_page, 'input#AIH_DT_SAI')

        # Use URL dates as canonical key (unique per link), page dates as supplementary
        data_ent = data_ent_url or data_ent_page
        data_sai = data_sai_url or data_sai_page

        aih_data = {
            'id_aih': id_aih.strip(),
            'prontuario': record_id,
            'cns_paciente': p_cns.strip(),
            'data_ent': data_ent,
            'data_sai': data_sai,
            'cid_principal': await safe_get_value(detail_page, 'select#AIH_CID_PRI'),
            'motivo_saida': await safe_get_value(detail_page, 'select#AIH_MOT_COB'),
            'medico_solic': await safe_get_value(detail_page, 'input#CADMED_NOME'),
            'medico_resp': await safe_get_value(detail_page, 'input#CADMED_NOME2'),
            'competencia': f"{month}/{year}",
            'data_atendimento': data_ent
        }

        # 3. Procedures
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

        procs_list = []
        if not procs_raw:
            main_proc = await safe_get_value(detail_page, 'input#AIH_PROC_REA')
            if main_proc and re.match(r'^\d{10}$', main_proc.strip()):
                procs_list.append({'id_aih': id_aih.strip(), 'code': main_proc.strip(), 'qty': 1, 'cbo': '', 'cnes': ''})
            await _log(f"  {index_label}+ EXTRAIDO: {record_id} - {p_name.strip()} | {len(procs_list)} proc (fallback)")
        else:
            for proc in procs_raw:
                qty = int(proc['qty']) if proc['qty'].isdigit() else 1
                procs_list.append({'id_aih': id_aih.strip(), 'code': proc['code'], 'qty': qty, 'cbo': proc['cbo'], 'cnes': proc['cnes']})
            await _log(f"  {index_label}+ EXTRAIDO: {record_id} - {p_name.strip()} | {cidade} | {len(procs_list)} procs | {data_ent} -> {data_sai}")

        return "saved", patient_data, aih_data, procs_list

    except Exception as e:
        await _log(f"  {index_label}ERRO DETALHE: {record_id} - {e}")
        return "error", None, None, None


async def run_scraper(competences=None, max_concurrent=5):
    db_manager.create_tables()
    db_manager.migrate_db()

    if competences is None:
        competences = [
            ("06", "2025"), ("07", "2025"), ("08", "2025"), ("09", "2025"),
            ("10", "2025"), ("11", "2025"), ("12", "2025"),
            ("01", "2026"), ("02", "2026"), ("03", "2026")
        ]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = f"scraper_hospital_{timestamp}.log"
    log_file = open(log_path, "w", encoding="utf-8")
    log_file.write(f"Scraper Hospital - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    log_file.write(f"Concorrencia: {max_concurrent} abas simultaneas\n")
    log_file.write("=" * 60 + "\n\n")

    log_lock = asyncio.Lock()

    async def log(msg):
        async with log_lock:
            print(msg)
            log_file.write(msg + "\n")
            log_file.flush()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # Login
            await log("Logging in...")
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
            await log("Logged in!")

            for month, year in competences:
                await log(f"\n{'='*60}")
                await log(f"COMPETENCIA {month}/{year}")
                await log(f"{'='*60}")

                stats = {
                    'site_total': 0,
                    'links_found': 0,
                    'already_in_db': 0,
                    'saved_new': 0,
                    'skipped_no_contar': 0,
                    'skipped_no_name': 0,
                    'errors': 0,
                    'error_details': [],
                }
                stats_lock = asyncio.Lock()

                await page.goto(REPORT_URL, wait_until="networkidle")
                await page.wait_for_selector('input[name="comp"]')
                await page.fill('input[name="comp"]', month)
                await page.fill('input[name="compa"]', year)
                await page.click('input[name="buscar"]')

                try:
                    await page.wait_for_selector('table', timeout=300000)
                except:
                    await log(f"  No results or timeout for {month}/{year}")
                    continue

                site_total = await page.evaluate("""() => {
                    const body = document.body.innerText;
                    let match = body.match(/Total[:\\s]+(\\d+)/i);
                    if (match) return parseInt(match[1]);
                    match = body.match(/Registro[s]?[:\\s]+(\\d+)/i);
                    if (match) return parseInt(match[1]);
                    const tables = document.querySelectorAll('table');
                    let maxRows = 0;
                    for (const t of tables) {
                        const anchors = t.querySelectorAll('a[href*="baixaaihre.php"]');
                        if (anchors.length > maxRows) maxRows = anchors.length;
                    }
                    return maxRows;
                }""")
                stats['site_total'] = site_total

                links_data = await page.evaluate("""() => {
                    const results = [];
                    const anchors = document.querySelectorAll('a[href*="baixaaihre.php"]');
                    anchors.forEach(a => {
                        const href = a.getAttribute('href') || '';
                        results.push(href);
                    });
                    return results;
                }""")

                stats['links_found'] = len(links_data)
                await log(f"  Site total: {site_total} | Links encontrados: {len(links_data)}")

                if site_total > 0 and len(links_data) != site_total:
                    await log(f"  ALERTA: Site mostra {site_total} registros mas encontramos {len(links_data)} links!")

                db_count = db_manager.count_by_competencia(f"{month}/{year}")
                await log(f"  Ja registrados no banco: {db_count}")
                await log(f"  {'-'*56}")

                # Batch data (thread-safe lists)
                batch_pacientes = []
                batch_aihs = []
                batch_procs = []
                batch_lock = asyncio.Lock()

                # Count prontuario occurrences
                prontuario_count = {}
                for href in links_data:
                    m = re.search(r"contar=([^&']+)", href)
                    if m:
                        pid = m.group(1)
                        prontuario_count[pid] = prontuario_count.get(pid, 0) + 1

                # Parse all tasks upfront
                tasks_to_process = []
                for i, href in enumerate(links_data):
                    contar_match = re.search(r"contar=([^&']+)", href)
                    ent_match = re.search(r"dataent=([^&']+)", href)
                    sai_match = re.search(r"datasai=([^&']+)", href)

                    if not contar_match:
                        stats['skipped_no_contar'] += 1
                        continue

                    record_id = contar_match.group(1)
                    data_ent_url = ent_match.group(1) if ent_match else ""
                    data_sai_url = sai_match.group(1) if sai_match else ""

                    if db_manager.check_aih_exists(record_id, f"{month}/{year}", data_ent_url, data_sai_url):
                        stats['already_in_db'] += 1
                        continue

                    url_match = re.search(r"location\.href='([^']+)'", href)
                    if url_match:
                        detail_path = url_match.group(1)
                    else:
                        detail_path = f"baixaaihre.php?contar={record_id}&datasai={data_sai_url}&dataent={data_ent_url}"

                    tasks_to_process.append({
                        'index': i,
                        'record_id': record_id,
                        'data_ent_url': data_ent_url,
                        'data_sai_url': data_sai_url,
                        'detail_url': f"{BASE_URL}{detail_path}",
                        'total': len(links_data),
                    })

                await log(f"  Ja no banco: {stats['already_in_db']} | A processar: {len(tasks_to_process)}")

                # Semaphore to limit concurrent pages
                semaphore = asyncio.Semaphore(max_concurrent)

                async def process_record(task):
                    async with semaphore:
                        idx = task['index']
                        record_id = task['record_id']
                        total = task['total']
                        index_label = f"[{idx+1}/{total}] "

                        detail_page = await context.new_page()
                        try:
                            await detail_page.goto(task['detail_url'], wait_until="networkidle", timeout=60000)
                            result, patient_data, aih_data, procs_list = await extract_record_data(
                                detail_page, record_id, month, year,
                                task['data_ent_url'], task['data_sai_url'],
                                index_label=index_label, log=log
                            )
                            if result == "saved":
                                observacoes = []
                                if prontuario_count.get(record_id, 1) > 1:
                                    observacoes.append(f"INTERNACAO MULTIPLA ({prontuario_count[record_id]}x no site)")
                                if not aih_data.get('id_aih') or aih_data['id_aih'].startswith('P'):
                                    observacoes.append("SEM AIH")
                                if not patient_data.get('cns'):
                                    observacoes.append("SEM CNS")
                                if not aih_data.get('cid_principal'):
                                    observacoes.append("SEM CID")
                                if not aih_data.get('data_ent'):
                                    observacoes.append("SEM DATA ENTRADA")
                                if not aih_data.get('data_sai'):
                                    observacoes.append("SEM DATA SAIDA")
                                if not procs_list:
                                    observacoes.append("SEM PROCEDIMENTOS")
                                aih_data['observacao'] = " | ".join(observacoes) if observacoes else ""

                                if observacoes:
                                    await log(f"  {index_label}!! PROBLEMAS: {record_id} -> {' | '.join(observacoes)}")

                                async with batch_lock:
                                    batch_pacientes.append(patient_data)
                                    batch_aihs.append(aih_data)
                                    batch_procs.extend(procs_list)
                                async with stats_lock:
                                    stats['saved_new'] += 1
                            elif result == "no_name":
                                async with stats_lock:
                                    stats['skipped_no_name'] += 1
                            elif result == "error":
                                async with stats_lock:
                                    stats['errors'] += 1
                                    stats['error_details'].append((record_id, "erro no detalhe"))
                        except Exception as e:
                            async with stats_lock:
                                stats['errors'] += 1
                                stats['error_details'].append((record_id, str(e)))
                            await log(f"  {index_label}ERRO: {record_id} - {e}")
                        finally:
                            await detail_page.close()

                # Process all records concurrently with semaphore
                if tasks_to_process:
                    start_time = datetime.now()
                    await asyncio.gather(*[process_record(t) for t in tasks_to_process])
                    elapsed = (datetime.now() - start_time).total_seconds()
                    await log(f"\n  Tempo de extracao: {elapsed:.0f}s ({elapsed/len(tasks_to_process):.1f}s/registro)")

                # Save batch
                if batch_pacientes:
                    await log(f"  Salvando {len(batch_aihs)} prontuarios no banco...")
                    db_manager.save_batch(batch_pacientes, batch_aihs, batch_procs)
                    await log(f"  Salvo com sucesso!")

                # Summary
                total_in_db_now = db_manager.count_by_competencia(f"{month}/{year}")
                with_problems = sum(1 for a in batch_aihs if a.get('observacao'))
                await log(f"\n  {'='*56}")
                await log(f"  RESUMO {month}/{year}")
                await log(f"  {'='*56}")
                await log(f"  Links no site:           {stats['links_found']}")
                await log(f"  Ja estavam no banco:     {stats['already_in_db']}")
                await log(f"  Extraidos agora (novos): {stats['saved_new']}")
                await log(f"  Com problemas:           {with_problems}")
                await log(f"  Sem nome (pulados):      {stats['skipped_no_name']}")
                await log(f"  Sem contar= (ignorados): {stats['skipped_no_contar']}")
                await log(f"  Erros ao carregar:       {stats['errors']}")
                await log(f"  TOTAL NO BANCO AGORA:    {total_in_db_now}")

                if stats['links_found'] > 0 and total_in_db_now != stats['links_found']:
                    diff = stats['links_found'] - total_in_db_now
                    await log(f"  DIFERENCA: faltam {diff} registros no banco!")
                elif stats['links_found'] > 0:
                    await log(f"  COMPLETO: {total_in_db_now} de {stats['links_found']} registros!")

                if stats['error_details']:
                    await log(f"\n  PRONTUARIOS COM ERRO:")
                    for rid, err in stats['error_details']:
                        await log(f"    {rid}: {err[:120]}")

        except Exception as e:
            await log(f"Critical Scraper Error: {e}")
            await page.screenshot(path="critical_error.png")
        finally:
            await browser.close()

    log_file.close()
    print(f"\nLog salvo em: {log_path}")


if __name__ == "__main__":
    asyncio.run(run_scraper())
