# 🎨 Guia de Instalação — Stable Diffusion para RPG-IA

## Sobre

Este guia ensina como instalar e configurar o **Stable Diffusion (Automatic1111 WebUI)** otimizado para sua **NVIDIA GeForce GTX 1660 (6GB VRAM)**.

Com esse setup, você poderá gerar retratos de personagens únicos e de alta qualidade, incluindo conteúdo adulto (+18), diretamente no RPG-IA.

---

## 📋 Pré-requisitos

✅ **Hardware:**
- GPU: NVIDIA GeForce GTX 1660 (6GB VRAM) ✓
- RAM: 16GB ✓
- Espaço em disco: ~10GB livres

✅ **Software:**
- Windows 10/11
- Python 3.10.6 (recomendado) ou 3.10.x
- Git for Windows
- CUDA Toolkit (será instalado automaticamente)

---

## 🚀 Instalação Passo a Passo

### Passo 1: Instalar Python 3.10.6

1. Baixar Python 3.10.6:
   - Link: https://www.python.org/downloads/release/python-3106/
   - Arquivo: `Windows installer (64-bit)`

2. Durante instalação:
   - ✅ Marcar **"Add Python 3.10 to PATH"**
   - ✅ Marcar **"Install for all users"** (opcional)
   - Clicar em **"Install Now"**

3. Verificar instalação:
   ```powershell
   python --version
   # Deve mostrar: Python 3.10.6
   ```

### Passo 2: Instalar Git

1. Baixar Git for Windows:
   - Link: https://git-scm.com/download/win
   - Arquivo: `64-bit Git for Windows Setup`

2. Instalar com configurações padrão (Next, Next, Finish)

3. Verificar instalação:
   ```powershell
   git --version
   # Deve mostrar: git version 2.x.x
   ```

### Passo 3: Baixar Automatic1111 WebUI

1. Criar pasta para o SD:
   ```powershell
   cd C:\
   mkdir StableDiffusion
   cd StableDiffusion
   ```

2. Clonar repositório:
   ```powershell
   git clone https://github.com/AUTOMATIC1111/stable-diffusion-webui.git
   cd stable-diffusion-webui
   ```

### Passo 4: Configurar para GTX 1660 (6GB VRAM)

Criar/editar arquivo `webui-user.bat` com as otimizações:

```batch
@echo off

set PYTHON=
set GIT=
set VENV_DIR=
set COMMANDLINE_ARGS=--api --medvram --xformers --no-half-vae

call webui.bat
```

**Explicação das flags:**
- `--api` → Habilita REST API (porta 7860) para integração com RPG-IA
- `--medvram` → Otimiza para GPUs com 4 a 6GB de VRAM
- `--xformers` → Acelera geração em ~30% (usa menos VRAM)
- `--no-half-vae` → Evita artefatos em imagens (problema comum em GPUs 16xx)

### Passo 5: Baixar Modelo SD 1.5

1. Criar pasta de modelos:
   ```powershell
   mkdir models\Stable-diffusion
   ```

2. Baixar modelo **SD 1.5** (leve e rápido na 6GB VRAM):
   - Link: https://huggingface.co/runwayml/stable-diffusion-v1-5
   - Arquivo: `v1-5-pruned-emaonly.safetensors` (~4GB)
   - Salvar em: `C:\StableDiffusion\stable-diffusion-webui\models\Stable-diffusion\`

**Alternativa (modelo uncensored para NSFW):**
- Link: https://civitai.com/models/4384/dreamshaper
- Arquivo: `dreamshaper_8.safetensors` (~2GB)
- Melhor para conteúdo +18

### Passo 6: (Opcional) Baixar LoRA de Fantasy Art

Para melhorar qualidade de personagens fantasy:

1. Criar pasta:
   ```powershell
   mkdir models\Lora
   ```

2. Baixar LoRA recomendado:
   - Link: https://civitai.com/models/14605/fantasy-character-portraits
   - Arquivo: `fantasyCharacterPortraits_v1.safetensors` (~150MB)
   - Salvar em: `models\Lora\`

### Passo 7: Primeira Execução

1. Executar `webui-user.bat` (duplo clique)

2. Aguardar instalação automática:
   - Criação do ambiente virtual Python
   - Download de dependências (torch, xformers, etc)
   - Primeira execução pode levar **10-20 minutos**

3. Quando ver mensagem:
   ```
   Running on local URL:  http://127.0.0.1:7860
   ```
   → Instalação concluída! ✅

4. Abrir navegador em: http://127.0.0.1:7860

### Passo 8: Testar Geração de Imagem

1. No WebUI:
   - **Prompt:** `portrait of a female elf mage, silver hair, purple eyes, fantasy art, detailed, 4k`
   - **Negative:** `blurry, low quality, deformed, ugly`
   - **Width:** 512
   - **Height:** 768
   - **Steps:** 25
   - **Sampler:** DPM++ 2M Karras
   - Clicar em **"Generate"**

2. Tempo esperado: **30-45 segundos** (primeira vez pode ser 1-2 min)

3. Se gerou imagem → **Tudo funcionando!** ✅

---

## ⚙️ Configurações Recomendadas

### Para Retratos de Personagens (RPG-IA)

```
Width: 512
Height: 768 (portrait ratio)
Steps: 25
CFG Scale: 7
Sampler: DPM++ 2M Karras
Batch Size: 1
Restore Faces: OFF (economiza VRAM)
Hires Fix: OFF (economiza VRAM)
```

### Prompt Template (NSFW Permitido)

```
portrait of a {gender} {race} {class}, 
{specific_features}, 
semi-realistic, detailed face, expressive eyes, good anatomy,
studio lighting, 4k, masterpiece, best quality,
beautiful, attractive, detailed body
```

**Negative Prompt:**
```
blurry, low quality, deformed, ugly, bad anatomy, bad hands,
extra fingers, watermark, signature, worst quality, lowres
```

---

## 🔥 Uso com RPG-IA

### Iniciar SD para integração

1. Rodar `webui-user.bat`
2. Aguardar mensagem: `Running on local URL: http://127.0.0.1:7860`
3. **Manter terminal aberto** (não fechar!)
4. Iniciar RPG-IA normalmente (`🎮 Iniciar RPG-IA.bat`)

