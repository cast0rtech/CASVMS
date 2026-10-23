#!/usr/bin/env bash
set -e

SRC_DIR="/mnt/c/Castor Programs/CASVMS"
TARGET_RELEASE="$SRC_DIR/frontend/src-tauri/target/release/casvms-desktop"
ICONS_DIR="$SRC_DIR/frontend/src-tauri/icons"
OUT_DIR="$SRC_DIR/release/linux"
PKG_DIR="/tmp/casvms_pkg/casvms_1.0.0_amd64"

rm -rf "/tmp/casvms_pkg"
mkdir -p "$PKG_DIR/DEBIAN"
mkdir -p "$PKG_DIR/usr/bin"
mkdir -p "$PKG_DIR/usr/share/applications"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/128x128/apps"
mkdir -p "$PKG_DIR/usr/share/icons/hicolor/32x32/apps"
mkdir -p "$OUT_DIR"

cat << 'EOF' > "$PKG_DIR/DEBIAN/control"
Package: casvms
Version: 1.0.0
Section: video
Priority: optional
Architecture: amd64
Depends: libc6, libgtk-3-0, libwebkit2gtk-4.1-0 | libwebkit2gtk-4.0-37, libsoup-2.4-1 | libsoup-3.0-0
Maintainer: CASVMS Engineering <support@casvms.internal>
Description: Industrial AI Video Management System (VMS)
 CASVMS is a zero-cloud high-performance edge video management system
 with Intel OpenVINO hardware acceleration, ALPR, MOG2 gatekeeper, and Modbus TCP.
EOF

cat << 'EOF' > "$PKG_DIR/usr/share/applications/casvms.desktop"
[Desktop Entry]
Name=CASVMS
Comment=Industrial AI Video Management System
Exec=/usr/bin/casvms
Icon=casvms
Terminal=false
Type=Application
Categories=Video;AudioVideo;Development;Network;
StartupWMClass=casvms-desktop
EOF

cp "$TARGET_RELEASE" "$PKG_DIR/usr/bin/casvms"
chmod 755 "$PKG_DIR/usr/bin/casvms"

cp "$ICONS_DIR/128x128.png" "$PKG_DIR/usr/share/icons/hicolor/128x128/apps/casvms.png"
cp "$ICONS_DIR/32x32.png" "$PKG_DIR/usr/share/icons/hicolor/32x32/apps/casvms.png"

# Copy binary to release/linux as well
cp "$TARGET_RELEASE" "$OUT_DIR/casvms-desktop"
chmod 755 "$OUT_DIR/casvms-desktop"

dpkg-deb --build "$PKG_DIR" "$OUT_DIR/casvms_1.0.0_amd64.deb"
rm -rf "/tmp/casvms_pkg"

echo "DEB package created successfully at: $OUT_DIR/casvms_1.0.0_amd64.deb"
