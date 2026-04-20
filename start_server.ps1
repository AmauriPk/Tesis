# ========================================
# Script de Inicio PowerShell - Sistema Web RPAS
# ========================================
# Ejecución: .\start_server.ps1

# Configuración
$projectRoot = Get-Location
$venvPath = Join-Path $projectRoot "venv_new"
$appFile = Join-Path $projectRoot "app.py"

# Colores para PowerShell
function Write-Info {
    Write-Host "[*] $args" -ForegroundColor Cyan
}

function Write-Success {
    Write-Host "[OK] $args" -ForegroundColor Green
}

function Write-Error-Custom {
    Write-Host "[ERROR] $args" -ForegroundColor Red
}

# Banner
Clear-Host
Write-Host "========================================"
Write-Host "  SISTEMA DE DETECCION DE DRONES RPAS  "
Write-Host "========================================"
Write-Host ""

# Verificar directorio correcto
if (-not (Test-Path $venvPath)) {
    Write-Error-Custom "Directorio 'venv_new' no encontrado."
    Write-Info "Ejecuta este script desde c:\Users\amaur\Desktop\Proyecto01\"
    Read-Host "Presiona Enter para salir"
    exit 1
}

# Verificar app.py
if (-not (Test-Path $appFile)) {
    Write-Error-Custom "Archivo 'app.py' no encontrado."
    Read-Host "Presiona Enter para salir"
    exit 1
}

# Activar entorno virtual
Write-Info "Activando entorno virtual..."
$activateScript = Join-Path $venvPath "Scripts" "Activate.ps1"

try {
    & $activateScript
    Write-Success "Entorno virtual activado."
} catch {
    Write-Error-Custom "No se pudo activar el entorno virtual."
    Read-Host "Presiona Enter para salir"
    exit 1
}

# Verificar dependencias
Write-Info "Verificando dependencias..."
$checkDeps = python -c "import flask; import ultralytics; import cv2; print('OK')" 2>$null

if ($checkDeps -ne "OK") {
    Write-Host "[WARNING] Algunas dependencias no están instaladas." -ForegroundColor Yellow
    Write-Info "Instalando dependencias..."
    pip install -r requirements.txt --quiet
    Write-Success "Dependencias instaladas."
}

# Iniciar servidor
Write-Host ""
Write-Host "========================================"
Write-Host "  INICIANDO SERVIDOR FLASK..." -ForegroundColor Green
Write-Host "========================================"
Write-Host ""
Write-Host "[INFO] Servidor disponible en: http://localhost:5000" -ForegroundColor Cyan
Write-Host "[INFO] Presiona Ctrl+C para detener el servidor" -ForegroundColor Yellow
Write-Host ""

# Ejecutar Flask
python app.py

Read-Host "Presiona Enter para salir"
