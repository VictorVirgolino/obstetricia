"""
Script de exploração do módulo Diretoria do sistema hospitalar.
Captura screenshots e HTML das páginas para entender a estrutura.
"""
import asyncio
from playwright.async_api import async_playwright

LOGIN = "ItaloCunha"
PASSWORD = "10208535497"
LOGIN_URL = "http://177.10.203.220/projetoisea/PAGINA%20DE%20LOGIN.php"


async def explore():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        # 1. Login
        print("1. Acessando página de login...")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
        await page.screenshot(path="explore_01_login.png", full_page=True)

        # Preencher credenciais
        await page.fill('input[name="usuario"]', LOGIN)
        await page.fill('input[name="senha"]', PASSWORD)

        # Verificar opções do radio "grau"
        grau_options = await page.evaluate("""
            () => {
                const radios = document.querySelectorAll('input[name="grau"]');
                return Array.from(radios).map(r => ({value: r.value, id: r.id, label: r.parentElement?.textContent?.trim()}));
            }
        """)
        print(f"   Opções de grau (radio): {grau_options}")

        # Verificar opções do select setor
        await page.click('input[name="grau"][value="5"]')
        await page.wait_for_selector('select#setor')
        setor_options = await page.evaluate("""
            () => {
                const sel = document.querySelector('select#setor');
                return Array.from(sel.options).map(o => ({value: o.value, text: o.text}));
            }
        """)
        print(f"   Opções de setor: {setor_options}")

        # Tentar selecionar "Diretoria" ou similar
        diretoria_value = None
        for opt in setor_options:
            if 'diret' in opt['text'].lower():
                diretoria_value = opt['value']
                print(f"   -> Encontrado setor Diretoria: value='{diretoria_value}', text='{opt['text']}'")
                break

        if not diretoria_value:
            print("   AVISO: Não encontrou 'Diretoria' no select. Opções disponíveis:")
            for opt in setor_options:
                print(f"      - value='{opt['value']}' text='{opt['text']}'")
            # Tentar com outro grau
            for grau in grau_options:
                print(f"\n   Tentando grau {grau['value']} ({grau['label']})...")
                await page.click(f'input[name="grau"][value="{grau["value"]}"]')
                await asyncio.sleep(1)
                setor_options2 = await page.evaluate("""
                    () => {
                        const sel = document.querySelector('select#setor');
                        if (!sel) return [];
                        return Array.from(sel.options).map(o => ({value: o.value, text: o.text}));
                    }
                """)
                print(f"   Opções de setor para grau {grau['value']}: {setor_options2}")
                for opt in setor_options2:
                    if 'diret' in opt['text'].lower():
                        diretoria_value = opt['value']
                        print(f"   -> Encontrado! value='{diretoria_value}', text='{opt['text']}'")
                        break
                if diretoria_value:
                    break

        if not diretoria_value:
            print("\n   ERRO: Não conseguiu encontrar módulo Diretoria em nenhum grau.")
            print("   Fazendo login com setor padrão para explorar navegação...")
            await page.click('input[name="grau"][value="5"]')
            await page.wait_for_selector('select#setor')
            await page.select_option('select#setor', value="Contas")
        else:
            await page.select_option('select#setor', value=diretoria_value)

        await page.screenshot(path="explore_02_login_preenchido.png", full_page=True)
        await page.click('.login100-form-btn')
        await page.wait_for_load_state("networkidle")
        await page.screenshot(path="explore_03_pos_login.png", full_page=True)

        print(f"\n2. Página pós-login: {page.url}")

        # Capturar toda a estrutura de navegação
        nav_html = await page.evaluate("""
            () => {
                // Capturar sidebar/menu
                const sidebar = document.querySelector('.sidebar, .nav, .menu, [class*="sidebar"], [class*="nav"], [class*="menu"]');
                if (sidebar) return sidebar.outerHTML;
                // Fallback: capturar todos os links
                const links = document.querySelectorAll('a');
                return Array.from(links).map(a => ({href: a.href, text: a.textContent.trim(), class: a.className}));
            }
        """)
        print(f"   Navegação encontrada: {str(nav_html)[:2000]}")

        # Capturar todos os links da página
        all_links = await page.evaluate("""
            () => {
                return Array.from(document.querySelectorAll('a')).map(a => ({
                    href: a.href,
                    text: a.textContent.trim().substring(0, 100),
                    parent_text: a.parentElement?.textContent?.trim().substring(0, 100) || ''
                }));
            }
        """)
        print(f"\n3. Todos os links da página ({len(all_links)}):")
        for link in all_links:
            if link['text']:
                print(f"   - [{link['text']}] -> {link['href']}")

        # Procurar por "Relatórios Analíticos", "NAQ", "Internação", "Urgência"
        keywords = ['relat', 'anali', 'naq', 'intern', 'urgenc', 'qualidade', 'estatist']
        relevant_links = [l for l in all_links if any(k in l['text'].lower() or k in l['parent_text'].lower() for k in keywords)]
        print(f"\n4. Links relevantes ({len(relevant_links)}):")
        for link in relevant_links:
            print(f"   - [{link['text']}] -> {link['href']}")

        # Se encontrou links relevantes, navegar para eles
        for i, link in enumerate(relevant_links[:5]):
            if link['href'] and link['href'] != '#' and 'javascript:void' not in link['href']:
                print(f"\n5.{i+1}. Navegando para: {link['text']} ({link['href']})")
                try:
                    await page.goto(link['href'], wait_until="networkidle", timeout=30000)
                    await page.screenshot(path=f"explore_04_page_{i}.png", full_page=True)

                    # Capturar estrutura da página
                    page_structure = await page.evaluate("""
                        () => {
                            const result = {};
                            // Forms
                            const forms = document.querySelectorAll('form');
                            result.forms = Array.from(forms).map(f => ({
                                action: f.action,
                                method: f.method,
                                inputs: Array.from(f.querySelectorAll('input, select, textarea')).map(el => ({
                                    tag: el.tagName,
                                    type: el.type,
                                    name: el.name,
                                    id: el.id,
                                    options: el.tagName === 'SELECT' ? Array.from(el.options).map(o => ({value: o.value, text: o.text})) : undefined
                                }))
                            }));
                            // Tables
                            const tables = document.querySelectorAll('table');
                            result.tables = Array.from(tables).map(t => {
                                const headers = Array.from(t.querySelectorAll('th')).map(th => th.textContent.trim());
                                const rowCount = t.querySelectorAll('tr').length;
                                const firstRows = Array.from(t.querySelectorAll('tr')).slice(0, 3).map(tr =>
                                    Array.from(tr.querySelectorAll('td, th')).map(td => td.textContent.trim().substring(0, 50))
                                );
                                return {headers, rowCount, firstRows};
                            });
                            // Selects
                            result.selects = Array.from(document.querySelectorAll('select')).map(s => ({
                                name: s.name, id: s.id,
                                options: Array.from(s.options).map(o => ({value: o.value, text: o.text}))
                            }));
                            // Date inputs
                            result.dateInputs = Array.from(document.querySelectorAll('input[type="date"], input[name*="data"], input[name*="dt"], input[id*="data"], input[id*="dt"]')).map(i => ({
                                name: i.name, id: i.id, type: i.type, value: i.value, placeholder: i.placeholder
                            }));
                            return result;
                        }
                    """)
                    print(f"   Estrutura: forms={len(page_structure.get('forms',[]))}, tables={len(page_structure.get('tables',[]))}")
                    print(f"   Selects: {page_structure.get('selects', [])}")
                    print(f"   Date inputs: {page_structure.get('dateInputs', [])}")
                    if page_structure.get('tables'):
                        for ti, table in enumerate(page_structure['tables']):
                            print(f"   Table {ti}: headers={table['headers']}, rows={table['rowCount']}")
                            for row in table['firstRows'][:2]:
                                print(f"      Row: {row}")
                    if page_structure.get('forms'):
                        for fi, form in enumerate(page_structure['forms']):
                            print(f"   Form {fi}: action={form['action']}, inputs={len(form['inputs'])}")
                            for inp in form['inputs']:
                                print(f"      {inp['tag']} name={inp['name']} id={inp['id']} type={inp.get('type','')}")
                                if inp.get('options'):
                                    print(f"         Options: {inp['options'][:10]}")
                except Exception as e:
                    print(f"   Erro ao navegar: {e}")

        # Salvar HTML completo da última página
        html = await page.content()
        with open("explore_page_html.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("\n6. HTML salvo em explore_page_html.html")

        # Tentar trocar de módulo se estamos em Contas
        print("\n7. Tentando trocar módulo via interface...")
        # Procurar select de módulo/setor na página atual
        module_selects = await page.evaluate("""
            () => {
                return Array.from(document.querySelectorAll('select')).map(s => ({
                    name: s.name, id: s.id,
                    options: Array.from(s.options).map(o => ({value: o.value, text: o.text}))
                }));
            }
        """)
        print(f"   Selects encontrados: {module_selects}")

        # Procurar botão "alterar" ou link para trocar módulo
        alter_elements = await page.evaluate("""
            () => {
                const elements = [];
                document.querySelectorAll('a, button, input[type="submit"], input[type="button"]').forEach(el => {
                    const text = (el.textContent || el.value || '').trim().toLowerCase();
                    if (text.includes('alter') || text.includes('modulo') || text.includes('módulo') || text.includes('trocar') || text.includes('setor')) {
                        elements.push({
                            tag: el.tagName,
                            text: (el.textContent || el.value || '').trim(),
                            href: el.href || '',
                            id: el.id,
                            name: el.name || '',
                            class: el.className
                        });
                    }
                });
                return elements;
            }
        """)
        print(f"   Elementos 'alterar/modulo': {alter_elements}")

        print("\n--- Exploração concluída ---")
        print("Verifique os screenshots explore_*.png para visualização")

        await asyncio.sleep(3)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(explore())
