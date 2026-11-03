#!/bin/bash
set -euo pipefail
root=$(cd "$(dirname "$0")/../../.." && pwd)
out="$root/apps/apple/artifacts"
mkdir -p "$out/source"
git -C "$root" archive HEAD apps/apple engines/managed | tar -x -C "$out/source"
cp -R "$root/engines/managed/patched" "$out/source/engines/managed/patched"
cd "$root/engines/managed"
go mod vendor -o "$out/source/engines/managed/vendor"
go install github.com/google/go-licenses/v2@v2.0.1
go-licenses check ./cmd/pl-apple --allowed_licenses=MIT,MPL-2.0,Apache-2.0,BSD-2-Clause,BSD-3-Clause,ISC
go-licenses save ./cmd/pl-apple --save_path="$out/licenses"
tar -czf "$out/corresponding-source-and-licenses.tar.gz" -C "$out" source licenses
cd "$root/apps/apple"
ditto -c -k --sequesterRsrc --keepParent DerivedData/Build/Products/Debug-iphonesimulator/PrettyLisaVPN.app "$out/PrettyLisaVPN-iOS-Simulator.zip"
ditto -c -k --sequesterRsrc --keepParent DerivedData/Build/Products/Debug/PrettyLisaVPN.app "$out/PrettyLisaVPN-macOS-UI-ad-hoc.zip"
ditto -c -k --sequesterRsrc --keepParent DerivedData/Build/Products/Release/PrettyLisaVPN.app "$out/PrettyLisaVPN-macOS-release-unsigned.zip"
ditto -c -k --sequesterRsrc --keepParent DerivedData/Build/Products/Release-iphoneos/PrettyLisaVPN.app "$out/PrettyLisaVPN-iOS-device-unsigned.zip"
python3 - <<'PY'
import json, os, subprocess
from pathlib import Path
identity = {'source_sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
            'run': os.environ.get('GITHUB_RUN_ID'), 'attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
            'ios_version': '0.1.0', 'macos_version': '0.1.0', 'real_vpn_verified': False,
            'signing': 'unsigned/ad-hoc; no Apple team or provisioning profiles'}
Path('artifacts/build-identity.json').write_text(json.dumps(identity, indent=2) + '\n')
PY
