#!/bin/bash
# Build StellarPulse.app with PyInstaller, then wrap it in a DMG with an
# /Applications symlink for drag-install. Run from the repo root:
#   bash packaging/build_dmg.sh
set -euo pipefail

cd "$(dirname "$0")/.."
VERSION=$(python3 -c "exec(open('src/version.py').read()); print(__version__)")

pyinstaller --noconfirm packaging/stellarpulse.spec

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
cp -R "dist/StellarPulse.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"

DMG="dist/StellarPulse-${VERSION}-macOS.dmg"
rm -f "$DMG"
hdiutil create -volname "StellarPulse ${VERSION}" -srcfolder "$STAGE" \
    -ov -format UDZO "$DMG"
echo "Built $DMG"
