$PythonExe = "C:\Users\gabri\AppData\Local\Programs\Python\Python312\python.exe"
$ProjectDir = "C:\Users\gabri\Documents\KIRO-IA\tools\rpg-ia"
$VenvDir = Join-Path $ProjectDir "venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip    = Join-Path $VenvDir "Scripts\pip.exe"

Write-Host "=== CRIANDO VENV ===" -ForegroundColor Cyan
if (-not (Test-Path $VenvDir)) {
    & $PythonExe -m venv $VenvDir
    Write-Host "venv criado." -ForegroundColor Green
} else {
    Write-Host "venv ja existe." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== INSTALANDO DEPENDENCIAS ===" -ForegroundColor Cyan
& $VenvPip install -r "$ProjectDir\requirements.txt"

Write-Host ""
Write-Host "=== TESTANDO IMPORTS ===" -ForegroundColor Cyan
& $VenvPython -c "import fastapi; import uvicorn; import httpx; import pydantic; print('Todos os imports OK')"

Write-Host ""
Write-Host "=== VERIFICANDO ESTRUTURA ===" -ForegroundColor Cyan
$dirs = @("backend","frontend","data\characters","data\worlds","data\sessions","frontend\static\css","frontend\static\js")
foreach ($d in $dirs) {
    $full = Join-Path $ProjectDir $d
    if (Test-Path $full) { Write-Host "OK: $d" -ForegroundColor Green }
    else { Write-Host "FALTA: $d" -ForegroundColor Red }
}

$files = @("backend\main.py","backend\config.py","backend\models.py","backend\session_manager.py","backend\ollama_client.py","backend\character_manager.py","frontend\index.html","frontend\static\css\style.css","frontend\static\js\app.js","data\characters\lyra.json","data\characters\vex.json","data\characters\morrigan.json")
foreach ($f in $files) {
    $full = Join-Path $ProjectDir $f
    if (Test-Path $full) { Write-Host "OK: $f" -ForegroundColor Green }
    else { Write-Host "FALTA: $f" -ForegroundColor Red }
}

Write-Host ""
Write-Host "=== TESTANDO SINTAXE PYTHON ===" -ForegroundColor Cyan
Set-Location $ProjectDir
& $VenvPython -c "
import sys
sys.path.insert(0, r'$ProjectDir')
from backend.config import *
from backend.models import *
from backend.session_manager import *
from backend.character_manager import *
from backend.ollama_client import *
print('Todos os modulos carregaram sem erro')
"

Write-Host ""
Write-Host "=== OLLAMA STATUS ===" -ForegroundColor Cyan
try {
    $r = Invoke-RestMethod "http://localhost:11434/api/tags" -TimeoutSec 3
    Write-Host "Ollama ONLINE" -ForegroundColor Green
    $r.models | ForEach-Object { Write-Host "  Modelo: $($_.name)" }
} catch {
    Write-Host "Ollama OFFLINE - rode 'ollama serve' antes de iniciar" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== PRONTO ===" -ForegroundColor Magenta
Write-Host "Para iniciar o servidor rode:" -ForegroundColor White
Write-Host "  powershell -ExecutionPolicy Bypass -File start.ps1" -ForegroundColor Cyan
