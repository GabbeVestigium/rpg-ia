# ============================================================
# RPG IA — Script de Inicialização
# ============================================================
# Uso: powershell -ExecutionPolicy Bypass -File start.ps1
# ============================================================

$PythonExe = "C:\Users\gabri\AppData\Local\Programs\Python\Python312\python.exe"
if (-not (Test-Path $PythonExe)) {
    # Plano B: qualquer Python 3 no PATH
    $found = Get-Command python -ErrorAction SilentlyContinue
    if ($found) { $PythonExe = $found.Source }
}
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "  ⚔️  RPG IA — Iniciando..." -ForegroundColor Magenta
Write-Host ""

# ── 1. Verifica Python ───────────────────────────────────────
if (-not (Test-Path $PythonExe)) {
    Write-Host "[ERRO] Python não encontrado em $PythonExe" -ForegroundColor Red
    exit 1
}
$pyVer = & $PythonExe --version 2>&1
Write-Host "[OK] $pyVer" -ForegroundColor Green

# ── 2. Cria venv se não existir ──────────────────────────────
$VenvDir = Join-Path $ProjectDir "venv"
if (-not (Test-Path $VenvDir)) {
    Write-Host "[...] Criando ambiente virtual..." -ForegroundColor Yellow
    & $PythonExe -m venv $VenvDir
    Write-Host "[OK] venv criado" -ForegroundColor Green
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip    = Join-Path $VenvDir "Scripts\pip.exe"

# ── 3. Instala dependências ──────────────────────────────────
$ReqFile = Join-Path $ProjectDir "requirements.txt"
Write-Host "[...] Verificando dependências..." -ForegroundColor Yellow
& $VenvPip install -r $ReqFile -q --disable-pip-version-check
Write-Host "[OK] Dependências prontas" -ForegroundColor Green

# ── 4. Verifica Ollama ───────────────────────────────────────
Write-Host "[...] Verificando Ollama..." -ForegroundColor Yellow
try {
    $ollamaStatus = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 3
    $modelNames = $ollamaStatus.models | ForEach-Object { $_.name }
    Write-Host "[OK] Ollama online. Modelos: $($modelNames -join ', ')" -ForegroundColor Green
} catch {
    Write-Host "[AVISO] Ollama não está respondendo." -ForegroundColor Yellow
    Write-Host "        Iniciando ollama serve em background..." -ForegroundColor Yellow
    # Economiza VRAM na GPU de 6 GB (só vale quando o script é quem inicia o Ollama)
    $env:OLLAMA_FLASH_ATTENTION = "1"
    $env:OLLAMA_KV_CACHE_TYPE = "q8_0"
    Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 3
    Write-Host "[OK] Ollama iniciado" -ForegroundColor Green
}

# ── 5. Sobe o servidor FastAPI ───────────────────────────────
Write-Host ""
Write-Host "[...] Iniciando servidor RPG IA em http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "      Pressione Ctrl+C para parar." -ForegroundColor DarkGray
Write-Host ""

# Abre o browser após 2 segundos (tempo para o servidor subir)
Start-Job -ScriptBlock {
    Start-Sleep -Seconds 2
    Start-Process "http://127.0.0.1:8000"
} | Out-Null

# Roda o servidor (bloqueante — mantém o terminal aberto)
Set-Location $ProjectDir
& $VenvPython -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
