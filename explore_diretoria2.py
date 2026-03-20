"""
Script de exploração fase 2: submete formulários e captura dados retornados.
- Internação (relainternamento.php)
- Urgência (relaurgencia.php)
- Relatórios de Qualidade (relanaqarquivo.php)
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


async def capture_table_structure(page, name):
    """Capture full table structure after form submission."""
    result = await page.evaluate("""
        () => {
            const tables = document.querySelectorAll('table');
            const data = [];
            for (let t = 0; t < tables.length; t++) {
                const table = tables[t];
                const headers = Array.from(table.querySelectorAll('thead th, tr:first-child th')).map(th => th.textContent.trim());
                const rows = Array.from(table.querySelectorAll('tbody tr, tr')).slice(0, 5).map(tr =>
                    Array.from(tr.querySelectorAll('td, th')).map(td => td.textContent.trim().substring(0, 80))
                );
                const totalRows = table.querySelectorAll('tbody tr, tr').length;
                // Check for links in cells
                const cellLinks = Array.from(table.querySelectorAll('a')).slice(0, 3).map(a => ({
                    href: a.href, text: a.textContent.trim().substring(0, 50)
                }));
                data.push({headers, rows, totalRows, cellLinks});
            }
            return data;
        }
    """)
    print(f"\n{'='*60}")
    print(f"TABELAS em {name}: {len(result)} tabelas encontradas")
    for i, table in enumerate(result):
        print(f"\n  Tabela {i}: {table['totalRows']} linhas")
        print(f"  Headers: {table['headers']}")
        for j, row in enumerate(table['rows'][:3]):
            print(f"  Row {j}: {row}")
        if table['cellLinks']:
            print(f"  Links nas células: {table['cellLinks']}")
    return result


async def explore_internacao(page):
    print("\n" + "="*60)
    print("EXPLORANDO: INTERNAÇÃO (relainternamento.php)")
    print("="*60)

    await page.goto(f"{BASE_URL}relainternamento.php", wait_until="networkidle", timeout=60000)
    await page.screenshot(path="explore_internacao_form.png", full_page=True)

    # Verificar radio buttons "caso"
    radio_options = await page.evaluate("""
        () => {
            const radios = document.querySelectorAll('input[name="caso"]');
            return Array.from(radios).map(r => ({
                value: r.value,
                label: r.parentElement?.textContent?.trim() || r.nextSibling?.textContent?.trim() || '',
                checked: r.checked
            }));
        }
    """)
    print(f"Radio 'caso': {radio_options}")

    # Preencher datas (último mês)
    await page.fill('input[name="matricula"]', '2026-01-01')
    await page.fill('input[name="matricula1"]', '2026-01-31')

    await page.screenshot(path="explore_internacao_preenchido.png", full_page=True)

    # Submeter
    await page.click('input[name="buscar"]')
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(2)

    await page.screenshot(path="explore_internacao_resultado.png", full_page=True)

    tables = await capture_table_structure(page, "Internação")

    # Salvar HTML
    html = await page.content()
    with open("explore_internacao.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("HTML salvo em explore_internacao.html")

    return tables


async def explore_urgencia(page):
    print("\n" + "="*60)
    print("EXPLORANDO: URGÊNCIA (relaurgencia.php)")
    print("="*60)

    await page.goto(f"{BASE_URL}relaurgencia.php", wait_until="networkidle", timeout=60000)
    await page.screenshot(path="explore_urgencia_form.png", full_page=True)

    # Verificar estrutura do formulário
    form_structure = await page.evaluate("""
        () => {
            const form = document.querySelector('form');
            if (!form) return null;
            return {
                action: form.action,
                inputs: Array.from(form.querySelectorAll('input, select, textarea')).map(el => ({
                    tag: el.tagName, type: el.type, name: el.name, id: el.id,
                    options: el.tagName === 'SELECT' ? Array.from(el.options).map(o => ({value: o.value, text: o.text})) : undefined
                }))
            };
        }
    """)
    print(f"Form urgência: {form_structure}")

    # Radio buttons
    radio_options = await page.evaluate("""
        () => {
            const radios = document.querySelectorAll('input[name="caso"]');
            return Array.from(radios).map(r => ({
                value: r.value,
                label: r.parentElement?.textContent?.trim() || '',
                checked: r.checked
            }));
        }
    """)
    print(f"Radio 'caso': {radio_options}")

    # Preencher datas
    date_inputs = await page.query_selector_all('input[type="date"]')
    if len(date_inputs) >= 2:
        await date_inputs[0].fill('2026-01-01')
        await date_inputs[1].fill('2026-01-31')

    await page.screenshot(path="explore_urgencia_preenchido.png", full_page=True)

    # Submeter
    buscar = await page.query_selector('input[name="buscar"]')
    if buscar:
        await buscar.click()
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

    await page.screenshot(path="explore_urgencia_resultado.png", full_page=True)

    tables = await capture_table_structure(page, "Urgência")

    html = await page.content()
    with open("explore_urgencia.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("HTML salvo em explore_urgencia.html")

    return tables


async def explore_qualidade(page):
    print("\n" + "="*60)
    print("EXPLORANDO: RELATÓRIOS DE QUALIDADE (relanaqarquivo.php)")
    print("="*60)

    await page.goto(f"{BASE_URL}relanaqarquivo.php", wait_until="networkidle", timeout=60000)
    await page.screenshot(path="explore_qualidade_form.png", full_page=True)

    # Capturar toda a estrutura
    form_structure = await page.evaluate("""
        () => {
            const forms = document.querySelectorAll('form');
            return Array.from(forms).map(form => ({
                action: form.action,
                method: form.method,
                inputs: Array.from(form.querySelectorAll('input, select, textarea')).map(el => ({
                    tag: el.tagName, type: el.type, name: el.name, id: el.id,
                    value: el.value,
                    options: el.tagName === 'SELECT' ? Array.from(el.options).map(o => ({value: o.value, text: o.text})) : undefined
                }))
            }));
        }
    """)
    print(f"Forms na página de qualidade ({len(form_structure)}):")
    for i, form in enumerate(form_structure):
        print(f"\n  Form {i}: action={form['action']}, method={form['method']}")
        for inp in form['inputs']:
            print(f"    {inp['tag']} name={inp['name']} id={inp['id']} type={inp['type']}")
            if inp.get('options'):
                for opt in inp['options']:
                    print(f"      option: value='{opt['value']}' text='{opt['text']}'")

    # Selecionar primeira opção e buscar
    selects = await page.query_selector_all('select')
    select_info = []
    for sel in selects:
        name = await sel.get_attribute('name')
        sel_id = await sel.get_attribute('id')
        opts = await sel.evaluate("""
            el => Array.from(el.options).map(o => ({value: o.value, text: o.text}))
        """)
        select_info.append({'name': name, 'id': sel_id, 'options': opts})

    print(f"\nSelects detalhados: {select_info}")

    # Tentar buscar com a primeira opção de relatório
    # Preencher datas se existirem
    date_inputs = await page.query_selector_all('input[type="date"]')
    if date_inputs:
        print(f"\n  Encontrados {len(date_inputs)} campos de data")
        if len(date_inputs) >= 2:
            await date_inputs[0].fill('2026-01-01')
            await date_inputs[1].fill('2026-01-31')
        elif len(date_inputs) == 1:
            await date_inputs[0].fill('2026-01-01')

    # Buscar
    buscar = await page.query_selector('input[name="buscar"], button[type="submit"], input[type="submit"]')
    if buscar:
        await page.screenshot(path="explore_qualidade_preenchido.png", full_page=True)
        await buscar.click()
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        await page.screenshot(path="explore_qualidade_resultado.png", full_page=True)
        tables = await capture_table_structure(page, "Qualidade")

    html = await page.content()
    with open("explore_qualidade.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("HTML salvo em explore_qualidade.html")


async def explore():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        await login(page)

        await explore_internacao(page)
        await explore_urgencia(page)
        await explore_qualidade(page)

        print("\n\n=== EXPLORAÇÃO CONCLUÍDA ===")
        print("Screenshots salvos: explore_internacao_*.png, explore_urgencia_*.png, explore_qualidade_*.png")
        print("HTML salvos: explore_internacao.html, explore_urgencia.html, explore_qualidade.html")

        await asyncio.sleep(3)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(explore())
