"""Quick check for CPN procedure cost structure."""
import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        # Init session
        await page.goto("http://sigtap.datasus.gov.br/tabela-unificada/app/sec/inicio.jsp", wait_until="networkidle", timeout=60000)
        link = await page.query_selector('a:has-text("Acessar a Tabela Unificada")')
        if link:
            await link.click()
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
        # Go to CPN procedure
        await page.goto("http://sigtap.datasus.gov.br/tabela-unificada/app/sec/procedimento/exibir/0310010055/03/2026", wait_until="networkidle")
        await asyncio.sleep(1)
        await page.screenshot(path="diag_cpn_screenshot.png", full_page=True)
        # Extract all values
        vals = await page.evaluate("""() => {
            const ids = ['valorSA', 'valorSH', 'valorSA_Total', 'valorSP', 'totalInternacao', 'totalAmbulatorio'];
            const res = {};
            ids.forEach(id => {
                const el = document.getElementById(id);
                res[id] = el ? el.innerText.trim() : 'NOT FOUND';
            });
            // Also try to get all text with R$
            const money = [];
            const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            while (walk.nextNode()) {
                const t = walk.currentNode.textContent.trim();
                if (t.match(/R\\$/)) {
                    const p = walk.currentNode.parentElement;
                    money.push(t + ' [' + p?.tagName + '#' + (p?.id || '') + '.' + (p?.className || '') + ']');
                }
            }
            res._money = money;
            return res;
        }""")
        print("Values:", vals)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
