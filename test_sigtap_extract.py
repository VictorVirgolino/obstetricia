"""Test SIGTAP value extraction for a single procedure."""
import asyncio
from playwright.async_api import async_playwright

SIGTAP_HOME = "http://sigtap.datasus.gov.br/tabela-unificada/app/sec/inicio.jsp"
SIGTAP_PROC_URL = "http://sigtap.datasus.gov.br/tabela-unificada/app/sec/procedimento/exibir/{code}/{month}/{year}"

# Test with the procedure the user wants to check
TEST_CODE = "0202010260"
TEST_MONTH = "07"
TEST_YEAR = "2025"

# Also test a few zero-value procedures
ZERO_PROCS = [
    ("0301010170", "12", "2025"),  # CONSULTA/AVALIAÇÃO EM PACIENTE INTERNADO
    ("0415010012", "12", "2025"),  # TRATAMENTO C/ CIRURGIAS MULTIPLAS
    ("0310010055", "09", "2025"),  # PARTO NORMAL EM CPN
]


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        # Init session
        page = await context.new_page()
        print("Initializing SIGTAP session...")
        await page.goto(SIGTAP_HOME, wait_until="networkidle", timeout=60000)
        link = await page.query_selector('a:has-text("Acessar a Tabela Unificada")')
        if link:
            await link.click()
            await page.wait_for_load_state("networkidle", timeout=30000)
            await asyncio.sleep(2)
            print("Session established.\n")
        await page.close()

        all_procs = [(TEST_CODE, TEST_MONTH, TEST_YEAR)] + ZERO_PROCS

        for code, month, year in all_procs:
            page = await context.new_page()
            url = SIGTAP_PROC_URL.format(code=code, month=month, year=year)
            print(f"{'='*60}")
            print(f"Fetching {code} ({month}/{year})")
            print(f"URL: {url}")

            await page.goto(url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            # 1. Check what's on the page
            title = await page.title()
            print(f"Page title: {title}")

            # 2. Get procedure name
            proc_el = await page.query_selector('#procedimento, span#procedimento')
            if proc_el:
                nome = await proc_el.inner_text()
                print(f"Procedure name: {nome}")
            else:
                print("WARNING: #procedimento element NOT found")

            # 3. Try the span IDs currently used
            span_ids = ['valorSA', 'valorSH', 'valorSA_Total', 'valorSP', 'totalInternacao']
            print("\n--- Span IDs (current approach) ---")
            for sid in span_ids:
                el = await page.query_selector(f'#{sid}')
                if el:
                    text = await el.inner_text()
                    print(f"  #{sid}: '{text}'")
                else:
                    print(f"  #{sid}: NOT FOUND")

            # 4. Dump ALL elements that contain "R$" or currency-like values
            print("\n--- All elements containing R$ ---")
            r_elements = await page.evaluate("""() => {
                const results = [];
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    // Only check direct text content, not children
                    const directText = Array.from(el.childNodes)
                        .filter(n => n.nodeType === 3)
                        .map(n => n.textContent.trim())
                        .join('');
                    const innerText = el.innerText?.trim() || '';
                    if ((innerText.includes('R$') || innerText.match(/\\d+,\\d{2}/))
                        && el.children.length === 0
                        && innerText.length < 50) {
                        results.push({
                            tag: el.tagName,
                            id: el.id || '',
                            class: el.className || '',
                            text: innerText,
                            parent_id: el.parentElement?.id || '',
                            parent_class: el.parentElement?.className || ''
                        });
                    }
                }
                return results;
            }""")
            for item in r_elements:
                print(f"  <{item['tag']} id='{item['id']}' class='{item['class']}'> = '{item['text']}' (parent: id='{item['parent_id']}' class='{item['parent_class']}')")

            # 5. Look at all tables with "Valor" or currency content
            print("\n--- Tables with financial data ---")
            tables_info = await page.evaluate("""() => {
                const results = [];
                const tables = document.querySelectorAll('table');
                for (let i = 0; i < tables.length; i++) {
                    const text = tables[i].innerText;
                    if (text.includes('Valor') || text.includes('R$') || text.includes('Ambulat') || text.includes('Hospit')) {
                        // Get all rows
                        const rows = [];
                        tables[i].querySelectorAll('tr').forEach(tr => {
                            const cells = [];
                            tr.querySelectorAll('td, th').forEach(td => {
                                cells.push(td.innerText.trim());
                            });
                            if (cells.length > 0) rows.push(cells);
                        });
                        results.push({index: i, rows: rows});
                    }
                }
                return results;
            }""")
            for t in tables_info:
                print(f"\n  Table #{t['index']}:")
                for row in t['rows']:
                    print(f"    {row}")

            # 6. Save full page HTML for analysis
            html = await page.content()
            fname = f"diag_sigtap_{code}.html"
            with open(fname, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"\nFull HTML saved to {fname}")

            await page.close()
            print()

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
