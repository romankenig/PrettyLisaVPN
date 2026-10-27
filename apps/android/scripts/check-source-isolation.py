"""Fixtures remain debug-only; only the requested WireGuard runtime is shipped."""
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

for variant, filename in (("debug", "app-debug.apk"), ("release", "app-release-unsigned.apk")):
    with ZipFile(Path("app/build/outputs/apk") / variant / filename) as apk:
        dex = b"".join(apk.read(name) for name in apk.namelist() if name.endswith(".dex"))
        assert (b"Lcom/prettylisavpn/android/data/FixtureSource;" in dex) == (variant == "debug")
        assert b"Lcom/wireguard/android/backend/GoBackend;" in dex
        for removed in (b"Lcom/prettylisavpn/engine/", b"Lcom/prettylisavpn/enginecore/"):
            assert removed not in dex, (variant, removed)
manifest = ET.parse("app/src/main/AndroidManifest.xml")
ns = "{http://schemas.android.com/apk/res/android}"
assert {p.attrib[ns+"name"] for p in manifest.findall("uses-permission")} == {"android.permission.INTERNET", "android.permission.ACCESS_NETWORK_STATE", "android.permission.FOREGROUND_SERVICE", "android.permission.FOREGROUND_SERVICE_SYSTEM_EXEMPTED"}
assert all(service.attrib[ns+"exported"] == "false" for service in manifest.find("application").findall("service"))
assert manifest.find("application").attrib[ns+"usesCleartextTraffic"] == "false"
print("Debug fixtures isolated; one APK with WireGuard and a private foreground service")
