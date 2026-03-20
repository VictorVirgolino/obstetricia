"""Quick test: fetch SIGTAP data for a single procedure via UI navigation."""
import asyncio
from playwright.async_api import async_playwright
from scraper_sigtap import parse_brl

PROC_CODE = "0202010317"
MONTH = "03"
YEAR = "2025"
SIGTAP_HOME = "http://sigtap.datasus.gov.br/tabela-unificada/app/sec/inicio.jsp"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Step 1: Go to homepage
        print("1. Acessando homepage...")
        await page.goto(SIGTAP_HOME, wait_until="networkidle", timeout=60000)

        # Step 2: Click "Acessar a Tabela Unificada"
        print("2. Clicando em 'Acessar a Tabela Unificada'...")
        link = await page.query_selector('a:has-text("Acessar a Tabela Unificada")')
        if link:
            await link.click()
            await page.wait_for_load_state("networkidle", timeout=30000)
            await asyncio.sleep(2)
        else:
            print("ERROR: Link não encontrado!")
            await browser.close()
            return

        await page.screenshot(path="sigtap_debug_step2.png")
        print("   Screenshot step2 salvo")

        # Step 3: Select competência if needed, then search for procedure
        # Let's see what we have on the page now
        body = await page.inner_text("body")
        print(f"   Page text (first 500): {body[:500]}")

        # Try to find a search/procedure input or navigation
        # Look for procedure code input field
        inputs = await page.query_selector_all('input[type="text"]')
        print(f"   Found {len(inputs)} text inputs")
        for i, inp in enumerate(inputs):
            name = await inp.get_attribute("name") or ""
            id_attr = await inp.get_attribute("id") or ""
            print(f"   Input {i}: name={name}, id={id_attr}")

        # Look for links that might lead to procedure search
        links = await page.query_selector_all('a')
        for a in links:
            text = (await a.inner_text()).strip()
            href = await a.get_attribute("href") or ""
            if any(kw in text.lower() for kw in ["procedimento", "consultar", "pesquis", "buscar", "código"]):
                print(f"   Link: '{text}' -> {href}")

        # Try navigating to procedure page now that session is established
        print("\n3. Tentando acessar procedimento via URL com sessão ativa...")
        url = f"http://sigtap.datasus.gov.br/tabela-unificada/app/sec/procedimento/exibir/{PROC_CODE}/{MONTH}/{YEAR}"
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

        await page.screenshot(path="sigtap_debug_step3.png")

        body = await page.inner_text("body")
        print(f"   Page after goto (first 1000): {body[:1000]}")

        # Check if procedure loaded
        proc_el = await page.query_selector('#procedimento, span#procedimento')
        if proc_el:
            nome = await proc_el.inner_text()
            print(f"   Procedimento encontrado: {nome}")
        else:
            print("   Procedimento NÃO encontrado na página.")
            # Try alternate: maybe competência 01/2026 is the latest
            for comp in [("01", "2026"), ("12", "2025"), ("01", "2025")]:
                m, y = comp
                url2 = f"http://sigtap.datasus.gov.br/tabela-unificada/app/sec/procedimento/exibir/{PROC_CODE}/{m}/{y}"
                print(f"   Tentando {m}/{y}...")
                await page.goto(url2, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(1)
                proc_el = await page.query_selector('#procedimento, span#procedimento')
                if proc_el:
                    nome = await proc_el.inner_text()
                    print(f"   ENCONTRADO com {m}/{y}: {nome}")
                    break
            else:
                # Save HTML for analysis
                html = await page.content()
                with open("sigtap_debug.html", "w", encoding="utf-8") as f:
                    f.write(html)
                print("   Nenhuma competência funcionou. HTML salvo para análise.")
                await browser.close()
                return

        # Extract costs
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

            // Fallback: parse table
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

            const pick = (field) => {
                const sv = spanData[field] || '0,00';
                const tv = tableData[field] || '0,00';
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

        # Extract metadata
        metadata = await page.evaluate("""() => {
            const res = {};
            const tables = document.querySelectorAll('table');
            for (const table of tables) {
                const text = table.innerText;
                if (text.includes('Complexidade') || text.includes('Financiamento') || text.includes('Modalidade')) {
                    const rows = table.querySelectorAll('tr');
                    rows.forEach(row => {
                        const tds = row.querySelectorAll('td');
                        if (tds.length >= 2) {
                            const label = tds[0].innerText.trim().replace(':', '');
                            const value = tds[1].innerText.trim();
                            if (label && value) res[label] = value;
                        }
                    });
                }
            }
            return res;
        }""")

        s_amb = parse_brl(costs.get('s_amb', '0'))
        s_hosp = parse_brl(costs.get('s_hosp', '0'))
        t_amb = parse_brl(costs.get('t_amb', '0'))
        s_prof = parse_brl(costs.get('s_prof', '0'))
        t_hosp = parse_brl(costs.get('t_hosp', '0'))

        nome_text = nome if proc_el else "N/A"

        md = f"""# SIGTAP - Procedimento {PROC_CODE}

**Competência:** {MONTH}/{YEAR}

## Identificação

**Nome completo:** {nome_text}

## Valores

| Campo | Valor |
|-------|-------|
| Serviço Ambulatorial (SA) | R$ {s_amb:.2f} |
| Serviço Hospitalar (SH) | R$ {s_hosp:.2f} |
| Serviço Profissional (SP) | R$ {s_prof:.2f} |
| **Total Ambulatorial** | **R$ {t_amb:.2f}** |
| **Total Hospitalar** | **R$ {t_hosp:.2f}** |

## Metadados

| Campo | Valor |
|-------|-------|
"""
        for k, v in metadata.items():
            md += f"| {k} | {v} |\n"

        md += f"\n---\n*Extraído automaticamente via Playwright do SIGTAP DATASUS*\n"

        with open("sigtap_test_resultado.md", "w", encoding="utf-8") as f:
            f.write(md)

        print(f"\nResultado final:")
        print(f"  Nome: {nome_text}")
        print(f"  SA={s_amb}, SH={s_hosp}, SP={s_prof}, T.Amb={t_amb}, T.Hosp={t_hosp}")
        print(f"  Metadata: {metadata}")
        print(f"\nSalvo em sigtap_test_resultado.md")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
