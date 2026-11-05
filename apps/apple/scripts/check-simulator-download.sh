#!/bin/bash
# Install the exact ZIP offered for browser simulators, without fixture arguments.
set -euo pipefail
cd "$(dirname "$0")/.."
unpacked=$(mktemp -d)
device=$(head -n 1 artifacts/simulators.txt)
trap 'xcrun simctl shutdown "$device" || true; rm -rf "$unpacked"' EXIT
ditto -x -k artifacts/PrettyLisaVPN-iOS-Simulator.zip "$unpacked"
app="$unpacked/PrettyLisaVPN.app"
test "$(/usr/libexec/PlistBuddy -c 'Print DTPlatformName' "$app/Info.plist")" = iphonesimulator
lipo "$app/PrettyLisaVPN" -verify_arch arm64
bundle=$(/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' "$app/Info.plist")
xcrun simctl boot "$device"
xcrun simctl bootstatus "$device" -b
xcrun simctl uninstall "$device" "$bundle"
xcrun simctl install "$device" "$app"
xcrun simctl launch "$device" "$bundle"
sleep 3
xcrun simctl io "$device" screenshot artifacts/simulator-download.png
xcrun simctl terminate "$device" "$bundle"
python3 - <<'PY'
import hashlib, json
from pathlib import Path
archive = Path('artifacts/PrettyLisaVPN-iOS-Simulator.zip')
Path('artifacts/simulator-download-check.json').write_text(json.dumps({
    'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
    'installed_and_launched': True, 'fixture_arguments': False,
    'sdk': 'iphonesimulator', 'required_architecture': 'arm64',
}, indent=2) + '\n')
PY
