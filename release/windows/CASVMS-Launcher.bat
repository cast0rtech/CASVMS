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

:: 2. Levantar la infraestructura backend si no esta activa
echo [1/3] Comprobando infraestructura backend (FastAPI, OpenVINO, InfluxDB, Grafana)...
docker compose up -d

:: 3. Esperar a que el motor FastAPI este listo
echo [2/3] Esperando a que el motor VMS responda en http://localhost:8000 ...
set /a retries=0
:WAIT_API
curl -s -f http://localhost:8000/health >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Motor VMS en linea y saludable.
    goto LAUNCH_APP
)
set /a retries+=1
if !retries! geq 30 (
    echo [ADVERTENCIA] El motor tardo mas de lo esperado en iniciar. Iniciando interfaz de todos modos...
    goto LAUNCH_APP
)
timeout /t 1 >nul
goto WAIT_API

:LAUNCH_APP
echo [3/3] Iniciando aplicacion de escritorio CASVMS...
echo.

if exist "release\windows\CASVMS.exe" (
    start "" "release\windows\CASVMS.exe"
) else if exist "frontend\src-tauri\target\x86_64-pc-windows-gnu\release\casvms-desktop.exe" (
    start "" "frontend\src-tauri\target\x86_64-pc-windows-gnu\release\casvms-desktop.exe"
) else (
    echo [ERROR] No se encontro el ejecutable CASVMS.exe.
    pause
    exit /b 1
)

echo CASVMS esta ejecutandose.
echo Disfruta del sistema de gestion de video edge industrial zero-cloud.
echo.