### Gerar Retrato no RPG-IA

1. Selecionar personagem
2. Clicar em **"✨ Gerar Retrato com IA"**
3. Aguardar 30-60 segundos
4. Imagem aparece automaticamente!

**Primeira geração:** Mais lenta (carrega modelo na VRAM)  
**Gerações seguintes:** ~30s cada

---

## 🐛 Solução de Problemas

### Erro: "CUDA out of memory"

**Solução:** Adicionar `--lowvram` no `webui-user.bat`:
```batch
set COMMANDLINE_ARGS=--api --lowvram --xformers --no-half-vae
```
(Geração ficará mais lenta, mas funcionará)

### Erro: "Could not find a version that satisfies torch"

**Solução:** Instalar manualmente:
```powershell
pip install torch==2.0.1+cu118 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### Geração muito lenta (>2 min por imagem)

**Causas possíveis:**
1. GPU não está sendo usada → Verificar se CUDA instalado corretamente
2. `--medvram` não está nas flags → Adicionar no `webui-user.bat`
3. Steps muito alto → Reduzir para 20-25

**Verificar GPU sendo usada:**
- Abrir Task Manager (Ctrl+Shift+Esc)
- Aba "Performance" → GPU
- Durante geração, deve mostrar ~95-100%

### Imagens com artefatos/borrões

**Solução:** Garantir que `--no-half-vae` está nas flags

### RPG-IA não detecta SD

**Verificar:**
1. SD está rodando? (terminal aberto com `Running on local URL`)
2. Porta correta? Deve ser `7860`
3. Firewall bloqueando? Liberar porta 7860

**Testar manualmente:**
```powershell
curl http://127.0.0.1:7860/sdapi/v1/sd-models
```
Se retornar JSON → API funcionando ✅

---

## 📊 Performance Esperada (GTX 1660)

| Resolução | Steps | Tempo Médio |
|-----------|-------|-------------|
| 512x512   | 20    | 15-20s      |
| 512x768   | 25    | 30-40s      |
| 512x768   | 30    | 45-60s      |
| 768x768   | 25    | 60-90s      |

**Primeira geração da sessão:** +15-30s (carregamento do modelo)

---

## 🔞 Conteúdo Adulto (NSFW)

### Modelos Recomendados para NSFW

1. **DreamShaper** (melhor custo/benefício)
   - Link: https://civitai.com/models/4384/dreamshaper
   - Versão: 8
   - Tamanho: ~2GB
   - Qualidade: ⭐⭐⭐⭐⭐

2. **Realistic Vision** (mais realista)
   - Link: https://civitai.com/models/4201/realistic-vision
   - Versão: 5.1
   - Tamanho: ~2GB
   - Qualidade: ⭐⭐⭐⭐

3. **CyberRealistic** (semi-realista)
   - Link: https://civitai.com/models/15003/cyberrealistic
   - Versão: 3.3
   - Tamanho: ~2GB
   - Qualidade: ⭐⭐⭐⭐⭐

### Configuração NSFW no RPG-IA

O sistema **já está configurado** para permitir NSFW:
- Flag `nsfw: true` habilitada por padrão
- Negative prompt sem restrições de nudez
- Modelos uncensored recomendados acima

**Nenhuma configuração adicional necessária!**

---

## 📚 Recursos Extras

### Sites para Inspiração de Prompts

- **Lexica.art** → Galeria com prompts (SD oficial)
- **Civitai.com** → Modelos + exemplos de prompts
- **PromptHero.com** → Biblioteca de prompts testados

### Comunidade

- Reddit: r/StableDiffusion
- Discord: Automatic1111 oficial
- GitHub: Issues e troubleshooting

---

## 🎯 Checklist Final

Antes de usar com RPG-IA, confirme:

- [x] Python 3.10.6 instalado
- [x] Git instalado
- [x] Automatic1111 clonado
- [x] `webui-user.bat` com flags `--api --medvram --xformers`
- [x] Modelo SD baixado (SD 1.5 ou DreamShaper)
- [x] Primeira execução concluída (WebUI abriu)
- [x] Teste de geração funcionou
- [x] API acessível em http://127.0.0.1:7860

**Tudo OK?** Você está pronto para gerar retratos incríveis! 🚀

---

## 💡 Dicas Avançadas

### Batch Generation (Gerar várias de uma vez)

```python
# No backend, chamar múltiplas vezes:
for char in all_characters:
    generate_character_portrait(char.id, ...)
```

### Expressões (Variações do mesmo personagem)

```python
# Usar função generate_expression_variants:
variants = generate_expression_variants("warrior_123", base_prompt)
# Gera: neutral, happy, angry, sad, surprised, hurt
```

### LoRA Usage

Para usar LoRA no prompt:
```
<lora:fantasyCharacterPortraits_v1:0.7>
```
Adicionar no início do prompt (0.7 = strength)

---

**Divirta-se gerando personagens únicos! ⚔️🎨**
