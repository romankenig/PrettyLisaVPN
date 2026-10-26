"""Ensure removed engines cannot silently return through a transitive dependency."""
from pathlib import Path
from zipfile import ZipFile
import json

report = {}
for variant, filename in (("debug", "app-debug.apk"), ("release", "app-release-unsigned.apk")):
    path = Path("app/build/outputs/apk") / variant / filename
    with ZipFile(path) as apk:
        assert not any(name.endswith(("libgojni.so", "libwg.so", "libwg-go.so", "libwg-quick.so")) for name in apk.namelist())
        assert not any(name.startswith("assets/engine-licenses/") for name in apk.namelist())
    report[variant] = {"apk_bytes": path.stat().st_size, "vpn_engine_present": False}
target = Path("app/build/reports/placeholder-packaging.json")
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(report, indent=2))
print(json.dumps(report))
