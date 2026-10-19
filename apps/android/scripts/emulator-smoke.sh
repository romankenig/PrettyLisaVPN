#!/usr/bin/env bash
set -euo pipefail

package=com.prettylisavpn.android.dev
mkdir -p evidence
python3 - <<'PY'
import hashlib, json, os, pathlib
directory = pathlib.Path('apk')
identity = json.loads((directory / 'build-identity.json').read_text())
assert identity['source_sha'] == os.environ['GITHUB_SHA']
assert hashlib.sha256((directory / identity['apk']).read_bytes()).hexdigest() == identity['apk_sha256']
PY
adb install -r apk/app-debug.apk
adb install -r test-apk/app-debug-androidTest.apk
adb shell am instrument -w -r \
  "$package.test/androidx.test.runner.AndroidJUnitRunner" | tee evidence/instrumentation.txt
python3 - <<'PY'
import pathlib, re
result = pathlib.Path('evidence/instrumentation.txt').read_text()
assert re.search(r'OK \(3 tests\)', result), result
assert not any(marker in result for marker in ('FAILURES!!!', 'INSTRUMENTATION_FAILED', 'shortMsg=')), result
PY
adb pull "/sdcard/Android/data/$package/files/acceptance/." evidence/

# Test the actual launcher after instrumentation has finished, including cold start.
adb shell am force-stop "$package"
adb shell am start -W -n "$package/com.prettylisavpn.android.MainActivity" | tee evidence/launch.txt
grep -q 'Status: ok' evidence/launch.txt
adb shell pidof "$package" > evidence/process.txt
adb shell dumpsys activity activities > evidence/activities.txt
grep -E '(mResumedActivity|topResumedActivity).*com.prettylisavpn.android.MainActivity' evidence/activities.txt
adb exec-out screencap -p > evidence/launcher.png
adb logcat -d -s AndroidRuntime:E > evidence/android-runtime.txt
if grep -q 'FATAL EXCEPTION' evidence/android-runtime.txt; then
  cat evidence/android-runtime.txt
  exit 1
fi
cp apk/build-identity.json evidence/
adb shell getprop ro.build.version.sdk > evidence/emulator-api.txt
adb shell getprop ro.product.cpu.abi > evidence/emulator-abi.txt
