#!/usr/bin/env bash
set -euo pipefail

package=com.prettylisavpn.android.dev
api_level=$(adb shell getprop ro.build.version.sdk | tr -d '\r')
[[ "$api_level" =~ ^[0-9]+$ ]]
mkdir -p evidence
cleanup() {
  if [[ -n "${vpn_peer_pid:-}" ]]; then kill "$vpn_peer_pid" 2>/dev/null || true; wait "$vpn_peer_pid" 2>/dev/null || true; fi
  adb logcat -d -s WireGuard/GoBackend AndroidRuntime > evidence/vpn-runtime-log.txt 2>&1 || true
  # Preserve framework/IME evidence too: a System UI ANR must not look like an app-input failure.
  adb logcat -d -b events > evidence/android-events.txt 2>&1 || true
  adb shell dumpsys activity lastanr > evidence/last-anr.txt 2>&1 || true
  adb shell dumpsys input_method > evidence/input-method.txt 2>&1 || true
  # Best-effort evidence and device reset also on test failure; never replaces the failing exit code.
  adb pull "/sdcard/Android/data/$package/files/acceptance/." evidence/ >/dev/null 2>&1 || true
  adb shell wm size reset >/dev/null 2>&1 || true
  adb shell wm density reset >/dev/null 2>&1 || true
  if (( api_level >= 30 )); then
    adb shell wm user-rotation free >/dev/null 2>&1 || true
  else
    adb shell settings put system user_rotation 0 >/dev/null 2>&1 || true
    adb shell settings put system accelerometer_rotation 1 >/dev/null 2>&1 || true
  fi
  adb shell settings put system font_scale 1.0 >/dev/null 2>&1 || true
}
trap cleanup EXIT
python3 - <<'PY'
import hashlib, json, os, pathlib
directory = pathlib.Path('apk')
identity = json.loads((directory / 'build-identity.json').read_text())
assert identity['source_sha'] == os.environ['GITHUB_SHA']
assert hashlib.sha256((directory / identity['apk']).read_bytes()).hexdigest() == identity['apk_sha256']
PY
adb install -r apk/app-debug.apk
adb install -r test-apk/app-debug-androidTest.apk
adb shell settings put secure show_ime_with_hard_keyboard 1
adb shell am instrument -w -r -e class com.prettylisavpn.android.NavigationTest \
  "$package.test/com.prettylisavpn.android.AcceptanceRunner" | tee evidence/instrumentation.txt
python3 - <<'PY'
import pathlib, re
result = pathlib.Path('evidence/instrumentation.txt').read_text()
assert re.search(r'OK \(3 tests\)', result), result
assert not any(marker in result for marker in ('FAILURES!!!', 'INSTRUMENTATION_FAILED', 'shortMsg=')), result
PY

# Exercise the actual Android Keystore and durable encrypted record on every supported API.
adb shell am instrument -w -r -e class com.prettylisavpn.android.KeystoreSessionTest \
  "$package.test/com.prettylisavpn.android.AcceptanceRunner" | tee evidence/keystore-instrumentation.txt
python3 - <<'KEYSTORE_CHECK'
import pathlib, re
result = pathlib.Path('evidence/keystore-instrumentation.txt').read_text()
assert re.search(r'OK \(4 tests\)', result), result
assert not any(marker in result for marker in ('FAILURES!!!', 'INSTRUMENTATION_FAILED', 'shortMsg=')), result
KEYSTORE_CHECK

# The real auth shell uses a synthetic AuthApi port here, never a real email/account.
adb shell am instrument -w -r -e class com.prettylisavpn.android.AuthSessionUiTest \
  "$package.test/com.prettylisavpn.android.AcceptanceRunner" | tee evidence/auth-ui-instrumentation.txt
python3 - <<'AUTH_UI_CHECK'
import pathlib, re
result = pathlib.Path('evidence/auth-ui-instrumentation.txt').read_text()
assert re.search(r'OK \(5 tests\)', result), result
assert not any(marker in result for marker in ('FAILURES!!!', 'INSTRUMENTATION_FAILED', 'shortMsg=')), result
AUTH_UI_CHECK

# Shared header, six locales and the real monotonic OTP cooldown; all APIs are synthetic.
adb shell am instrument -w -r -e class com.prettylisavpn.android.PresentationUiTest \
  "$package.test/com.prettylisavpn.android.AcceptanceRunner" | tee evidence/presentation-ui-instrumentation.txt
python3 - <<'PRESENTATION_CHECK'
import pathlib, re
result = pathlib.Path('evidence/presentation-ui-instrumentation.txt').read_text()
assert re.search(r'OK \(4 tests\)', result), result
assert not any(marker in result for marker in ('FAILURES!!!', 'INSTRUMENTATION_FAILED', 'shortMsg=')), result
PRESENTATION_CHECK

# Two independent Android processes prove encrypted state survives force-stop.
for stage in Seed Check; do
  adb shell am force-stop "$package"
  adb shell am instrument -w -r -e class "com.prettylisavpn.android.KeystoreRestart$stage" \
    "$package.test/com.prettylisavpn.android.AcceptanceRunner" | tee "evidence/keystore-restart-$stage.txt"
  python3 - "$stage" <<'RESTART_CHECK'
