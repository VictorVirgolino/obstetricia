import asyncio
from playwright.async_api import async_playwright
import db_manager
import sqlite3
from datetime import datetime

# The SIGTAP site is a JSF app. Direct URL access only works after a session
# is established by visiting the homepage first.
SIGTAP_HOME = "http://sigtap.datasus.gov.br/tabela-unificada/app/sec/inicio.jsp"
SIGTAP_PROC_URL = "http://sigtap.datasus.gov.br/tabela-unificada/app/sec/procedimento/exibir/{code}/{month}/{year}"


def parse_brl(text):
    """Parse 'R$ 395,68' or '395,68' to float."""
    if not text:
        return 0.0
    cleaned = text.replace("R$", "").replace("\xa0", "").strip()
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


async def init_sigtap_session(page):
    """Visit SIGTAP homepage to establish JSF session, then click 'Acessar a Tabela Unificada'."""
    print("Initializing SIGTAP session...")
    await page.goto(SIGTAP_HOME, wait_until="networkidle", timeout=60000)
    link = await page.query_selector('a:has-text("Acessar a Tabela Unificada")')
    if link:
        await link.click()
        await page.wait_for_load_state("networkidle", timeout=30000)
        await asyncio.sleep(2)
        print("SIGTAP session established.")
    else:
        print("WARNING: Could not find 'Acessar a Tabela Unificada' link.")


async def fetch_sigtap_data(page, code, month, year):
    url = SIGTAP_PROC_URL.format(code=code, month=month, year=year)
    print(f"Fetching SIGTAP for {code} ({month}/{year})...")

    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(1)

        # Check if procedure page loaded (look for the procedure span)
        proc_el = await page.query_selector('#procedimento, span#procedimento')
        if not proc_el:
            # Maybe we landed on the homepage - try to check
            body_text = await page.inner_text("body")
            if "Procedimento" not in body_text or "Valores" not in body_text:
                print(f"  Procedure {code} page did not load. Skipping.")
                return None

        # Extract procedure name from #procedimento span
        nome = ""
        if proc_el:
            nome_full = await proc_el.inner_text()
            # Format: "04.11.01.003-4 - OPERAÇÃO CESARIANA" -> extract name part
            if " - " in nome_full:
                nome = nome_full.split(" - ", 1)[1].strip()
            else:
                nome = nome_full.strip()

        # Extract costs from span IDs + fallback from table structure
        costs = await page.evaluate("""() => {
            const get = (id) => {
                const el = document.getElementById(id);
                if (!el) return '0,00';
                return el.innerText.trim();
            };

            const spanData = {
                s_amb: get('valorSA'),
                s_hosp: get('valorSH'),
                t_amb: get('valorSA_Total'),
                s_prof: get('valorSP'),
                t_hosp: get('totalInternacao')
            };

            // Also parse Table #5 as fallback
            const tableData = {};
            const tables = document.querySelectorAll('table');
            for (const table of tables) {
                const text = table.innerText;
                if (text.includes('Ambulatorial') && text.includes('Hospitalar')) {
                    const tds = table.querySelectorAll('td');
                    for (let i = 0; i < tds.length; i++) {
                        const label = tds[i].innerText.trim().replace(':', '');
                        const val = tds[i+1]?.innerText.trim();
                        if (label.includes('Servi') && label.includes('Ambulat')) tableData.s_amb = val;
                        else if (label.includes('Servi') && label.includes('Hospit')) tableData.s_hosp = val;
                        else if (label.includes('Total') && label.includes('Ambulat')) tableData.t_amb = val;
                        else if (label.includes('Servi') && label.includes('Profiss')) tableData.s_prof = val;
                        else if (label.includes('Total') && label.includes('Hospit')) tableData.t_hosp = val;
                    }
                    break;
                }
            }

            // Use span values, fall back to table values for any that are missing/zero
            const pick = (field) => {
                const sv = spanData[field] || '0,00';
                const tv = tableData[field] || '0,00';
                // If span returned only 'R$' or '0,00', prefer table
                const svClean = sv.replace('R$', '').replace(/\\s/g, '');
                if (!svClean || svClean === '0,00') return tv;
                return sv;
            };

            return {
                s_amb: pick('s_amb'),
                s_hosp: pick('s_hosp'),
                t_amb: pick('t_amb'),
                s_prof: pick('s_prof'),
                t_hosp: pick('t_hosp')
            };
        }""")

        s_amb = parse_brl(costs.get('s_amb', '0'))
        s_hosp = parse_brl(costs.get('s_hosp', '0'))
        t_amb = parse_brl(costs.get('t_amb', '0'))
        s_prof = parse_brl(costs.get('s_prof', '0'))
        t_hosp = parse_brl(costs.get('t_hosp', '0'))

        # Extract metadata from Table #4 structure (td-based, not dt/dd)
        metadata = await page.evaluate("""() => {
            const res = {};
            const tables = document.querySelectorAll('table');
            for (const table of tables) {
                const text = table.innerText;
                if (text.includes('Complexidade') && text.includes('Financiamento')) {
                    const rows = table.querySelectorAll('tr');
                    rows.forEach(row => {
                        const tds = row.querySelectorAll('td');
                        if (tds.length >= 2) {
                            const label = tds[0].innerText.trim().replace(':', '');
                            const value = tds[1].innerText.trim();
                            if (label.includes('Modalidade')) res.modalidade = value;
                            else if (label.includes('Complexidade')) res.complexidade = value;
                            else if (label.includes('Financiamento') && !label.includes('Sub')) res.financiamento = value;
                            else if (label.includes('Instrumento')) res.instrumento = value;
                            else if (label === 'Sexo') res.sexo = value;
                            else if (label.includes('Idade M') && label.includes('nima')) res.idade_min = value;
                            else if (label.includes('Idade M') && label.includes('xima')) res.idade_max = value;
                            else if (label.includes('dia de Perman')) res.permanencia = value;
                            else if (label.includes('Pontos')) res.pontos = value;
                        }
                    });
                    break;
                }
            }
            return res;
        }""")

        def safe_int(val, default=0):
            if not val:
                return default
            try:
                return int(val.split()[0])
            except (ValueError, IndexError):
                return default

        final_data = {
            'proc_cod': code,
            'competencia': f"{month}/{year}",
            'nome': nome,
            'descricao': "",
            'complexidade': metadata.get('complexidade', ''),
            'financiamento': metadata.get('financiamento', ''),
            's_amb': s_amb,
            's_hosp': s_hosp,
            't_amb': t_amb,
            's_prof': s_prof,
            't_hosp': t_hosp,
            'idade_min': safe_int(metadata.get('idade_min')),
            'idade_max': safe_int(metadata.get('idade_max')),
            'sexo': metadata.get('sexo', ''),
            'permanencia_media': safe_int(metadata.get('permanencia'))
        }

        db_manager.save_sigtap(final_data)
        # Determine the effective cost for logging
        custo_efetivo = t_hosp if t_hosp > 0 else t_amb
        label = "T.Hosp" if t_hosp > 0 else "T.Amb"
        all_zero = (s_amb == 0 and s_hosp == 0 and t_amb == 0 and s_prof == 0 and t_hosp == 0)
        flag = " [TODOS ZERADOS]" if all_zero else ""
        print(f"  Saved: {nome} | {label}: R$ {custo_efetivo:.2f}{flag}")
        return final_data

    except Exception as e:
        print(f"  Error fetching SIGTAP for {code}: {e}")
        return None


