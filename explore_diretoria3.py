"""
Exploração simplificada: navega, submete, captura resultados.
"""
import asyncio
from playwright.async_api import async_playwright

LOGIN = "ItaloCunha"
PASSWORD = "10208535497"
LOGIN_URL = "http://177.10.203.220/projetoisea/PAGINA%20DE%20LOGIN.php"
BASE_URL = "http://177.10.203.220/projetoisea/"


async def login(page):
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
    await page.fill('input[name="usuario"]', LOGIN)
    await page.fill('input[name="senha"]', PASSWORD)
    await page.click('input[name="grau"][value="5"]')
    await page.wait_for_selector('select#setor')
    await page.select_option('select#setor', value="Direção")
    await page.click('.login100-form-btn')
    await page.wait_for_load_state("networkidle")
    print("Login OK!")


async def capture_tables(page):
    """Capture table headers and first few rows."""
    return await page.evaluate("""
        () => {
            const tables = document.querySelectorAll('table');
            return Array.from(tables).map((table, idx) => {
                const allRows = table.querySelectorAll('tr');
                const rows = Array.from(allRows).slice(0, 6).map(tr =>
                    Array.from(tr.querySelectorAll('td, th')).map(cell => cell.textContent.trim().substring(0, 60))
                );
                return {
                    index: idx,
                    totalRows: allRows.length,
                    sampleRows: rows
                };
            });
        }
    """)


async def explore():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        await login(page)

        # ===== INTERNAÇÃO =====
        print("\n=== INTERNAÇÃO ===")
        await page.goto(f"{BASE_URL}relainternamento.php", wait_until="networkidle", timeout=60000)

        # Radio values
        radios = await page.evaluate("""
            () => Array.from(document.querySelectorAll('input[name="caso"]')).map(r => ({
                value: r.value, checked: r.checked
            }))
        """)
        print(f"Radios 'caso': {radios}")

        await page.fill('input[name="matricula"]', '2026-01-01')
        await page.fill('input[name="matricula1"]', '2026-01-31')
        await page.click('input[name="buscar"]')
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        await page.screenshot(path="result_internacao.png", full_page=True)

        tables = await capture_tables(page)
        for t in tables:
            print(f"\nTabela {t['index']}: {t['totalRows']} linhas")
            for row in t['sampleRows']:
                print(f"  {row}")

        # ===== URGÊNCIA =====
        print("\n\n=== URGÊNCIA ===")
        await page.goto(f"{BASE_URL}relaurgencia.php", wait_until="networkidle", timeout=60000)

        radios = await page.evaluate("""
            () => Array.from(document.querySelectorAll('input[name="caso"]')).map(r => ({
                value: r.value, checked: r.checked
            }))
        """)
        print(f"Radios 'caso': {radios}")

        # Form inputs
        inputs = await page.evaluate("""
            () => {
                const form = document.querySelector('form');
                if (!form) return [];
                return Array.from(form.querySelectorAll('input, select')).map(el => ({
                    tag: el.tagName, name: el.name, id: el.id, type: el.type
                }));
            }
        """)
        print(f"Form inputs: {inputs}")

        date_inputs = await page.query_selector_all('input[type="date"]')
        if len(date_inputs) >= 2:
            await date_inputs[0].fill('2026-01-01')
            await date_inputs[1].fill('2026-01-31')

        buscar = await page.query_selector('input[name="buscar"]')
        if buscar:
            await buscar.click()
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)

        await page.screenshot(path="result_urgencia.png", full_page=True)

        tables = await capture_tables(page)
        for t in tables:
            print(f"\nTabela {t['index']}: {t['totalRows']} linhas")
            for row in t['sampleRows']:
                print(f"  {row}")

        # ===== QUALIDADE =====
        print("\n\n=== QUALIDADE ===")
        await page.goto(f"{BASE_URL}relanaqarquivo.php", wait_until="networkidle", timeout=60000)
        await page.screenshot(path="result_qualidade_form.png", full_page=True)

        # Form structure
        form_info = await page.evaluate("""
            () => {
                const forms = document.querySelectorAll('form');
                return Array.from(forms).map(form => ({
                    action: form.action,
                    inputs: Array.from(form.querySelectorAll('input, select')).map(el => {
                        const info = {tag: el.tagName, name: el.name, id: el.id, type: el.type};
                        if (el.tagName === 'SELECT') {
                            info.options = Array.from(el.options).map(o => ({value: o.value, text: o.text}));
                        }
                        return info;
                    })
                }));
            }
        """)
        for fi, form in enumerate(form_info):
            print(f"\nForm {fi}: action={form['action']}")
            for inp in form['inputs']:
                s = f"  {inp['tag']} name={inp['name']} id={inp['id']} type={inp['type']}"
                if inp.get('options'):
                    s += f"\n    OPTIONS: {[o['text'] for o in inp['options']]}"
                print(s)

        # Select first meaningful option and search
        main_select = None
        for form in form_info:
            for inp in form['inputs']:
                if inp['tag'] == 'SELECT' and inp.get('options') and len(inp['options']) > 2:
                    if inp['name'] != 'setor2':
                        main_select = inp
                        break

        if main_select:
            print(f"\nSelecionando: {main_select['name']} -> primeira opção com valor")
            for opt in main_select['options']:
                if opt['value']:
                    await page.select_option(f"select[name='{main_select['name']}']", value=opt['value'])
                    print(f"  Selecionado: {opt['text']}")
                    break

        date_inputs = await page.query_selector_all('input[type="date"]')
        if date_inputs:
            print(f"Date inputs encontrados: {len(date_inputs)}")
            if len(date_inputs) >= 2:
                await date_inputs[0].fill('2026-01-01')
                await date_inputs[1].fill('2026-01-31')

        buscar = await page.query_selector('input[name="buscar"], input[type="submit"]')
        if buscar:
            btn_value = await buscar.get_attribute('value')
            print(f"Clicando botão: {btn_value}")
            await buscar.click()
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)

        await page.screenshot(path="result_qualidade.png", full_page=True)

        tables = await capture_tables(page)
        for t in tables:
            print(f"\nTabela {t['index']}: {t['totalRows']} linhas")
            for row in t['sampleRows']:
                print(f"  {row}")

        # Salvar HTML de qualidade
        html = await page.content()
        with open("result_qualidade.html", "w", encoding="utf-8") as f:
            f.write(html)

        print("\n\nDone!")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(explore())
