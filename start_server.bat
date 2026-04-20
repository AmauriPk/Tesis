@echo off
REM ========================================
REM Script de Inicio - Sistema Web RPAS
REM ========================================

setlocal enabledelayedexpansion

REM Colores para consola
REM Esta es una simple versión sin colores para Windows
cls
echo ========================================
echo  SISTEMA DE DETECCION DE DRONES RPAS
echo ========================================
echo.

REM Verificar que estamos en el directorio correcto
if not exist "venv_new" (
    echo ERROR: Directorio 'venv_new' no encontrado.
    echo Ejecuta este script desde c:\Users\amaur\Desktop\Proyecto01\
    pause
    exit /b 1
)

REM Verificar que app.py existe
if not exist "app.py" (
    echo ERROR: Archivo 'app.py' no encontrado.
    pause
    exit /b 1
)

echo [*] Activando entorno virtual...
call venv_new\Scripts\activate.bat

if errorlevel 1 (
    echo ERROR: No se pudo activar el entorno virtual.
    pause
    exit /b 1
)

echo [OK] Entorno virtual activado.
echo.

REM Verificar que Flask está instalado
echo [*] Verificando dependencias...
python -c "import flask; import ultralytics; import cv2; print('[OK] Todas las dependencias disponibles.')" 2>nul

if errorlevel 1 (
    echo [WARNING] Algunas dependencias no están instaladas.
    echo [*] Instalando dependencias...
    pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo ERROR: No se pudieron instalar las dependencias.
        pause
        exit /b 1
    )
    echo [OK] Dependencias instaladas.
)

echo.
echo ========================================
echo  INICIANDO SERVIDOR FLASK...
echo ========================================
echo.
echo [INFO] Servidor disponible en: http://localhost:5000
echo [INFO] Presiona Ctrl+C para detener el servidor
echo.

REM Iniciar servidor Flask
python app.py

pause
