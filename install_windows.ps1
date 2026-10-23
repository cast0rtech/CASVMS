# ==============================================================================
# CASVMS - Script de Instalación Automatizada para Windows (PowerShell)
# Nota: Ejecutar este script desde una consola de PowerShell como Administrador.
# Si hay errores de permisos de ejecución, corre primero: 
# Set-ExecutionPolicy Bypass -Scope Process -Force
# ==============================================================================

$ErrorActionPreference = "Stop"

Write-Host "Iniciando la instalación de CASVMS (Edge AI VMS) en Windows..." -ForegroundColor Green

# 1. Verificación de permisos de Administrador
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (!$isAdmin) {
    Write-Host "ERROR: Por favor, ejecuta PowerShell como Administrador." -ForegroundColor Red
    exit
}

# 2. Verificación de Docker Desktop
Write-Host "Comprobando dependencias de Docker..." -ForegroundColor Yellow
if (!(Get-Command "docker" -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Docker no está instalado o no está en el PATH." -ForegroundColor Red
    Write-Host "Por favor, instala Docker Desktop con integración WSL2 y vuelve a intentarlo." -ForegroundColor Red
    exit
}

# 3. Creación de la estructura de volúmenes persistentes
Write-Host "Creando estructura de directorios para volúmenes de Docker..." -ForegroundColor Yellow

$directories = @(
    "data\influxdb",
    "data\grafana",
    "clips",
    "config",
    "mosquitto\config",
    "mosquitto\data",
    "mosquitto\log"
)

foreach ($dir in $directories) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        Write-Host "  -> Creado: $dir" -ForegroundColor DarkGray
    }
}

# 4. Configuración de Eclipse Mosquitto
Write-Host "Configurando broker MQTT local..." -ForegroundColor Yellow
$mosquittoConfigPath = "mosquitto\config\mosquitto.conf"
$mosquittoConfigContent = @"
listener 1883 0.0.0.0
allow_anonymous true
persistence true
persistence_location /mosquitto/data/
log_dest file /mosquitto/log/mosquitto.log
"@

Set-Content -Path $mosquittoConfigPath -Value $mosquittoConfigContent -Encoding UTF8
Write-Host "  -> Archivo mosquitto.conf generado." -ForegroundColor DarkGray

# 5. Levantar el stack de Docker
Write-Host "Construyendo y levantando los contenedores de CASVMS (esto puede tardar unos minutos)..." -ForegroundColor Yellow
try {
    # Usamos docker compose (V2) por defecto en Docker Desktop
    docker compose up -d --build
} catch {
    Write-Host "Hubo un error al ejecutar docker compose. Revisa que Docker Desktop esté encendido." -ForegroundColor Red
    exit
}

Write-Host "------------------------------------------------------------" -ForegroundColor Cyan
Write-Host "¡Instalación de CASVMS completada con éxito en Windows!" -ForegroundColor Green
Write-Host "------------------------------------------------------------" -ForegroundColor Cyan
Write-Host "Servicios locales disponibles en tu equipo:"
Write-Host " 👁️  Motor VMS (API):  http://localhost:8000"
Write-Host " 📊 Dashboards Grafana: http://localhost:3000 (admin/admin)"
Write-Host " 🗄️  InfluxDB Console:   http://localhost:8086"
Write-Host " 📡 Broker MQTT:        mqtt://localhost:1883"
Write-Host "`nPara arrancar el sistema completo y la aplicación de escritorio, ejecuta:" -ForegroundColor Cyan
Write-Host "  .\CASVMS-Launcher.bat  (o .\Start-CASVMS.ps1)" -ForegroundColor Yellow
Write-Host "O abre directamente el binario autoejecutable en: release\windows\CASVMS.exe" -ForegroundColor Green