async def sync_all_procedures(max_concurrent=5, retry_zeros=False):
    db_manager.create_tables()
    db_manager.migrate_db()

    conn = sqlite3.connect('saude_real.db')
    cursor = conn.cursor()

    # Get unique procedures that don't have SIGTAP data yet
    cursor.execute("""
        SELECT DISTINCT p.proc_cod, r.competencia
        FROM aih_procedimentos p
        JOIN aih_records r ON p.id_aih = r.id_aih
        LEFT JOIN sigtap_metadata s ON p.proc_cod = s.proc_cod AND r.competencia = s.competencia
        WHERE s.proc_cod IS NULL
    """)
    pending = cursor.fetchall()

    failed = []
    if retry_zeros:
        # Re-fetch all entries where every value is 0 (likely extraction failures)
        cursor.execute("""
            SELECT proc_cod, competencia FROM sigtap_metadata
            WHERE s_amb = 0.0 AND s_hosp = 0.0 AND t_amb = 0.0
              AND s_prof = 0.0 AND t_hosp = 0.0
        """)
        failed = cursor.fetchall()
    conn.close()

    all_to_fetch = list(set(pending + failed))

    if not all_to_fetch:
        print("No pending procedures for SIGTAP sync.")
        return

    print(f"Found {len(all_to_fetch)} procedures to sync ({len(pending)} new, {len(failed)} failed retries).")
    print(f"Concorrencia: {max_concurrent} abas simultaneas")

    semaphore = asyncio.Semaphore(max_concurrent)
    done = 0
    total = len(all_to_fetch)
    lock = asyncio.Lock()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        # Establish session on first page
        first_page = await context.new_page()
        await init_sigtap_session(first_page)
        await first_page.close()

        async def fetch_one(code, comp):
            nonlocal done
            month, year = comp.split('/')
            async with semaphore:
                page = await context.new_page()
                try:
                    await fetch_sigtap_data(page, code, month, year)
                except Exception as e:
                    print(f"  Error {code} ({comp}): {e}")
                finally:
                    await page.close()
                async with lock:
                    done += 1
                    if done % 50 == 0:
                        print(f"  Progresso: {done}/{total} ({done/total*100:.0f}%)")

        await asyncio.gather(*[fetch_one(code, comp) for code, comp in all_to_fetch])
        await browser.close()

    print(f"\nSIGTAP sync complete: {done}/{total} processados.")
    db_manager.sync_costs()
    print("Cost sync complete.")


if __name__ == "__main__":
    asyncio.run(sync_all_procedures())
