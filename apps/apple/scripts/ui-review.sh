#!/bin/bash
set -euo pipefail
mkdir -p artifacts
python3 - <<'PY'
import json, subprocess
devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '--json']))['devices']
phones = [d for values in devices.values() for d in values if 'iPhone' in d['name']]
if not phones:
    raise SystemExit('No iPhone Simulator runtime installed')
small = next((d for d in phones if 'SE' in d['name'] or '16e' in d['name']), phones[0])
large = next((d for d in phones if 'Pro Max' in d['name']), phones[-1])
with open('artifacts/simulators.txt', 'w') as output:
    output.write(small['udid'] + '\n' + large['udid'] + '\n')
PY
index=0
while IFS= read -r device; do
  index=$((index + 1))
  xcrun simctl boot "$device" || xcrun simctl bootstatus "$device" -b
  xcrun simctl bootstatus "$device" -b
  for theme in light dark; do
    xcrun simctl ui "$device" appearance "$theme"
    xcodebuild -project PrettyLisaVPN.xcodeproj -scheme PrettyLisaVPN-iOS -configuration Debug \
      -destination "platform=iOS Simulator,id=$device" -derivedDataPath DerivedData \
      -resultBundlePath "artifacts/iphone-$index-$theme.xcresult" CODE_SIGNING_ALLOWED=NO test
    xcrun simctl io "$device" screenshot "artifacts/iphone-$index-$theme.png"
  done
  xcrun simctl shutdown "$device"
done < artifacts/simulators.txt
