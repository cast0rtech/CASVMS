@echo off
setlocal enabledelayedexpansion
title CASVMS - Industrial Video Management System

echo ==============================================================================
echo   CASVMS - Industrial AI Video Management System (Edge AI Zero-Cloud)
echo ==============================================================================
echo.

:: 1. Verificar Docker
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker no esta instalado o no se encuentra en el PATH.
    echo Por favor, instala e inicia Docker Desktop y vuelve a ejecutar este lanzador.
    pause
    exit /b 1
)

:: Determinar directorio raiz
set "ROOT_DIR=%~dp0"
if exist "%~dp0..\..\docker-compose.yml" (
    pushd "%~dp0..\.."
    set "ROOT_DIR=!CD!\"
    popd
) else if exist "%~dp0..\docker-compose.yml" (
    pushd "%~dp0.."
    set "ROOT_DIR=!CD!\"
    popd
)

:: 2. Levantar la infraestructura backend si no esta activa
echo [1/3] Comprobando infraestructura backend (FastAPI, OpenVINO, InfluxDB, Grafana)...
if exist "%ROOT_DIR%docker-compose.yml" (
    docker compose -f "%ROOT_DIR%docker-compose.yml" up -d
) else (
    docker compose up -d
)

:: 3. Esperar a que el motor FastAPI y Frontend esten listos
echo [2/3] Esperando a que el backend (8001) y frontend (1420) esten en linea...
set /a retries=0
:WAIT_API
curl -s -f http://localhost:8001/health >nul 2>&1
if %errorlevel% equ 0 (
    curl -s -f http://localhost:1420 >nul 2>&1
    if !errorlevel! equ 0 (
        echo [OK] Motor VMS e Interfaz de Usuario en linea y saludables.
        goto LAUNCH_APP
    )
)
set /a retries+=1
if !retries! geq 30 (
    echo [ADVERTENCIA] Los servicios tardaron mas de lo esperado en iniciar. Iniciando interfaz de todos modos...
    goto LAUNCH_APP
)
timeout /t 1 >nul
goto WAIT_API

:LAUNCH_APP
echo [3/3] Iniciando aplicacion de escritorio CASVMS...
echo.

:: Limpiar posibles instancias previas y procesos huerfanos de WebView2 que bloqueen el perfil de datos
taskkill /f /im CASVMS.exe >nul 2>&1
taskkill /f /im casvms-desktop.exe >nul 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name like '%%webview%%'\" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'com\.casvms\.desktop' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
powershell -NoProfile -Command "if (Test-Path \"$env:LOCALAPPDATA\com.casvms.desktop\EBWebView\Default\LOCK\") { Remove-Item \"$env:LOCALAPPDATA\com.casvms.desktop\EBWebView\Default\LOCK\" -Force -ErrorAction SilentlyContinue }" >nul 2>&1

set "EXE_PATH="
set "EXE_DIR="

if exist "%~dp0CASVMS.exe" (
    set "EXE_PATH=%~dp0CASVMS.exe"
    set "EXE_DIR=%~dp0"
) else if exist "%ROOT_DIR%release\windows\CASVMS.exe" (
    set "EXE_PATH=%ROOT_DIR%release\windows\CASVMS.exe"
    set "EXE_DIR=%ROOT_DIR%release\windows"
) else if exist "%ROOT_DIR%frontend\src-tauri\target\x86_64-pc-windows-gnu\release\casvms-desktop.exe" (
    set "EXE_PATH=%ROOT_DIR%frontend\src-tauri\target\x86_64-pc-windows-gnu\release\casvms-desktop.exe"
    set "EXE_DIR=%ROOT_DIR%frontend\src-tauri\target\x86_64-pc-windows-gnu\release"
)

if defined EXE_PATH (
    start "" /D "!EXE_DIR!" "!EXE_PATH!"
) else (
    echo [ERROR] No se encontro el ejecutable CASVMS.exe.
    pause
    exit /b 1
)

echo CASVMS esta ejecutandose.
echo Disfruta del sistema de gestion de video edge industrial zero-cloud.
echo.
