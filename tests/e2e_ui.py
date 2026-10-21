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
import urllib.request
for _ in range(100):  # espera o servidor responder (em vez de um tempo fixo)
    try:
        urllib.request.urlopen("http://127.0.0.1:18000/api/status", timeout=1)
        break
    except Exception:
        time.sleep(0.2)

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
        check(page.locator(".char-card").count() == 6, "6 personagens listados")
        page.wait_for_function("document.getElementById('status-text').textContent.includes('fake-rp:8b')", timeout=5000)
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

        # Retrato e expressões: com as expressões geradas, o clima da resposta troca a imagem
        page.click("#btn-generate-portrait")
        page.wait_for_selector("#char-portrait-img", state="visible")
        page.wait_for_selector("#char-expressions .expr-add")
        page.click("#char-expressions .expr-add")
        page.wait_for_function("document.querySelectorAll('#char-expressions .expr-btn:not(.expr-add)').length === 6", timeout=20000)
        check(page.locator("#char-expressions .expr-add").count() == 0, "5 expressões geradas (mais a normal)")
        page.screenshot(path=f"{SHOTS}/10-expressions.png")

        page.fill("#user-input", "Olá Yasmin")
        page.keyboard.press("Enter")
        page.wait_for_selector(".message.assistant[data-index='2'] .bubble:not(.typing-cursor)")
        txt = page.inner_text(".message.assistant[data-index='2'] .bubble")
        check("pensando" not in txt and "Olá, viajante" in txt, "resposta em streaming sem bloco <think>")
        page.wait_for_function("document.getElementById('char-portrait-img').src.includes('__happy.png')", timeout=5000)
        check(True, "o clima da resposta trocou o retrato para a expressão feliz")
        check(page.locator(".message[data-index='2'] .msg-action[data-action=regenerate]").count() == 1,
              "botão regenerar na última resposta")
        page.screenshot(path=f"{SHOTS}/3-chat.png")

        # Regenerar
        page.hover(".message[data-index='2']")
        page.click(".message[data-index='2'] [data-action=regenerate]")
        page.wait_for_selector(".message.assistant[data-index='2'] .bubble:not(.typing-cursor)")
        check(page.locator(".message").count() == 3, "regenerar não duplica mensagens")
        page.wait_for_selector(".message[data-index='2'] .swipe-label")
        check(page.inner_text(".message[data-index='2'] .swipe-label") == "2/2", "regenerar guarda a versão anterior (2/2)")
        page.hover(".message[data-index='2']")
        page.click(".message[data-index='2'] [data-action=swipe-prev]")
        page.wait_for_function("document.querySelector(\".message[data-index='2'] .swipe-label\")?.textContent === '1/2'")
        check(True, "dá para voltar para a versão 1/2")
        page.hover(".message[data-index='2']")
        page.click(".message[data-index='2'] [data-action=swipe-next]")
        page.wait_for_function("document.querySelector(\".message[data-index='2'] .swipe-label\")?.textContent === '2/2'")

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
        check(page.input_value("#user-input") == "Olá Yasmin", "desfazer devolve o texto à caixa")

        # Cena
        page.fill("#user-input", "Vamos sentar")
        page.keyboard.press("Enter")
        page.wait_for_selector(".message.assistant[data-index='2'] .bubble:not(.typing-cursor)")
        page.click("#btn-scene")
        page.wait_for_selector(".scene-card img")
        check(True, "cena gerada e exibida")
        page.screenshot(path=f"{SHOTS}/4-scene.png")

        # Exportar a conversa baixa um arquivo de texto com a conversa
        with page.expect_download() as dl:
            page.click("[data-action=export-chat]")
        check(dl.value.suggested_filename.startswith("conversa-") and dl.value.suggested_filename.endswith(".md"),
              "exportar conversa baixa um .md")

        # Memória
        page.click("[data-action=open-memory]")
        page.wait_for_selector("#modal-memory", state="visible")
        page.fill("#memory-text", "Yasmin confia no jogador.")
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
        # Restaurar um backup (um zip pequeno com um personagem novo) mantém o que já existia
        import io, json as _json, zipfile as _zip
        _buf = io.BytesIO()
        with _zip.ZipFile(_buf, "w") as _z:
            _z.writestr("characters/ana.json", _json.dumps({"id": "ana", "name": "Ana Restaurada", "age": 30,
                "description": "d", "personality": "p", "scenario": "s", "first_message": "oi"}))
        page.set_input_files("#backup-file", files=[{"name": "b.zip", "mimeType": "application/zip", "buffer": _buf.getvalue()}])
        page.wait_for_selector(".toast:has-text('Backup restaurado')")
        check(True, "restaurar backup mostra o resultado")
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
        check(page.locator(".char-card").count() == 8, "personagem novo aparece na galeria (e a Ana restaurada)")
        page.screenshot(path=f"{SHOTS}/6-gallery.png")

        # Perfil do jogador: menor de idade é recusado; salvo, já vem na criação do personagem
        page.click("[data-action=open-profile]")
        page.wait_for_selector("#profile-form input")
        page.fill("#f-name", "Tonico Brasa")
        page.fill("#f-age", "16")
        page.click("[data-action=save-profile]")
        page.wait_for_selector(".toast-error")
        check("18" in page.inner_text(".toast-error"), "perfil com menos de 18 é recusado")
        page.fill("#f-age", "29")
        page.fill("#f-appearance", "alto, barba por fazer")
        page.fill("#f-about", "Fala pouco e rói a unha quando mente.")
        page.click("[data-action=save-profile]")
        page.wait_for_selector("#modal-profile", state="hidden")

        # Modo completo
        page.click(".char-card:has-text(\"Trama\")")
        page.click('[data-mode="full"]')
        page.wait_for_selector("#screen-create.active")
        check(page.input_value("#input-player-name") == "Tonico Brasa" and page.input_value("#input-player-age") == "29",
              "criação do personagem já vem com o perfil")
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

        # Inventário automático: a história entrega um item e ele aparece na lateral (modo completo)
        page.evaluate("fetch('/api/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({auto_inventory:true})})")
        page.fill("#user-input", "Pego a chave que ela me entrega")
        page.keyboard.press("Enter")
        page.wait_for_selector(".message.assistant[data-index='2'] .bubble:not(.typing-cursor)", timeout=40000)
        check(not page.is_disabled("#user-input"), "chat liberado ao fim da resposta")
        page.wait_for_selector(".toast:has-text('Inventário')")
        page.wait_for_selector("#inventory-list .inventory-item:has-text('Chave enferrujada')")
        check(True, "item dado pela história aparece no inventário")

        # Rolagem automática: o dado aparece e a resposta continua depois dele
        page.fill("#user-input", "Eu ataco o goblin com minha espada")
        page.keyboard.press("Enter")
        page.wait_for_selector(".message.assistant[data-index='4'] .bubble:not(.typing-cursor)", timeout=40000)
        check("Olá, viajante" in page.inner_text(".message.assistant[data-index='4'] .bubble"),
              "resposta chega depois da animação do dado")

        # Personagem de grupo no modo médio: uma barra por integrante do elenco
        page.click("[data-action=go-back]")
        page.click(".char-card:has-text(\"Javali\")")
        page.wait_for_selector("#prompt-warning", state="visible")
        check("tokens de contexto" in page.inner_text("#prompt-warning"), "aviso de personagem pesado aparece")
        page.click('[data-mode="medium"]')
        page.wait_for_selector("#screen-create.active")
        page.fill("#input-player-name", "Tonico")
        page.click("#race-grid .option-btn >> nth=0")
        page.click("#class-grid .option-btn >> nth=0")
        page.click("#btn-confirm-create")
        page.wait_for_selector("#cast-list .cast-row")
        check(page.locator("#cast-list .cast-row").count() == 7, "sidebar mostra 7 barras do elenco")
        check(not page.is_visible("#rel-section"), "medidor único some no personagem de grupo")
        page.fill("#user-input", "Obrigado, Yasmin, eu confio em você")
        page.keyboard.press("Enter")
        page.wait_for_selector(".message.assistant[data-index='2'] .bubble:not(.typing-cursor)")
        page.wait_for_selector("#cast-list .cast-row.up")
        check("Yasmin" in page.inner_text("#cast-list .cast-row.up"), "barra da Yasmin subiu depois do elogio")
        page.screenshot(path=f"{SHOTS}/8-cast.png")

        # Livro de fatos: abrir, adicionar uma entrada e salvar
        page.click("[data-action=open-lore]")
        page.wait_for_selector("#lore-list .lore-row")
        n = page.locator("#lore-list .lore-row").count()
        page.click("[data-action=add-lore]")
        page.fill("#lore-list .lore-row:last-child .lore-name", "Gato do balcão")
        page.fill("#lore-list .lore-row:last-child .lore-keys", "gato, balcão")
        page.fill("#lore-list .lore-row:last-child .lore-text", "Um gato cinza que dorme no balcão da tasca.")
        page.screenshot(path=f"{SHOTS}/9-lore.png")
        page.click("[data-action=save-lore]")
        page.wait_for_selector("#modal-lore", state="hidden")
        page.click("[data-action=open-lore]")
        page.wait_for_selector("#lore-list .lore-row")
        check(page.locator("#lore-list .lore-row").count() == n + 1, "entrada nova do livro de fatos foi salva")

        browser.close()
finally:
    server.terminate()
    fake.terminate()

real_errors = [e for e in errors if "favicon" not in e and "422" not in e]  # 422 esperados (validação 18+)
check(not real_errors, f"sem erros de console/JS {real_errors[:3]}")
print(f"\nscreenshots em {SHOTS}")
sys.exit(1 if failures else 0)
