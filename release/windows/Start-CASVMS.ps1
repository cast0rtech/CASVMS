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
$projectRoot = $PSScriptRoot
if (Test-Path (Join-Path $PSScriptRoot "..\..\docker-compose.yml")) {
    $projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
} elseif (Test-Path (Join-Path $PSScriptRoot "..\docker-compose.yml")) {
    $projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}
$composeFile = Join-Path $projectRoot "docker-compose.yml"

Write-Host "`n[1/3] Levantando stack de contenedores (FastAPI, OpenVINO, InfluxDB, Grafana)..." -ForegroundColor Yellow
try {
    if (Test-Path $composeFile) {
        docker compose -f $composeFile up -d
    } else {
        docker compose up -d
    }
} catch {
    Write-Host "[ERROR] Falló al ejecutar docker compose up. Revisa el estado de Docker Desktop." -ForegroundColor Red
    exit 1
}

# 3. Esperar al motor REST y Frontend / Healthcheck
Write-Host "[2/3] Esperando a que el backend (8001) y frontend (1420) respondan..." -ForegroundColor Yellow
$retries = 0
$online = $false

while ($retries -lt 30 -and !$online) {
    try {
        $resApi = Invoke-WebRequest -Uri "http://localhost:8001/health" -TimeoutSec 1 -UseBasicParsing -ErrorAction SilentlyContinue
        $resUi = Invoke-WebRequest -Uri "http://localhost:1420/" -TimeoutSec 1 -UseBasicParsing -ErrorAction SilentlyContinue
        if ($resApi.StatusCode -eq 200 -and $resUi.StatusCode -eq 200) {
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
    Write-Host "  -> [OK] Motor VMS e interfaz frontend en línea y listos." -ForegroundColor Green
} else {
    Write-Host "  -> [ADVERTENCIA] Los servicios tardaron en responder. Iniciando GUI..." -ForegroundColor DarkYellow
}

# 4. Lanzar la aplicación nativa
Write-Host "[3/3] Iniciando cliente nativo de escritorio CASVMS..." -ForegroundColor Yellow

# Limpiar instancias previas y procesos huérfanos de WebView2 para evitar bloqueos (0x800700AA / 0x8007139F)
Stop-Process -Name "CASVMS" -Force -ErrorAction SilentlyContinue
Stop-Process -Name "casvms-desktop" -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 300

Get-CimInstance Win32_Process -Filter "Name like '%webview%'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "com\.casvms\.desktop" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# Eliminar archivo LOCK residual de WebView2 si existiera
$lockPath = Join-Path $env:LOCALAPPDATA "com.casvms.desktop\EBWebView\Default\LOCK"
if (Test-Path $lockPath) {
    Remove-Item -Path $lockPath -Force -ErrorAction SilentlyContinue
}

$exeCandidates = @(
    (Join-Path $PSScriptRoot "CASVMS.exe"),
    (Join-Path $projectRoot "release\windows\CASVMS.exe"),
    (Join-Path $projectRoot "frontend\src-tauri\target\x86_64-pc-windows-gnu\release\casvms-desktop.exe")
)

$exePath = $null
foreach ($cand in $exeCandidates) {
    if (Test-Path $cand) {
        $exePath = (Resolve-Path $cand).Path
        break
    }
}

if ($exePath) {
    $exeDir = Split-Path $exePath -Parent
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $exePath
    $psi.WorkingDirectory = $exeDir
    $psi.UseShellExecute = $true
    [System.Diagnostics.Process]::Start($psi) | Out-Null
    Write-Host "`n¡CASVMS ha iniciado con éxito!" -ForegroundColor Green
    Write-Host "Servicios activos:" -ForegroundColor Cyan
    Write-Host " • Interfaz / Dashboard: http://localhost:1420"
    Write-Host " • API / Motor VMS:      http://localhost:8001"
    Write-Host " • Paneles Grafana:      http://localhost:3000 (admin/admin)"
    Write-Host " • Consola InfluxDB:     http://localhost:8086"
    Write-Host " • Broker MQTT:          mqtt://localhost:1883"
    Write-Host " • Modbus TCP:           localhost:5020"
} else {
    Write-Host "[ERROR] No se encontró el binario CASVMS.exe" -ForegroundColor Red
    exit 1
}
