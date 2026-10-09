"""
Abre o painel num navegador sem tela para que o Streamlit Community Cloud não o coloque para dormir.
Se o app já estiver dormindo, clica em "Yes, get this app back up!" e espera ele carregar.

Roda pelo GitHub Actions (.github/workflows/manter-acordado.yml). Uso local:
    APP_URL=https://seu-app.streamlit.app python scripts/manter_acordado.py
"""
import os
import re
import sys

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL", "").strip()
MARCA = "ELEIÇÕES"  # texto do cabeçalho do painel: se aparecer, o app está no ar


def app_carregou(page) -> bool:
    # no Streamlit Cloud o app roda dentro de um iframe; procura o texto em todos os frames
    for frame in page.frames:
        try:
            if MARCA in frame.inner_text("body", timeout=2000):
                return True
        except Exception:
            pass
    return False


def main() -> int:
    if not URL:
        print("Defina APP_URL com o endereço do app.")
        return 1
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        page = navegador.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=120_000)

        botao = page.get_by_role("button", name=re.compile(r"get this app back up", re.I))
        try:
            botao.wait_for(timeout=15_000)
            print("App estava dormindo: clicando para acordar.")
            botao.click()
        except PWTimeout:
            print("App já estava acordado.")

        # espera até 3 minutos o painel aparecer (acordar pode levar ~1 minuto)
        for _ in range(36):
            if app_carregou(page):
                print("Painel no ar.")
                navegador.close()
                return 0
            page.wait_for_timeout(5_000)
        print("O painel não apareceu em 3 minutos.")
        page.screenshot(path="falha.png", full_page=True)
        navegador.close()
        return 1


if __name__ == "__main__":
    sys.exit(main())
