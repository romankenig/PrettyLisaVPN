"""Fixtures are debug-only; neither shipped variant contains a VPN engine/service."""
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

for variant, filename in (("debug", "app-debug.apk"), ("release", "app-release-unsigned.apk")):
    with ZipFile(Path("app/build/outputs/apk") / variant / filename) as apk:
        dex = b"".join(apk.read(name) for name in apk.namelist() if name.endswith(".dex"))
        assert (b"Lcom/prettylisavpn/android/data/FixtureSource;" in dex) == (variant == "debug")
        for removed in (b"Lcom/prettylisavpn/engine/", b"Lcom/prettylisavpn/enginecore/", b"Lcom/wireguard/"):
            assert removed not in dex, (variant, removed)
manifest = ET.parse("app/src/main/AndroidManifest.xml")
ns = "{http://schemas.android.com/apk/res/android}"
assert {p.attrib[ns+"name"] for p in manifest.findall("uses-permission")} == {"android.permission.INTERNET", "android.permission.ACCESS_NETWORK_STATE"}
assert not manifest.find("application").findall("service")
assert manifest.find("application").attrib[ns+"usesCleartextTraffic"] == "false"
print("Debug fixtures isolated; no VPN engine/service/foreground permissions")
