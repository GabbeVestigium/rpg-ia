# ⚔️ RPG IA

IA de roleplay local, sem censura, estilo visual novel, +18 (todos os personagens são adultos).
Roda 100% no seu PC: texto no Ollama, imagens no Stable Diffusion, voz no navegador ou no Piper.

## Requisitos
- Windows com Python 3.12+
- [Ollama](https://ollama.com) com um modelo de chat instalado
- Opcional: Stable Diffusion (Automatic1111) para retratos e cenas, ver `INSTALL_SD.md`
- Opcional: Piper para voz mais natural (sem ele, a voz do navegador funciona)

## Como rodar

```powershell
powershell -ExecutionPolicy Bypass -File start.ps1
```

O script cria o ambiente virtual, instala as dependências, inicia o Ollama se preciso, sobe o servidor em
http://127.0.0.1:8000 e abre o navegador. Ou use o `🎮 Iniciar RPG-IA.bat`.

## O que tem

- **Chat em streaming** com botões para **regenerar**, **desfazer**, **editar** qualquer mensagem e **parar** a resposta.
  O 🔄 guarda a versão anterior: use ◀ 2/3 ▶ para voltar e escolher a melhor resposta.
- **Memória de longo prazo**: a conversa inteira fica salva; o modelo recebe as mensagens recentes
  (ajustadas ao contexto) mais um resumo automático do resto. Você vê e edita o resumo em 🧠 Memória.
- **Meu perfil** (👤 na tela inicial): seu nome, idade (18+), aparência e jeito de agir, salvos uma vez. Os personagens passam a
  conhecer você em qualquer história, até no modo Narrativo, e a criação do personagem já vem preenchida.
- **Livro de fatos** (📚 Fatos): detalhes do mundo (lugares, grupos, regras) que só entram na conversa quando você os cita.
  O núcleo do mundo fica curto e o resto aparece sob demanda, o que poupa contexto na placa de 6 GB.
- **Aviso de personagem pesado**: se a ficha fixa ocupa contexto demais, o jogo avisa antes de começar.
- **Imagens**: retrato do personagem e botão 🖼️ Cena, que ilustra o momento atual mantendo o visual do personagem.
- **Voz**: 🔊 em cada resposta, ou leitura automática. Pode ler só as falas e pular as *ações*.
- **Galeria de personagens** com criador e editor na própria interface.
- **Configurações** na interface: modelo, criatividade, contexto, tamanho das respostas, imagens, voz.
- **RPG** em três modos: narrativo, médio e completo (atributos, HP, XP, quests, d20 automático).

## Modelo de texto (GTX 1660, 6 GB)

O `deepseek-r1:7b` é um modelo de raciocínio: gasta tokens "pensando" e costuma sair do personagem.
Para roleplay, um modelo de chat/RP de 7B a 12B rende mais. Instale e escolha em ⚙️ Configurações:

```powershell
ollama pull dolphin-mistral:7b      # exemplo de 7B sem censura que cabe inteiro na GPU
ollama pull hf.co/<usuario>/<repo>:Q4_K_M   # qualquer GGUF do Hugging Face
```

Os nomes mudam rápido; procure por modelos de roleplay em Q4_K_M. Na prática:
- **7B em Q4** cabe inteiro na VRAM com contexto 4096 (padrão).
- **8B a 12B** ficam no limite de 6 GB: se ficar lento, reduza o contexto ou use Q4 menor.
- Para economizar VRAM, inicie o Ollama com `OLLAMA_FLASH_ATTENTION=1` e `OLLAMA_KV_CACHE_TYPE=q8_0`
  (o `start.ps1` já faz isso quando é ele quem inicia o Ollama).
- O Ollama e o Stable Diffusion não cabem juntos na VRAM. Ao gerar imagem, o modelo de texto é
  descarregado automaticamente e volta na próxima mensagem (pode demorar alguns segundos).

## Voz com Piper (opcional)

1. Baixe o Piper e uma voz em português (ex: `pt_BR-faber-medium.onnx` com o `.onnx.json`).
2. Em ⚙️ Configurações > Voz, escolha a engine **Piper** e preencha os caminhos do `piper.exe` e do `.onnx`.

O Piper roda na CPU, sem tirar VRAM do texto e das imagens.

## Personagens

Use **➕ Novo personagem** na tela inicial (ou crie um `.json` em `data/characters/`).
Dicas para um personagem que soa bem:
- **Falas de exemplo** ensinam o estilo melhor que descrições.
- **Tags de aparência** (inglês, ex: `1girl, long black hair, violet eyes`) mantêm o rosto igual em todas as imagens.
- Idade mínima 18, textos que indiquem menor de idade são recusados ao salvar.

## Estrutura

```
backend/    FastAPI (routers, memória, cliente Ollama/SD/Piper)
frontend/   HTML + módulos ES, sem build
data/       characters/, worlds/, sessions/ (conversas), scenes/ (imagens), settings.json
tests/      pytest + teste de ponta a ponta no navegador
```

## Testes

```powershell
pip install -r requirements-dev.txt
python -m pytest tests -q          # usa Ollama e SD falsos, não precisa de GPU
python tests/e2e_ui.py             # teste no navegador (Playwright)
```
