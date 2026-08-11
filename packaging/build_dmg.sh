#!/bin/bash
# Build StellarPulse.app with PyInstaller, then wrap it in a DMG with an
# /Applications symlink for drag-install. Run from the repo root:
#   bash packaging/build_dmg.sh
#
# Signing/notarization (both optional, each skipped with a warning if unset):
#   CODESIGN_IDENTITY  "Developer ID Application: Name (TEAMID)" — signs the
#                      app (hardened runtime + entitlements) and the DMG.
#   NOTARY_PROFILE     notarytool keychain profile name (created once via
#                      `xcrun notarytool store-credentials <name> ...`) —
#                      notarizes the app and the DMG, then staples both.
set -euo pipefail

cd "$(dirname "$0")/.."
VERSION=$(python3 -c "exec(open('src/version.py').read()); print(__version__)")

pyinstaller --noconfirm packaging/stellarpulse.spec
APP="dist/StellarPulse.app"

if [[ -n "${CODESIGN_IDENTITY:-}" ]]; then
    codesign --verify --strict --verbose=1 "$APP"
else
    echo "WARNING: CODESIGN_IDENTITY not set — app is ad-hoc signed" >&2
fi

if [[ -n "${NOTARY_PROFILE:-}" ]]; then
    # Notarize the app first so it can be stapled before the DMG snapshots it;
    # a stapled app passes Gatekeeper even offline after being dragged out.
    ZIP=$(mktemp -d)/app.zip
    ditto -c -k --keepParent "$APP" "$ZIP"
    xcrun notarytool submit "$ZIP" --keychain-profile "$NOTARY_PROFILE" --wait
    rm -f "$ZIP"
    xcrun stapler staple "$APP"
else
    echo "WARNING: NOTARY_PROFILE not set — skipping notarization" >&2
fi

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"

DMG="dist/StellarPulse-${VERSION}-macOS.dmg"
rm -f "$DMG"
hdiutil create -volname "StellarPulse ${VERSION}" -srcfolder "$STAGE" \
    -ov -format UDZO "$DMG"

if [[ -n "${CODESIGN_IDENTITY:-}" ]]; then
    codesign --force --sign "$CODESIGN_IDENTITY" "$DMG"
fi
if [[ -n "${NOTARY_PROFILE:-}" ]]; then
    xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait
    xcrun stapler staple "$DMG"
fi

echo "Built $DMG"
