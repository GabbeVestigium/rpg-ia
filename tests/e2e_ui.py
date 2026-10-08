"""
Teste de ponta a ponta no navegador (Playwright) contra Ollama/SD falsos.
Uso: python tests/e2e_ui.py [pasta-de-screenshots]
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="shots-")
os.makedirs(SHOTS, exist_ok=True)

tmp = tempfile.mkdtemp(prefix="rpgia-e2e-")
data = os.path.join(tmp, "data")
shutil.copytree(os.path.join(ROOT, "data"), data, ignore=shutil.ignore_patterns("sessions"))
env = dict(os.environ, RPG_DATA_DIR=data, OLLAMA_BASE_URL="http://127.0.0.1:18434",
           SD_API_URL="http://127.0.0.1:18860", RPG_PORTRAITS_DIR=os.path.join(tmp, "portraits"), PYTHONPATH=ROOT + ":" + os.path.join(ROOT, "tests"))

fake = subprocess.Popen([sys.executable, "-c", (
    "import fake_services as f, time;"
    "f.serve(f.make_ollama(), 18434); f.serve(f.make_sd(), 18860); time.sleep(600)")], env=env)
server = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--port", "18000", "--log-level", "warning"],
                          cwd=ROOT, env=env)
time.sleep(3)

errors, failures = [], []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium", args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1400, "height": 850})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto("http://127.0.0.1:18000")
        page.wait_for_selector(".char-card")
        check(page.locator(".char-card").count() == 3, "3 personagens listados")
        check("fake-rp:8b" in page.inner_text("#status-text"), "status mostra modelo ativo")
        page.screenshot(path=f"{SHOTS}/1-select.png")

        # Narrativo
        page.click(".char-card:has-text(\"Trama\")")
        page.wait_for_selector("#modal-mode", state="visible")
        page.screenshot(path=f"{SHOTS}/2-mode.png")
        page.click('[data-mode="narrative"]')
        page.wait_for_selector("#screen-chat.active")
        check("Trama" in page.inner_text("#topbar-char-name"), "chat abriu com a Trama")
        check(page.locator(".message.assistant .bubble").count() >= 1, "mensagem de abertura renderizada")

        page.fill("#user-input", "Olá Dalila")
        page.keyboard.press("Enter")
        page.wait_for_selector(".message.assistant[data-index='2'] .bubble:not(.typing-cursor)")
        txt = page.inner_text(".message.assistant[data-index='2'] .bubble")
        check("pensando" not in txt and "Olá, viajante" in txt, "resposta em streaming sem bloco <think>")
        check(page.locator(".message[data-index='2'] .msg-action[data-action=regenerate]").count() == 1,
              "botão regenerar na última resposta")
        page.screenshot(path=f"{SHOTS}/3-chat.png")

        # Regenerar
        page.hover(".message[data-index='2']")
        page.click(".message[data-index='2'] [data-action=regenerate]")
        page.wait_for_selector(".message.assistant[data-index='2'] .bubble:not(.typing-cursor)")
        check(page.locator(".message").count() == 3, "regenerar não duplica mensagens")

        # Editar
        page.hover(".message[data-index='2']")
        page.click(".message[data-index='2'] [data-action=edit-message]")
        page.fill(".edit-area", "Texto *editado* pelo jogador.")
        page.click("[data-action=save-edit]")
        page.wait_for_selector(".message[data-index='2'] em")
        check("editado" in page.inner_text(".message[data-index='2'] .bubble"), "edição de mensagem salva")

        # Desfazer
        page.hover(".message[data-index='2']")
        page.click(".message[data-index='2'] [data-action=undo]")
        page.wait_for_function("document.querySelectorAll('.message').length === 1")
        check(page.input_value("#user-input") == "Olá Dalila", "desfazer devolve o texto à caixa")

        # Cena
        page.fill("#user-input", "Vamos sentar")
        page.keyboard.press("Enter")
        page.wait_for_selector(".message.assistant[data-index='2'] .bubble:not(.typing-cursor)")
        page.click("#btn-scene")
        page.wait_for_selector(".scene-card img")
        check(True, "cena gerada e exibida")
        page.screenshot(path=f"{SHOTS}/4-scene.png")

        # Memória
        page.click("[data-action=open-memory]")
        page.wait_for_selector("#modal-memory", state="visible")
        page.fill("#memory-text", "Dalila confia no jogador.")
        page.click("[data-action=save-memory]")
        page.wait_for_selector("#modal-memory", state="hidden")

        # Retomar sessão preserva cena e histórico
        page.click("[data-action=go-back]")
        page.wait_for_selector(".session-card")
        page.click(".session-card")
        page.wait_for_selector("#screen-chat.active")
        page.wait_for_selector(".scene-card img")
        check(page.locator(".message").count() == 3, "sessão retomada com histórico completo")

        # Configurações
        page.click("#screen-chat [data-action=open-settings]")
        page.wait_for_selector("#settings-form input")
        page.screenshot(path=f"{SHOTS}/5-settings.png", full_page=False)
        page.fill("#f-num_predict", "500")
        page.click("[data-action=save-settings]")
        page.wait_for_selector("#modal-settings", state="hidden")

        # Editor de personagem: menor de idade é recusado
        page.click("[data-action=go-back]")
        page.click("[data-action=new-character]")
        page.wait_for_selector("#editor-form input")
        page.fill("#f-name", "Teste")
        page.fill("#f-age", "17")
        page.fill("#f-description", "Descrição.")
        page.fill("#f-personality", "Calma.")
        page.fill("#f-scenario", "Estrada.")
        page.fill("#f-first_message", "*Acena*")
        page.click("[data-action=save-character]")
        page.wait_for_selector("#editor-error", state="visible")
        check("18" in page.inner_text("#editor-error"), "editor recusa personagem menor de 18")
        page.fill("#f-age", "27")
        page.click("[data-action=save-character]")
        page.wait_for_selector("#modal-editor", state="hidden")
        page.wait_for_selector(".char-card >> text=Teste")
        check(page.locator(".char-card").count() == 4, "personagem novo aparece na galeria")
        page.screenshot(path=f"{SHOTS}/6-gallery.png")

        # Modo completo
        page.click(".char-card:has-text(\"Trama\")")
        page.click('[data-mode="full"]')
        page.wait_for_selector("#screen-create.active")
        page.fill("#input-player-name", "Kael")
        page.click("#race-grid .option-btn >> nth=0")
        page.click("#class-grid .option-btn >> nth=0")
        page.fill("#input-player-age", "16")
        page.click("#btn-confirm-create")
        page.wait_for_selector(".toast-error")
        check("18" in page.inner_text(".toast-error"), "jogador menor de 18 é recusado")
        page.fill("#input-player-age", "28")
        page.click("#btn-confirm-create")
        page.wait_for_selector("#screen-chat.active")
        check(page.inner_text("#player-title").lower() == "kael", "jogador criado no modo completo")
        page.screenshot(path=f"{SHOTS}/7-full.png")

        # Rolagem automática: o dado aparece e a resposta continua depois dele
        page.fill("#user-input", "Eu ataco o goblin com minha espada")
        page.keyboard.press("Enter")
        page.wait_for_selector(".message.assistant[data-index='2'] .bubble:not(.typing-cursor)", timeout=40000)
        check("Olá, viajante" in page.inner_text(".message.assistant[data-index='2'] .bubble"),
              "resposta chega depois da animação do dado")

        # Personagem de grupo no modo médio: uma barra por integrante do elenco
        page.click("[data-action=go-back]")
        page.click(".char-card:has-text(\"Javali\")")
        page.click('[data-mode="medium"]')
        page.wait_for_selector("#screen-create.active")
        page.fill("#input-player-name", "Tonico")
        page.click("#race-grid .option-btn >> nth=0")
        page.click("#class-grid .option-btn >> nth=0")
        page.click("#btn-confirm-create")
        page.wait_for_selector("#cast-list .cast-row")
        check(page.locator("#cast-list .cast-row").count() == 7, "sidebar mostra 7 barras do elenco")
        check(not page.is_visible("#rel-section"), "medidor único some no personagem de grupo")
        page.fill("#user-input", "Obrigado, Dalila, eu confio em você")
        page.keyboard.press("Enter")
        page.wait_for_selector(".message.assistant[data-index='2'] .bubble:not(.typing-cursor)")
        page.wait_for_selector("#cast-list .cast-row.up")
        check("Dalila" in page.inner_text("#cast-list .cast-row.up"), "barra da Dalila subiu depois do elogio")
        page.screenshot(path=f"{SHOTS}/8-cast.png")

        browser.close()
finally:
    server.terminate()
    fake.terminate()

real_errors = [e for e in errors if "favicon" not in e and "422" not in e]  # 422 esperados (validação 18+)
check(not real_errors, f"sem erros de console/JS {real_errors[:3]}")
print(f"\nscreenshots em {SHOTS}")
sys.exit(1 if failures else 0)
