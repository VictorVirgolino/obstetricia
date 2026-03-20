"""
Exploração dos relatórios de qualidade - identificar radios e testar submissão.
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
    return await page.evaluate("""
        () => {
            const tables = document.querySelectorAll('table');
            return Array.from(tables).map((table, idx) => {
                const allRows = table.querySelectorAll('tr');
                const rows = Array.from(allRows).slice(0, 8).map(tr =>
                    Array.from(tr.querySelectorAll('td, th')).map(cell => cell.textContent.trim().substring(0, 80))
                );
                return { index: idx, totalRows: allRows.length, sampleRows: rows };
            });
        }
    """)


async def explore():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        await login(page)

        print("\n=== QUALIDADE - RADIO BUTTONS ===")
        await page.goto(f"{BASE_URL}relanaqarquivo.php", wait_until="networkidle", timeout=60000)

        # Get radio buttons with their labels using JS that looks at surrounding text
        radios = await page.evaluate("""
            () => {
                const radios = document.querySelectorAll('input[name="caso"]');
                return Array.from(radios).map((r, i) => {
                    // Try label element
                    let label = '';
                    const labelEl = r.closest('label') || r.parentElement?.querySelector('label');
                    if (labelEl) label = labelEl.textContent.trim();

                    // Try next sibling text
                    if (!label) {
                        let node = r.nextSibling;
                        while (node && !label) {
                            if (node.nodeType === 3) label = node.textContent.trim();
                            else if (node.nodeType === 1) label = node.textContent.trim();
                            node = node.nextSibling;
                        }
                    }

                    // Try parent text (minus child element text)
                    if (!label && r.parentElement) {
                        const parent = r.parentElement;
                        const childTexts = Array.from(parent.children).map(c => c.textContent).join('');
                        label = parent.textContent.replace(childTexts, '').trim();
                    }

                    return {
                        index: i,
                        value: r.value,
                        label: label.substring(0, 100),
                        checked: r.checked,
                        visible: r.offsetParent !== null
                    };
                });
            }
        """)
        print(f"Total radios: {len(radios)}")
        for r in radios:
            print(f"  [{r['index']}] value='{r['value']}' label='{r['label']}' checked={r['checked']} visible={r['visible']}")

        # Try a different approach: get all text near each radio
        labels2 = await page.evaluate("""
            () => {
                const radios = document.querySelectorAll('input[name="caso"]');
                return Array.from(radios).map((r, i) => {
                    // Get the containing div/section
                    const container = r.closest('div, td, li, span, p') || r.parentElement;
                    const containerText = container ? container.textContent.trim().substring(0, 150) : '';

                    // Get immediate preceding text
                    let prevText = '';
                    let prev = r.previousSibling;
                    if (prev && prev.nodeType === 3) prevText = prev.textContent.trim();
                    else if (prev && prev.nodeType === 1) prevText = prev.textContent.trim();

                    // Get immediate following text
                    let nextText = '';
                    let next = r.nextSibling;
                    if (next && next.nodeType === 3) nextText = next.textContent.trim();
                    else if (next && next.nodeType === 1) nextText = next.textContent.trim();

                    return {
                        index: i,
                        value: r.value,
                        prevText: prevText.substring(0, 80),
                        nextText: nextText.substring(0, 80),
                        containerText: containerText.substring(0, 150)
                    };
                });
            }
        """)
        print("\nRadio labels (detail):")
        for r in labels2:
            print(f"  [{r['index']}] value='{r['value']}' next='{r['nextText']}' prev='{r['prevText']}'")

        # Test first few visible radios with date submission
        for radio_idx in [0, 1, 2, 3, 4]:
            if radio_idx >= len(radios):
                break
            r = radios[radio_idx]
            print(f"\n--- Testando radio [{radio_idx}] value='{r['value']}' ---")

            await page.goto(f"{BASE_URL}relanaqarquivo.php", wait_until="networkidle", timeout=60000)

            # Click this radio
            all_radios = await page.query_selector_all('input[name="caso"]')
            if radio_idx < len(all_radios):
                await all_radios[radio_idx].click()
                await asyncio.sleep(1)

            # Find visible date inputs and fill them
            date_inputs = await page.query_selector_all('input[type="date"]')
            filled_dates = 0
            for di in date_inputs:
                visible = await di.evaluate("el => el.offsetParent !== null")
                if visible:
                    if filled_dates == 0:
                        await di.fill('2026-01-01')
                    elif filled_dates == 1:
                        await di.fill('2026-01-31')
                    filled_dates += 1
                    if filled_dates >= 2:
                        break

            # Find visible submit button
            buscar = await page.query_selector('input[name="buscar"]')
            if buscar:
                visible = await buscar.evaluate("el => el.offsetParent !== null")
                if visible:
                    await buscar.click()
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(3)

                    tables = await capture_tables(page)
                    for t in tables:
                        print(f"  Tabela {t['index']}: {t['totalRows']} linhas")
                        for row in t['sampleRows'][:4]:
                            print(f"    {row}")
                else:
                    # Try all submit buttons
                    submits = await page.query_selector_all('input[type="submit"]')
                    for sub in submits:
                        vis = await sub.evaluate("el => el.offsetParent !== null")
                        if vis:
                            val = await sub.get_attribute('value')
                            print(f"  Clicando submit visível: {val}")
                            await sub.click()
                            await page.wait_for_load_state("networkidle")
                            await asyncio.sleep(3)
                            tables = await capture_tables(page)
                            for t in tables:
                                print(f"  Tabela {t['index']}: {t['totalRows']} linhas")
                                for row in t['sampleRows'][:4]:
                                    print(f"    {row}")
                            break

        print("\n\nDone!")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(explore())
