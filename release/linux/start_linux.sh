#!/usr/bin/env bash
# ==============================================================================
# CASVMS - Lanzador Automatizado para Linux (Debian / Ubuntu)
# Inicia los servicios Docker de fondo y lanza el cliente nativo CASVMS
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=============================================================================="
echo "  👁️  CASVMS - Industrial AI Video Management System (Edge AI Zero-Cloud)"
echo "=============================================================================="

# 1. Comprobar Docker
if ! command -v docker &> /dev/null; then
    echo "[ERROR] Docker no está instalado o no se encuentra en el PATH."
    echo "Instala Docker con: sudo apt-get install -y docker.io docker-compose-plugin"
    exit 1
fi

# 2. Levantar el stack Docker
echo ""
echo "[1/3] Levantando stack de contenedores (FastAPI, OpenVINO, InfluxDB, Grafana)..."
docker compose up -d

# 3. Esperar al motor REST / Healthcheck
echo "[2/3] Esperando a que el motor VMS responda en http://localhost:8000/health ..."
retries=0
until curl -s -f http://localhost:8000/health > /dev/null 2>&1; do
    retries=$((retries + 1))
    if [ $retries -ge 30 ]; then
        echo "[ADVERTENCIA] El motor tardó en responder. Continuando con el inicio de la GUI..."
        break
    fi
    sleep 1
done

if curl -s -f http://localhost:8000/health > /dev/null 2>&1; then
    echo "  -> [OK] Motor VMS en línea y listo para conexiones."
fi

# 4. Lanzar la aplicación nativa
echo "[3/3] Iniciando cliente nativo de escritorio CASVMS..."

if [ -f "$SCRIPT_DIR/release/linux/casvms-desktop" ]; then
    chmod +x "$SCRIPT_DIR/release/linux/casvms-desktop"
    nohup "$SCRIPT_DIR/release/linux/casvms-desktop" > /dev/null 2>&1 &
elif command -v casvms &> /dev/null; then
    nohup casvms > /dev/null 2>&1 &
elif [ -f "$SCRIPT_DIR/frontend/src-tauri/target/release/casvms-desktop" ]; then
    chmod +x "$SCRIPT_DIR/frontend/src-tauri/target/release/casvms-desktop"
    nohup "$SCRIPT_DIR/frontend/src-tauri/target/release/casvms-desktop" > /dev/null 2>&1 &
else
    echo "[ERROR] No se encontró el binario casvms-desktop."
    exit 1
fi

echo ""
echo "¡CASVMS ha iniciado con éxito!"
echo "Servicios activos:"
echo " • API / Motor VMS:    http://localhost:8000"
echo " • Paneles Grafana:    http://localhost:3000 (admin/admin)"
echo " • Consola InfluxDB:   http://localhost:8086"
echo " • Broker MQTT:        mqtt://localhost:1883"
echo " • Modbus TCP:         localhost:5020"
