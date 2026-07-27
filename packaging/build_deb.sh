#!/bin/bash
# Build the Linux .deb: PyInstaller one-dir bundle installed to
# /opt/stellarpulse with a /usr/bin launcher and a desktop entry.
# Run from the repo root on Linux:
#   bash packaging/build_deb.sh
set -euo pipefail

cd "$(dirname "$0")/.."
VERSION=$(python3 -c "exec(open('src/version.py').read()); print(__version__)")
ARCH=$(dpkg --print-architecture)

pyinstaller --noconfirm packaging/stellarpulse.spec

PKG=$(mktemp -d)
trap 'rm -rf "$PKG"' EXIT

mkdir -p "$PKG/opt/stellarpulse" \
         "$PKG/usr/bin" \
         "$PKG/usr/share/applications" \
         "$PKG/usr/share/icons/hicolor/512x512/apps" \
         "$PKG/DEBIAN"

cp -R dist/StellarPulse/. "$PKG/opt/stellarpulse/"
ln -s /opt/stellarpulse/StellarPulse "$PKG/usr/bin/stellarpulse"
cp assets/stellar_pulse_smart_reminder_timer.png \
   "$PKG/usr/share/icons/hicolor/512x512/apps/stellarpulse.png"

cat > "$PKG/usr/share/applications/stellarpulse.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=StellarPulse
Name[zh_CN]=星际脉动
Comment=Smart reminder timer
Exec=/opt/stellarpulse/StellarPulse
Icon=stellarpulse
Terminal=false
Categories=Utility;Clock;
EOF

INSTALLED_SIZE=$(du -sk "$PKG/opt" | cut -f1)
# Depends lists the system libraries Qt's bundled xcb platform plugin dlopens
# at runtime — libxcb-cursor0 in particular is absent on stock Ubuntu 22.04
# and its lack makes the app exit with "could not load the xcb plugin".
cat > "$PKG/DEBIAN/control" <<EOF
Package: stellarpulse
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Installed-Size: ${INSTALLED_SIZE}
Depends: libxcb-cursor0, libxkbcommon-x11-0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render-util0, libxcb-shape0, libxcb-xkb1, libegl1, libgl1, libfontconfig1, libdbus-1-3
Maintainer: StellarPulse <goosehuangmatt@gmail.com>
Description: StellarPulse smart reminder timer (星际脉动)
 Task timer with presets, categories, statistics and reminders.
EOF

DEB="dist/stellarpulse_${VERSION}_${ARCH}.deb"
dpkg-deb --build --root-owner-group "$PKG" "$DEB"
echo "Built $DEB"
