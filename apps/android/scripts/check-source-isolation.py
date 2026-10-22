"""Both artifacts come from this checkout; release must have no test adapter class."""
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

for variant, filename in (("debug", "app-debug.apk"), ("release", "app-release-unsigned.apk")):
    with ZipFile(Path("app/build/outputs/apk") / variant / filename) as apk:
        dex = b"".join(apk.read(name) for name in apk.namelist() if name.endswith(".dex"))
    present = b"Lcom/prettylisavpn/android/data/FixtureSource;" in dex
    assert present == (variant == "debug"), (variant, present)
manifest = ET.parse("app/src/main/AndroidManifest.xml")
permissions = {p.attrib["{http://schemas.android.com/apk/res/android}name"] for p in manifest.findall("uses-permission")}
assert permissions == {"android.permission.INTERNET", "android.permission.ACCESS_NETWORK_STATE"}, permissions
assert manifest.find("application").attrib["{http://schemas.android.com/apk/res/android}usesCleartextTraffic"] == "false"
print("Debug fixture present; release fixture absent; main permits HTTPS auth, no VPN permission")
