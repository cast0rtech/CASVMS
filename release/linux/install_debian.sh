#!/usr/bin/env bash
# ==============================================================================
# CASVMS - Script de Instalación Automatizada para Linux Debian / Ubuntu
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=============================================================================="
echo "  Instalador de CASVMS para Debian / Ubuntu"
echo "=============================================================================="

# 1. Comprobar permisos de root
if [ "$EUID" -ne 0 ]; then
    echo "[!] Por favor ejecuta este instalador con sudo:"
    echo "    sudo ./install_debian.sh"
    exit 1
fi

# 2. Instalar dependencias del sistema operativo
echo "[1/4] Actualizando repositorios e instalando librerías de interfaz..."
apt-get update
apt-get install -y --no-install-recommends \
    libgtk-3-0 \
    libsoup2.4-1 \
    libwebkit2gtk-4.1-0 \
    curl \
    ca-certificates

# 3. Verificar o instalar Docker
echo "[2/4] Verificando Docker Engine..."
if ! command -v docker &> /dev/null; then
    echo "  -> Instalando Docker..."
    apt-get install -y docker.io docker-compose-plugin
    systemctl enable --now docker || true
fi

# 4. Crear estructura de datos persistentes
echo "[3/4] Creando directorios para persistencia de datos..."
mkdir -p data/influxdb data/grafana clips config mosquitto/config mosquitto/data mosquitto/log

if [ ! -f mosquitto/config/mosquitto.conf ]; then
    cat << 'EOF' > mosquitto/config/mosquitto.conf
listener 1883 0.0.0.0
allow_anonymous true
persistence true
persistence_location /mosquitto/data/
log_dest file /mosquitto/log/mosquitto.log
EOF
fi

# 5. Instalar paquete .deb nativo
echo "[4/4] Instalando el paquete nativo CASVMS..."
DEB_PATH="$SCRIPT_DIR/release/linux/casvms_1.0.0_amd64.deb"
if [ -f "$DEB_PATH" ]; then
    dpkg -i "$DEB_PATH" || apt-get install -f -y
    echo "  -> Paquete casvms instalado correctamente en /usr/bin/casvms"
    echo "  -> Lanzador agregado al menú de aplicaciones de escritorio"
else
    echo "[ADVERTENCIA] No se encontró $DEB_PATH, usando binario directo..."
    if [ -f "$SCRIPT_DIR/release/linux/casvms-desktop" ]; then
        cp "$SCRIPT_DIR/release/linux/casvms-desktop" /usr/local/bin/casvms
        chmod 755 /usr/local/bin/casvms
    fi
fi

echo "=============================================================================="
echo "¡Instalación completada con éxito en Debian / Ubuntu!"
echo "Para arrancar todo el sistema (backend + GUI nativa), ejecuta:"
echo "  ./start_linux.sh"
echo "O abre 'CASVMS' desde tu menú de aplicaciones."
echo "=============================================================================="