import pathlib, re, sys
result = pathlib.Path(f'evidence/keystore-restart-{sys.argv[1]}.txt').read_text()
assert re.search(r'OK \(1 test\)', result), result
assert not any(marker in result for marker in ('FAILURES!!!', 'INSTRUMENTATION_FAILED', 'shortMsg=')), result
RESTART_CHECK
done

# Live account screens and encrypted operation journal use isolated API ports only.
for spec in AccountScreensTest:11 AccountJournalTest:2; do
  test_class=${spec%:*}; test_count=${spec#*:}
  adb shell am instrument -w -r -e class "com.prettylisavpn.android.$test_class" \
    "$package.test/com.prettylisavpn.android.AcceptanceRunner" | tee "evidence/$test_class-instrumentation.txt"
  python3 - "$test_class" "$test_count" <<'ACCOUNT_CHECK'
import pathlib, re, sys
result = pathlib.Path(f'evidence/{sys.argv[1]}-instrumentation.txt').read_text()
assert re.search(rf'OK \({sys.argv[2]} tests\)', result), result
assert not any(marker in result for marker in ('FAILURES!!!', 'INSTRUMENTATION_FAILED', 'shortMsg=')), result
ACCOUNT_CHECK
done

# The disposable host peer is owned only by this emulator job; keys are never artifacts.
bash apps/android/scripts/vpn-test-peer.sh > /tmp/prettylisa-peer-log 2>&1 &
vpn_peer_pid=$!
for attempt in $(seq 1 50); do
  if [[ -s /tmp/prettylisa-test-peer-public ]]; then break; fi
  if ! kill -0 "$vpn_peer_pid" 2>/dev/null; then cat /tmp/prettylisa-peer-log; exit 1; fi
  sleep 0.2
done
[[ -s /tmp/prettylisa-test-peer-public ]]
adb shell mkdir -p "/sdcard/Android/data/$package/files/acceptance/vpn"
adb push /tmp/prettylisa-test-peer-public "/sdcard/Android/data/$package/files/acceptance/vpn/server-public-key" > /dev/null

# Production VpnService + actual WireGuard JNI/TUN. Isolated unresponsive peer, never real OTP.
adb shell am instrument -w -r -e class com.prettylisavpn.android.VpnServiceTest \
  "$package.test/com.prettylisavpn.android.AcceptanceRunner" | tee evidence/vpn-instrumentation.txt
python3 - <<'VPN_CHECK'
import pathlib, re
result = pathlib.Path('evidence/vpn-instrumentation.txt').read_text()
assert re.search(r'OK \(1 test\)', result), result
assert not any(marker in result for marker in ('FAILURES!!!', 'INSTRUMENTATION_FAILED', 'shortMsg=')), result
VPN_CHECK
# Keep a real connected peer/journal, kill the application, then recover in a new process.
adb shell am force-stop "$package"
adb shell am instrument -w -r -e class com.prettylisavpn.android.VpnServiceTest -e vpnStage seed \
  "$package.test/com.prettylisavpn.android.AcceptanceRunner" | tee evidence/vpn-restart-seed-instrumentation.txt
adb shell am force-stop "$package"
adb shell am instrument -w -r -e class com.prettylisavpn.android.VpnRestartCheck \
  "$package.test/com.prettylisavpn.android.AcceptanceRunner" | tee evidence/vpn-restart-check-instrumentation.txt
python3 - <<'VPN_RESTART'
import pathlib,re
for stage in ('seed','check'):
    result=pathlib.Path(f'evidence/vpn-restart-{stage}-instrumentation.txt').read_text()
    assert re.search(r'OK \(1 test\)',result),result
    assert not any(marker in result for marker in ('FAILURES!!!','INSTRUMENTATION_FAILED','shortMsg=')),result
VPN_RESTART
kill "$vpn_peer_pid"
wait "$vpn_peer_pid" || true
vpn_peer_pid=

# Full fixture flows use the same installed APK, real Android Back and native dialogs.
adb shell am instrument -w -r -e class com.prettylisavpn.android.ScreenFlowTest \
  "$package.test/com.prettylisavpn.android.AcceptanceRunner" | tee evidence/flows-instrumentation.txt
python3 - <<'FLOW_CHECK'
import pathlib, re
result = pathlib.Path('evidence/flows-instrumentation.txt').read_text()
assert re.search(r'OK \(9 tests\)', result), result
assert not any(marker in result for marker in ('FAILURES!!!', 'INSTRUMENTATION_FAILED', 'shortMsg=')), result
FLOW_CHECK

# Use real Android configuration changes and actual keyboard/insets, not Compose previews.
for design_case in compact small scaled-font large-font roomy landscape; do
  case "$design_case" in
    compact) viewport=720x1280; font_scale=1.0 ;;
    small) viewport=640x1136; font_scale=1.0 ;;
    scaled-font) viewport=640x1136; font_scale=1.3 ;;
    large-font) viewport=720x1280; font_scale=2.0 ;;
    roomy) viewport=824x1648; font_scale=1.0 ;;
    landscape) viewport=720x1280; font_scale=1.0 ;;
  esac
  adb shell am force-stop "$package"
  adb shell wm size "$viewport"
  adb shell wm density 320
  adb shell settings put system font_scale "$font_scale"
  # Do not race SettingsProvider rotation observers against wm resize on modern Android.
  # Portrait cases use the emulator's natural orientation; rotate only the final landscape case.
  if [[ "$design_case" == landscape ]]; then
    if (( api_level >= 30 )); then
      adb shell wm user-rotation lock 1
    else
      adb shell settings put system accelerometer_rotation 0
      adb shell settings put system user_rotation 1
    fi
  fi
  # Settle the real Activity/display configuration before the instrumentation rule owns it.
  # Otherwise the final rotation can recreate the Activity after a test-only setContent call.
  adb shell am start -W -n "$package/com.prettylisavpn.android.MainActivity" > /dev/null
  if [[ "$design_case" == landscape ]]; then
    expected_width=1280; expected_height=720
  else
    expected_width=${viewport%x*}; expected_height=${viewport#*x}
  fi
  mkdir -p "evidence/$design_case"
  adb shell am instrument -w -r \
    -e class com.prettylisavpn.android.DesignAcceptanceTest \
    -e designCase "$design_case" -e fontScale "$font_scale" \
    -e widthPx "$expected_width" -e heightPx "$expected_height" \
    "$package.test/com.prettylisavpn.android.AcceptanceRunner" | tee "evidence/$design_case/instrumentation.txt"
  python3 - "$design_case" <<'PY'
import pathlib, re, sys
result = (pathlib.Path('evidence') / sys.argv[1] / 'instrumentation.txt').read_text()
assert re.search(r'OK \(3 tests\)', result), result
assert not any(marker in result for marker in ('FAILURES!!!', 'INSTRUMENTATION_FAILED', 'shortMsg=')), result
PY
done
adb pull "/sdcard/Android/data/$package/files/acceptance/." evidence/
python3 - <<'PY'
import json, os, pathlib, struct
identity = json.loads(pathlib.Path('apk/build-identity.json').read_text())
native_size = struct.unpack('>II', pathlib.Path('evidence/home.png').read_bytes()[16:24])
cases = {'compact': (720,1280,1.0), 'small': (640,1136,1.0), 'scaled-font': (640,1136,1.3),
         'large-font': (720,1280,2.0), 'roomy': (824,1648,1.0), 'landscape': (1280,720,1.0)}
for case, (width,height,font) in cases.items():
    for shot in ('home','settings','about','support-keyboard-error','support-filled','components'):
        path = pathlib.Path('evidence') / case / shot
        png = path.with_suffix('.png').read_bytes()
        assert png[:8] == b'\x89PNG\r\n\x1a\n'
        # Old SurfaceFlinger captures retain the physical display; newer APIs use wm size.
        assert struct.unpack('>II', png[16:24]) in ((width,height), native_size, native_size[::-1]), (case,shot)
        metadata = json.loads(path.with_suffix('.json').read_text())
        assert metadata['source_sha'] == os.environ['GITHUB_SHA']
        assert (metadata['window_width_px'], metadata['window_height_px']) == (width,height), (case,shot,metadata)
        assert metadata['version_name'] == identity['version_name']
        assert metadata['version_code'] == identity['version_code']
        assert metadata['application_id'] == identity['application_id']
        assert abs(metadata['font_scale'] - font) < 0.02
        assert abs(metadata['density'] - 2.0) < 0.02
        if shot == 'support-keyboard-error': assert metadata['ime_visible'] is True
print('Native viewport/fontScale/IME/source identities verified for all six configurations')
PY

adb shell wm size reset
adb shell wm density reset
if (( api_level >= 30 )); then
  adb shell wm user-rotation free
else
  adb shell settings put system user_rotation 0
  adb shell settings put system accelerometer_rotation 1
fi
adb shell settings put system font_scale 1.0
# Test the actual launcher after instrumentation, at the original device configuration.
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
adb logcat -d -b events > evidence/android-events.txt
python3 - <<'ANR_CHECK'
import pathlib, re
log = pathlib.Path('evidence/android-events.txt').read_text()
assert not re.search(r'\bam_anr\b.*(?:com\.android\.systemui|com\.prettylisavpn\.android\.dev)', log), 'App/System UI ANR; inspect android-events.txt and last-anr.txt'
ANR_CHECK
cp apk/build-identity.json evidence/
adb shell getprop ro.build.version.sdk > evidence/emulator-api.txt
adb shell getprop ro.product.cpu.abi > evidence/emulator-abi.txt

# Capture the installed package icon on the native Android app-info screen.
adb shell am start -W -a android.settings.APPLICATION_DETAILS_SETTINGS -d "package:$package" > evidence/app-info-launch.txt
sleep 2
adb exec-out screencap -p > evidence/app-info-icon.png
