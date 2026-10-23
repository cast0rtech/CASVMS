# ==============================================================================
# CASVMS - Lanzador Automatizado para Windows (PowerShell)
# Inicia los servicios Docker de fondo y lanza la aplicación nativa CASVMS
# ==============================================================================

$ErrorActionPreference = "Stop"

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "  👁️  CASVMS - Industrial AI Video Management System (Edge AI Zero-Cloud)" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan

# 1. Comprobar Docker
if (!(Get-Command "docker" -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] Docker no está instalado o no se encuentra en el PATH." -ForegroundColor Red
    Write-Host "Asegúrate de tener Docker Desktop activo y vuelve a intentarlo." -ForegroundColor Yellow
    exit 1
}

# 2. Levantar el stack Docker
Write-Host "`n[1/3] Levantando stack de contenedores (FastAPI, OpenVINO, InfluxDB, Grafana)..." -ForegroundColor Yellow
try {
    docker compose up -d
} catch {
    Write-Host "[ERROR] Falló al ejecutar docker compose up. Revisa el estado de Docker Desktop." -ForegroundColor Red
    exit 1
}

# 3. Esperar al motor REST / Healthcheck
Write-Host "[2/3] Esperando a que el motor VMS responda en http://localhost:8000/health ..." -ForegroundColor Yellow
$retries = 0
$online = $false

while ($retries -lt 30 -and !$online) {
    try {
        $res = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 1 -UseBasicParsing -ErrorAction SilentlyContinue
        if ($res.StatusCode -eq 200) {
            $online = $true
            break
        }
    } catch {
        # Sigue esperando
    }
    Start-Sleep -Seconds 1
    $retries++
}

if ($online) {
    Write-Host "  -> [OK] Motor VMS en línea y listo para conexiones." -ForegroundColor Green
} else {
    Write-Host "  -> [ADVERTENCIA] El motor tardó en responder. Iniciando GUI..." -ForegroundColor DarkYellow
}

# 4. Lanzar la aplicación nativa
Write-Host "[3/3] Iniciando cliente nativo de escritorio CASVMS..." -ForegroundColor Yellow

$exePath = Join-Path $PSScriptRoot "release\windows\CASVMS.exe"
if (!(Test-Path $exePath)) {
    $exePath = Join-Path $PSScriptRoot "frontend\src-tauri\target\x86_64-pc-windows-gnu\release\casvms-desktop.exe"
}

if (Test-Path $exePath) {
    Start-Process -FilePath $exePath
    Write-Host "`n¡CASVMS ha iniciado con éxito!" -ForegroundColor Green
    Write-Host "Servicios activos:" -ForegroundColor Cyan
    Write-Host " • API / Motor VMS:    http://localhost:8000"
    Write-Host " • Paneles Grafana:    http://localhost:3000 (admin/admin)"
    Write-Host " • Consola InfluxDB:   http://localhost:8086"
    Write-Host " • Broker MQTT:        mqtt://localhost:1883"
    Write-Host " • Modbus TCP:         localhost:5020"
} else {
    Write-Host "[ERROR] No se encontró el binario CASVMS.exe en $exePath" -ForegroundColor Red
    exit 1
}
