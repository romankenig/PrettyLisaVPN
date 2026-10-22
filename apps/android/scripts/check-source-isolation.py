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
assert permissions == {"android.permission.INTERNET", "android.permission.ACCESS_NETWORK_STATE", "android.permission.FOREGROUND_SERVICE", "android.permission.FOREGROUND_SERVICE_SYSTEM_EXEMPTED", "android.permission.POST_NOTIFICATIONS"}, permissions
services = manifest.find("application").findall("service")
service = next(s for s in services if s.attrib["{http://schemas.android.com/apk/res/android}name"] == ".vpn.PrettyVpnService")
assert service.attrib["{http://schemas.android.com/apk/res/android}permission"] == "android.permission.BIND_VPN_SERVICE"
assert service.attrib["{http://schemas.android.com/apk/res/android}exported"] == "false"
assert service.attrib["{http://schemas.android.com/apk/res/android}foregroundServiceType"] == "systemExempted"
assert next(s for s in services if s.attrib["{http://schemas.android.com/apk/res/android}name"] == "com.wireguard.android.backend.GoBackend$VpnService").attrib["{http://schemas.android.com/tools}node"] == "remove"
assert manifest.find("application").attrib["{http://schemas.android.com/apk/res/android}usesCleartextTraffic"] == "false"
print("Debug fixture present; release fixture absent; HTTPS only; one protected VPN foreground service")
