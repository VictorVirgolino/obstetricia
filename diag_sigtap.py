"""
Diagnostico SIGTAP v2 - Navega pela interface real do SIGTAP.
Roda: python diag_sigtap.py
"""
import asyncio
from playwright.async_api import async_playwright

BASE_URL = "http://sigtap.datasus.gov.br/tabela-unificada/app/sec/inicio.jsp"
PROC_CODE = "0411010034"
COMP_MONTH = "03"
COMP_YEAR = "2026"

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # Step 1: Homepage
        print("1. Acessando homepage SIGTAP...")
        await page.goto(BASE_URL, wait_until="networkidle", timeout=60000)

        # Step 2: Click "Acessar a Tabela Unificada"
        print("2. Clicando 'Acessar a Tabela Unificada'...")
        link = await page.query_selector('a:has-text("Acessar a Tabela Unificada")')
        if link:
            href = await link.get_attribute("href")
            print(f"   Link href: {href}")
            await link.click()
            await page.wait_for_load_state("networkidle", timeout=30000)
            await asyncio.sleep(2)
        else:
            print("   ERRO: Link nao encontrado!")
            await browser.close()
            return

        await page.screenshot(path="diag_sigtap_2_tabela.png", full_page=True)
        print("   Screenshot: diag_sigtap_2_tabela.png")

        # Step 3: Check current URL and page content
        print(f"   URL atual: {page.url}")

        # Dump all visible elements for understanding the search interface
        print("\n3. Analisando interface de busca...")
        inputs = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('input, select, textarea').forEach(el => {
                results.push({
                    tag: el.tagName,
                    type: el.type || '',
                    name: el.name || '',
                    id: el.id || '',
                    placeholder: el.placeholder || '',
                    value: el.value || '',
                    class: el.className?.substring(0, 60) || ''
                });
            });
            return results;
        }""")
        for inp in inputs:
            print(f"   <{inp['tag']} type='{inp['type']}' name='{inp['name']}' id='{inp['id']}' placeholder='{inp['placeholder']}' value='{inp['value']}'> class='{inp['class']}'")

        # Step 4: Try to navigate directly to the procedure URL now that session exists
        proc_url = f"http://sigtap.datasus.gov.br/tabela-unificada/app/sec/procedimento/exibir/{PROC_CODE}/{COMP_MONTH}/{COMP_YEAR}"
        print(f"\n4. Tentando URL direta: {proc_url}")
        await page.goto(proc_url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

        current_url = page.url
        print(f"   URL resultante: {current_url}")
        await page.screenshot(path="diag_sigtap_3_procedimento.png", full_page=True)
        print("   Screenshot: diag_sigtap_3_procedimento.png")

        # Check if we got to the procedure page
        body_text = await page.inner_text("body")
        has_values = "R$" in body_text or "Valor" in body_text or "valor" in body_text

        if has_values or PROC_CODE in body_text:
            print("   SUCESSO: Pagina do procedimento carregada!")
        else:
            print("   Pagina nao carregou o procedimento. Tentando busca pela interface...")

            # Step 5: Go back to table and try to search
            await page.go_back()
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(1)

            # Try to find a search field and enter the procedure code
            print("\n5. Tentando busca pela interface...")

            # Look for competencia selector
            selects = await page.query_selector_all("select")
            for sel in selects:
                sel_id = await sel.get_attribute("id") or ""
                sel_name = await sel.get_attribute("name") or ""
                options = await sel.evaluate("el => Array.from(el.options).map(o => ({value: o.value, text: o.text})).slice(0, 10)")
                print(f"   Select id='{sel_id}' name='{sel_name}': {options[:5]}")

            # Look for search input
            search_inputs = await page.query_selector_all("input[type='text'], input[type='search']")
            for si in search_inputs:
                si_id = await si.get_attribute("id") or ""
                si_name = await si.get_attribute("name") or ""
                print(f"   Search input id='{si_id}' name='{si_name}'")

            # Try filling procedure code in any text input
            for si in search_inputs:
                si_id = await si.get_attribute("id") or ""
                si_name = await si.get_attribute("name") or ""
                if "codigo" in si_id.lower() or "codigo" in si_name.lower() or "proc" in si_id.lower():
                    print(f"   Preenchendo {si_id} com {PROC_CODE}")
                    await si.fill(PROC_CODE)
                    break

            # Look for search/submit buttons
            buttons = await page.query_selector_all("input[type='submit'], button, input[type='button']")
            for btn in buttons:
                btn_val = await btn.get_attribute("value") or await btn.inner_text() if await btn.get_attribute("value") is None else await btn.get_attribute("value")
                btn_id = await btn.get_attribute("id") or ""
                print(f"   Button id='{btn_id}' value='{btn_val}'")

        # Final: dump all text and HTML for analysis
        html = await page.content()
        with open("diag_sigtap_dom.html", "w", encoding="utf-8") as f:
            f.write(html)
        text = await page.inner_text("body")
        with open("diag_sigtap_text.txt", "w", encoding="utf-8") as f:
            f.write(text)

        # Extract ALL content including tabs, values, everything
        print("\n=== FULL PAGE TEXT (first 3000 chars) ===")
        print(text[:3000])

        # Check for iframes
        frames = page.frames
        print(f"\n=== FRAMES ({len(frames)}) ===")
        for frame in frames:
            print(f"   Frame: {frame.url} name={frame.name}")

        # Extract all monetary values
        print("\n=== Valores monetarios ===")
        money = await page.evaluate("""() => {
            const results = [];
            const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            while (walk.nextNode()) {
                const t = walk.currentNode.textContent.trim();
                if (t.match(/R\\$|\\d+[,.]\\d{2}/)) {
                    const p = walk.currentNode.parentElement;
                    results.push({
                        text: t.substring(0, 150),
                        tag: p?.tagName, id: p?.id, class: p?.className?.substring(0, 40)
                    });
                }
            }
            return results;
        }""")
        for m in money:
            print(f"   {m['text'][:100]} | <{m['tag']} id='{m['id']}' class='{m['class']}'>")

        # Extract tables
        print("\n=== TABELAS ===")
        tables = await page.evaluate("""() => {
            const res = [];
            document.querySelectorAll('table').forEach((t, i) => {
                const rows = [];
                t.querySelectorAll('tr').forEach(tr => {
                    const cells = [];
                    tr.querySelectorAll('td, th').forEach(c => cells.push(c.innerText?.trim().substring(0, 60)));
                    if (cells.length) rows.push(cells);
                });
                res.push({i, id: t.id, cls: t.className?.substring(0, 40), rows: rows.slice(0, 15)});
            });
            return res;
        }""")
        for t in tables:
            print(f"\n  Table #{t['i']} id='{t['id']}' class='{t['cls']}'")
            for r in t['rows']:
                print(f"    {'  |  '.join(r)}")

        # Extract dt/dd
        print("\n=== DT/DD ===")
        dtdd = await page.evaluate("""() => {
            const r = [];
            document.querySelectorAll('dt').forEach(dt => {
                const dd = dt.nextElementSibling;
                if (dd?.tagName === 'DD') r.push({dt: dt.innerText?.trim(), dd: dd.innerText?.trim().substring(0, 100)});
            });
            return r;
        }""")
        for d in dtdd:
            print(f"   {d['dt']}: {d['dd']}")

        # Check for tabs/sections
        print("\n=== TABS / Sections ===")
        tabs = await page.evaluate("""() => {
            const r = [];
            document.querySelectorAll('.ui-tabs-nav li a, .tabs a, [role="tab"], .tab-pane, .nav-tabs a, .nav-link, .ui-tabview a, fieldset legend').forEach(el => {
                r.push({tag: el.tagName, text: el.innerText?.trim().substring(0, 80), href: el.href || '', class: el.className?.substring(0, 40), id: el.id || ''});
            });
            return r;
        }""")
        for t in tabs:
            print(f"   [{t['tag']}] {t['text']} | href={t['href'][:60]} class={t['class']} id={t['id']}")

        print("\n=== DIAGNOSTICO COMPLETO ===")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
