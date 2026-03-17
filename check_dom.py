from playwright.sync_api import sync_playwright
import time

LOGIN = "ItaloCunha"
PASSWORD = "10208535497"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("http://177.10.203.220/projetoisea/PAGINA%20DE%20LOGIN.php")
    
    # Login
    page.fill('input[name="usuario"]', LOGIN)
    page.fill('input[name="senha"]', PASSWORD)
    page.click('input[name="grau"][value="5"]')
    page.wait_for_selector('select#setor')
    page.select_option('select#setor', value="Contas")
    page.click('.login100-form-btn')
    page.wait_for_load_state("networkidle")
    
    # Go to Reports
    page.goto("http://177.10.203.220/projetoisea/relasisaih.php?operacao=R")
    page.wait_for_load_state("networkidle")
    
    content = page.content()
    with open("report_dom.html", "w", encoding="utf-8") as f:
        f.write(content)
    browser.close()
    print("Report DOM saved to report_dom.html")
