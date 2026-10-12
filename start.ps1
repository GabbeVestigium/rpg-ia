# ============================================================
# RPG IA: Script de Inicialização
# ============================================================
# Uso: powershell -ExecutionPolicy Bypass -File start.ps1
# Sai com código 1 quando algo falha (o .bat então pausa para dar tempo de ler o erro).
# ============================================================

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppUrl = "http://127.0.0.1:8000"

function Falha($msg) {
    Write-Host "[ERRO] $msg" -ForegroundColor Red
    exit 1
}

function Responde($url) {
    try { Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 2 | Out-Null; return $true } catch { return $false }
}

Write-Host ""
Write-Host "  ⚔️  RPG IA: Iniciando..." -ForegroundColor Magenta
Write-Host ""

# ── 0. Já está rodando? (ex: segundo duplo clique) ───────────
if (Responde $AppUrl) {
    Write-Host "[OK] O RPG IA já está rodando. Abrindo o navegador..." -ForegroundColor Green
    Start-Process $AppUrl
    exit 0
}

# ── 1. Cria venv se não existir (só aqui precisa do Python do sistema) ──
$VenvDir = Join-Path $ProjectDir "venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    # Prefere o launcher "py"; ignora o atalho da Microsoft Store (WindowsApps), que não é um Python de verdade
    $PythonExe = (Get-Command py -ErrorAction SilentlyContinue).Source
    $PyArgs = @("-3")
    if (-not $PythonExe) {
        $PythonExe = Get-Command python -All -ErrorAction SilentlyContinue |
            Where-Object { $_.Source -notlike "*\WindowsApps\*" } |
            Select-Object -First 1 -ExpandProperty Source
        $PyArgs = @()
    }
    if (-not $PythonExe) { Falha "Python 3 não encontrado. Instale em python.org (marque 'Add to PATH') e rode de novo." }
    Write-Host "[...] Criando ambiente virtual com $PythonExe..." -ForegroundColor Yellow
    & $PythonExe @PyArgs -m venv $VenvDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPython)) { Falha "Não consegui criar o ambiente virtual (venv)." }
    Write-Host "[OK] venv criado" -ForegroundColor Green
}
$pyVer = & $VenvPython --version 2>&1
if ($LASTEXITCODE -ne 0) { Falha "O ambiente virtual está quebrado. Apague a pasta 'venv' e rode de novo." }
Write-Host "[OK] $pyVer" -ForegroundColor Green

# ── 2. Instala dependências (só quando o requirements.txt mudou) ──
$ReqFile = Join-Path $ProjectDir "requirements.txt"
$Stamp = Join-Path $VenvDir ".requirements.sha256"
$ReqHash = (Get-FileHash $ReqFile -Algorithm SHA256).Hash
if ((Test-Path $Stamp) -and ((Get-Content $Stamp -Raw).Trim() -eq $ReqHash)) {
    Write-Host "[OK] Dependências já instaladas" -ForegroundColor Green
} else {
    Write-Host "[...] Instalando dependências..." -ForegroundColor Yellow
    & $VenvPython -m pip install -r $ReqFile -q --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { Falha "A instalação das dependências (pip) falhou. Veja a mensagem acima e confira a internet." }
    Set-Content -Path $Stamp -Value $ReqHash
    Write-Host "[OK] Dependências prontas" -ForegroundColor Green
}

# ── 3. Verifica Ollama ───────────────────────────────────────
Write-Host "[...] Verificando Ollama..." -ForegroundColor Yellow
$OllamaTags = "http://localhost:11434/api/tags"
if (-not (Responde $OllamaTags)) {
    Write-Host "        Ollama não está respondendo. Iniciando ollama serve em background..." -ForegroundColor Yellow
    # Economiza VRAM na GPU de 6 GB (só vale quando o script é quem inicia o Ollama)
    $env:OLLAMA_FLASH_ATTENTION = "1"
    $env:OLLAMA_KV_CACHE_TYPE = "q8_0"
    try {
        Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden -ErrorAction Stop
        for ($i = 0; $i -lt 20 -and -not (Responde $OllamaTags); $i++) { Start-Sleep -Seconds 1 }
    } catch {
        Write-Host "[AVISO] Comando 'ollama' não encontrado. Instale em ollama.com." -ForegroundColor Yellow
    }
}
try {
    $modelNames = (Invoke-RestMethod -Uri $OllamaTags -TimeoutSec 3).models | ForEach-Object { $_.name }
    Write-Host "[OK] Ollama online. Modelos: $($modelNames -join ', ')" -ForegroundColor Green
} catch {
    Write-Host "[AVISO] Ollama não respondeu. O app abre, mas o chat só funciona com o Ollama rodando." -ForegroundColor Yellow
}

# ── 4. Celular pelo Tailscale (opcional) ─────────────────────
# O `tailscale serve` cria um endereço https que só os aparelhos da sua conta Tailscale abrem
# e repassa para 127.0.0.1:8000. O servidor continua fechado para a rede.
$TailscaleExe = (Get-Command tailscale -ErrorAction SilentlyContinue).Source
if (-not $TailscaleExe -and (Test-Path "C:\Program Files\Tailscale\tailscale.exe")) {
    $TailscaleExe = "C:\Program Files\Tailscale\tailscale.exe"
}
if ($TailscaleExe) {
    $tsStatus = $null
    try { $tsStatus = & $TailscaleExe status --json 2>$null | ConvertFrom-Json } catch { }
    if ($tsStatus -and $tsStatus.BackendState -eq "Running") {
        Write-Host "[...] Ligando o acesso pelo celular (Tailscale)..." -ForegroundColor Yellow
        # Na primeira vez o Tailscale pode mostrar um link para liberar o HTTPS: abra e aprove.
        & $TailscaleExe serve --bg 8000
        if ($LASTEXITCODE -eq 0) {
            $PhoneUrl = "https://" + $tsStatus.Self.DNSName.TrimEnd(".")
            Write-Host "[OK] No celular, abra: $PhoneUrl" -ForegroundColor Green
        } else {
            Write-Host "[AVISO] O Tailscale não ligou o acesso. Rode este script como administrador uma vez." -ForegroundColor Yellow
        }
    } else {
        Write-Host "[INFO] Tailscale instalado, mas desligado. Abra o Tailscale e entre na conta para usar no celular." -ForegroundColor DarkGray
    }
} else {
    Write-Host "[INFO] Para jogar no celular, instale o Tailscale (veja README.md)." -ForegroundColor DarkGray
}

# ── 5. Sobe o servidor FastAPI ───────────────────────────────
Write-Host ""
Write-Host "[...] Iniciando servidor RPG IA em $AppUrl" -ForegroundColor Cyan
Write-Host "      Pressione Ctrl+C para parar." -ForegroundColor DarkGray
Write-Host ""

# Abre o navegador só quando o servidor responder (até ~30 s)
Start-Job -ArgumentList $AppUrl -ScriptBlock {
    param($url)
    for ($i = 0; $i -lt 30; $i++) {
        try { Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 2 | Out-Null; Start-Process $url; return } catch { Start-Sleep -Seconds 1 }
    }
} | Out-Null

# Roda o servidor (bloqueante: mantém o terminal aberto)
Set-Location $ProjectDir
& $VenvPython -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
if ($LASTEXITCODE -ne 0) { Falha "O servidor parou com erro (código $LASTEXITCODE). Veja a mensagem acima." }
