"""Verifica se o total de registros extraídos bate com o total do site."""
import asyncio
from playwright.async_api import async_playwright

LOGIN = "ItaloCunha"
PASSWORD = "10208535497"
LOGIN_URL = "http://177.10.203.220/projetoisea/PAGINA%20DE%20LOGIN.php"
BASE_URL = "http://177.10.203.220/projetoisea/"


async def verify():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        # Login
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
        await page.fill('input[name="usuario"]', LOGIN)
        await page.fill('input[name="senha"]', PASSWORD)
        await page.click('input[name="grau"][value="5"]')
        await page.wait_for_selector('select#setor')
        await page.select_option('select#setor', value="Direção")
        await page.click('.login100-form-btn')
        await page.wait_for_load_state("networkidle")

        for name, url in [("Internação", f"{BASE_URL}relainternamento.php"),
                          ("Urgência", f"{BASE_URL}relaurgencia.php")]:
            print(f"\n=== {name} ===")
            await page.goto(url, wait_until="networkidle", timeout=60000)
            await page.fill('input[name="matricula"]', '2026-01-01')
            await page.fill('input[name="matricula1"]', '2026-01-31')
            await page.click('input[name="buscar"]')
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)

            info = await page.evaluate("""
                () => {
                    const table = document.querySelector('table');
                    if (!table) return {dom_rows: 0, headers: [], last_3: []};
                    const allRows = table.querySelectorAll('tr');
                    const headerRow = allRows[0];
                    const headers = headerRow
                        ? Array.from(headerRow.querySelectorAll('th, td')).map(c => c.textContent.trim())
                        : [];
                    const dataRows = Array.from(allRows).slice(1);
                    const last3 = dataRows.slice(-3).map(tr =>
                        Array.from(tr.querySelectorAll('td')).map(td => td.textContent.trim().substring(0, 40))
                    );
                    // Check first row columns
                    const firstRow = dataRows[0]
                        ? Array.from(dataRows[0].querySelectorAll('td')).map(td => td.textContent.trim().substring(0, 40))
                        : [];
                    return {
                        dom_total_tr: allRows.length,
                        dom_data_rows: dataRows.length,
                        headers: headers,
                        num_columns_header: headers.length,
                        first_row: firstRow,
                        num_columns_first_row: firstRow.length,
                        last_3: last3,
                    };
                }
            """)
            print(f"Total <tr> no DOM: {info['dom_total_tr']}")
            print(f"Data rows (excl header): {info['dom_data_rows']}")
            print(f"Headers ({info['num_columns_header']}): {info['headers']}")
            print(f"First row ({info['num_columns_first_row']} cols): {info['first_row']}")
            print(f"Últimas 3 linhas:")
            for row in info['last_3']:
                print(f"  {row}")

            # Also check for any pagination or "total" text
            total_text = await page.evaluate("""
                () => {
                    const body = document.body.textContent;
                    const matches = body.match(/total[:\\s]*(\\d+)/i);
                    return matches ? matches[0] : 'Não encontrado';
                }
            """)
            print(f"Texto 'total' na página: {total_text}")

        # Compare with DB
        import sqlite3
        conn = sqlite3.connect('saude_real.db')
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM estat_internacao")
        print(f"\nDB estat_internacao: {c.fetchone()[0]}")
        c.execute("SELECT COUNT(*) FROM estat_urgencia")
        print(f"DB estat_urgencia: {c.fetchone()[0]}")
        conn.close()

        await browser.close()


if __name__ == "__main__":
    asyncio.run(verify())
