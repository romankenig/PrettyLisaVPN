#!/bin/bash
set -euo pipefail
mkdir -p artifacts
python3 - <<'PY'
import json, subprocess
devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '--json']))['devices']
phones = [dict(d, runtime=runtime) for runtime, values in devices.items() for d in values if 'iPhone' in d['name']]
if not phones:
    raise SystemExit('No iPhone Simulator runtime installed')
small = next((d for d in phones if 'SE' in d['name'] or '16e' in d['name']), phones[0])
large = next((d for d in phones if 'Pro Max' in d['name']), phones[-1])
with open('artifacts/simulators.txt', 'w') as output:
    output.write(small['udid'] + '\n' + large['udid'] + '\n')
with open('artifacts/simulators.json', 'w') as output:
    json.dump([small, large], output, indent=2)
PY
index=0
while IFS= read -r device; do
  index=$((index + 1))
  # One runner installation per device; XCTest exercises BOTH appearances internally.
  # Reinstalling the runner between themes races CoreSimulator's install/uninstall state.
  xcrun simctl boot "$device" || xcrun simctl bootstatus "$device" -b
  xcrun simctl bootstatus "$device" -b
  xcodebuild -project PrettyLisaVPN.xcodeproj -scheme PrettyLisaVPN-iOS -configuration Debug \
    -destination "platform=iOS Simulator,id=$device" -derivedDataPath DerivedData \
    -parallel-testing-enabled NO -maximum-concurrent-test-simulator-destinations 1 \
    -resultBundlePath "artifacts/iphone-$index.xcresult" CODE_SIGNING_ALLOWED=YES \
    CODE_SIGN_IDENTITY=- CODE_SIGN_ENTITLEMENTS=Config/Simulator.entitlements DEVELOPMENT_TEAM= test </dev/null
  bundle=$(/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' DerivedData/Build/Products/Debug-iphonesimulator/PrettyLisaVPN.app/Info.plist)
  for theme in light dark; do
    xcrun simctl ui "$device" appearance "$theme"
    xcrun simctl launch "$device" "$bundle" -ui-fixtures YES -simulate-vpn YES -AppleLanguages '(ru)' -theme "$theme"
    sleep 2
    xcrun simctl io "$device" screenshot "artifacts/iphone-$index-$theme.png"
    xcrun simctl terminate "$device" "$bundle"
  done
  xcrun simctl shutdown "$device"
done < artifacts/simulators.txt
