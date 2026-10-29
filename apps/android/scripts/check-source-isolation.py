"""Fixtures remain debug-only; real engines stay private inside one APK."""
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

for variant, filename in (("debug", "app-debug.apk"), ("release", "app-release-unsigned.apk")):
    with ZipFile(Path("app/build/outputs/apk") / variant / filename) as apk:
        dex = b"".join(apk.read(name) for name in apk.namelist() if name.endswith(".dex"))
        assert (b"Lcom/prettylisavpn/android/data/FixtureSource;" in dex) == (variant == "debug")
        assert b"Lcom/wireguard/android/backend/GoBackend;" in dex
        assert (b"Lcom/prettylisavpn/android/vpn/placeholders/" in dex) == (variant == "debug")
        for required in (b"Lcom/prettylisavpn/engine/EngineService;", b"Lcom/prettylisavpn/enginecore/mobile/Mobile;"):
            assert required in dex, (variant, required)
manifest = ET.parse("app/src/main/AndroidManifest.xml")
ns = "{http://schemas.android.com/apk/res/android}"
assert {p.attrib[ns+"name"] for p in manifest.findall("uses-permission")} == {"android.permission.INTERNET", "android.permission.ACCESS_NETWORK_STATE", "android.permission.FOREGROUND_SERVICE", "android.permission.FOREGROUND_SERVICE_SYSTEM_EXEMPTED"}
assert all(service.attrib[ns+"exported"] == "false" for service in manifest.find("application").findall("service"))
assert manifest.find("application").attrib[ns+"usesCleartextTraffic"] == "false"
print("Debug fixtures isolated; one APK with WireGuard and private managed engines")
