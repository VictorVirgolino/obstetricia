"""
Diagnostico Hospital v2 - Testa navegacao ao detalhe.
"""
import asyncio
from playwright.async_api import async_playwright
import re

LOGIN = "ItaloCunha"
PASSWORD = "10208535497"
LOGIN_URL = "http://177.10.203.220/projetoisea/PAGINA%20DE%20LOGIN.php"

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # Login
        print("1. Login...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
        await page.fill('input[name="usuario"]', LOGIN)
        await page.fill('input[name="senha"]', PASSWORD)
        await page.click('input[name="grau"][value="5"]')
        await page.wait_for_selector('select#setor')
        await page.select_option('select#setor', value="Contas")
        await page.click('.login100-form-btn')
        await page.wait_for_load_state("networkidle")
        print("   Logged in!")

        # Go to reports
        print("2. Navigating to reports...")
        await page.goto("http://177.10.203.220/projetoisea/relasisaih.php?operacao=R", wait_until="networkidle")

        # Search for 03/2026
        print("3. Searching 03/2026...")
        await page.fill('input[name="comp"]', "03")
        await page.fill('input[name="compa"]', "2026")
        await page.click('input[name="buscar"]')
        await page.wait_for_selector('table', timeout=120000)

        # Extract first link URL
        links = await page.query_selector_all('a[href*="baixaaihre.php"]')
        print(f"  Found {len(links)} links")

        first_href = await links[0].get_attribute('href')
        print(f"  First href: {first_href}")

        # Extract the actual URL from javascript href
        match = re.search(r"location\.href='([^']+)'", first_href)
        if match:
            detail_path = match.group(1)
        else:
            detail_path = first_href.split("'")[-2]

        detail_url = f"http://177.10.203.220/projetoisea/{detail_path}"
        print(f"  Detail URL: {detail_url}")

        # Extract data_ent and data_sai from URL params
        ent_match = re.search(r"dataent=([^&]+)", detail_path)
        sai_match = re.search(r"datasai=([^&]+)", detail_path)
        contar_match = re.search(r"contar=([^&]+)", detail_path)
        if ent_match:
            print(f"  data_ent from URL: {ent_match.group(1)}")
        if sai_match:
            print(f"  data_sai from URL: {sai_match.group(1)}")
        if contar_match:
            print(f"  prontuario from URL: {contar_match.group(1)}")

        # Navigate directly to detail URL
        print("\n4. Opening detail page directly...")
        detail_page = await context.new_page()
        await detail_page.goto(detail_url, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)

        await detail_page.screenshot(path="diag_hosp_3_detail_before.png", full_page=True)
        print("  Screenshot (before checkboxes): diag_hosp_3_detail_before.png")

        # Find all checkboxes
        print("\n5. Checkboxes on detail page...")
        checkboxes = await detail_page.evaluate("""() => {
            return Array.from(document.querySelectorAll('input[type="checkbox"]')).map(cb => ({
                id: cb.id,
                name: cb.name,
                value: cb.value,
                checked: cb.checked,
                label: cb.parentElement?.innerText?.trim().substring(0, 80) || '',
                nextText: cb.nextSibling?.textContent?.trim().substring(0, 60) || ''
            }));
        }""")
        for cb in checkboxes:
            print(f"  id='{cb['id']}' name='{cb['name']}' checked={cb['checked']} label='{cb['label'][:50]}' next='{cb['nextText'][:40]}'")

        # Check desired checkboxes
        print("\n6. Checking 'dados do paciente' and 'procedimentos realizados'...")
        for cb in checkboxes:
            cb_id = cb['id']
            cb_text = (cb['label'] + ' ' + cb['nextText']).lower()
            if 'paciente' in cb_text or 'procedimento' in cb_text:
                print(f"  Checking: #{cb_id} ({cb_text[:50]})")
                try:
                    await detail_page.check(f"#{cb_id}")
                except:
                    # Try with escaped ID
                    await detail_page.evaluate(f"document.getElementById('{cb_id}').checked = true; document.getElementById('{cb_id}').dispatchEvent(new Event('change'))")
                await asyncio.sleep(1)

        await asyncio.sleep(3)
        await detail_page.screenshot(path="diag_hosp_4_detail_after.png", full_page=True)
        print("  Screenshot (after checkboxes): diag_hosp_4_detail_after.png")

        # Dump ALL inputs with values
        print("\n7. All input fields with values...")
        inputs = await detail_page.evaluate("""() => {
            return Array.from(document.querySelectorAll('input')).map(el => ({
                id: el.id, name: el.name, type: el.type,
                value: el.value?.substring(0, 100) || ''
            })).filter(el => el.value && el.type !== 'hidden' && el.type !== 'checkbox');
        }""")
        for inp in inputs:
            print(f"  {inp['id'] or inp['name']}: '{inp['value']}' (type={inp['type']})")

        # Select elements
        print("\n8. Select elements...")
        selects = await detail_page.evaluate("""() => {
            return Array.from(document.querySelectorAll('select')).map(el => ({
                id: el.id, name: el.name,
                selected: el.options[el.selectedIndex]?.text || '',
                selectedValue: el.value
            }));
        }""")
        for sel in selects:
            print(f"  {sel['id'] or sel['name']}: '{sel['selected']}' (value={sel['selectedValue']})")

        # ALL tables
        print("\n9. All tables on detail page...")
        tables = await detail_page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('table').forEach((t, i) => {
                const rows = [];
                t.querySelectorAll('tr').forEach(tr => {
                    const cells = [];
                    tr.querySelectorAll('td, th').forEach(c => {
                        const inputs = c.querySelectorAll('input');
                        if (inputs.length > 0) {
                            const inputInfo = Array.from(inputs).map(inp =>
                                `[${inp.type}#${inp.id}=${inp.value?.substring(0,25)||''}]`
                            ).join(' ');
                            cells.push(inputInfo);
                        } else {
                            cells.push(c.innerText?.trim().substring(0, 50) || '');
                        }
                    });
                    if (cells.length && cells.some(c => c.length > 0)) rows.push(cells);
                });
                if (rows.length) results.push({i, rows: rows.slice(0, 15)});
            });
            return results;
        }""")
        for t in tables:
            print(f"\n  Table #{t['i']}:")
            for row in t['rows']:
                print(f"    {' | '.join(row)}")

        # Save HTML
        html = await detail_page.content()
        with open("diag_hosp_detail.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("\n  Full HTML saved: diag_hosp_detail.html")

        await detail_page.close()
        await browser.close()
        print("\n=== DIAGNOSTICO HOSPITAL COMPLETO ===")

if __name__ == "__main__":
    asyncio.run(run())
