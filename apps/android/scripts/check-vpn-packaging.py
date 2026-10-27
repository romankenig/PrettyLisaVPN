"""Allow the requested MIT WireGuard runtime; reject former engines and GPL utilities."""
from pathlib import Path
from zipfile import ZipFile
import json

report = {}
for variant, filename in (("debug", "app-debug.apk"), ("release", "app-release-unsigned.apk")):
    path = Path("app/build/outputs/apk") / variant / filename
    with ZipFile(path) as apk:
        assert len(apk.read("assets/licenses/Rubik-OFL.txt")) > 1000
        assert not any(name.endswith(("libgojni.so", "libwg.so", "libwg-quick.so")) for name in apk.namelist())
        for abi in ("arm64-v8a", "armeabi-v7a", "x86", "x86_64"):
            assert f"lib/{abi}/libwg-go.so" in apk.namelist()
        for license in ("WireGuard-Android-Apache-2.0.txt", "WireGuard-Go-MIT.txt", "Go-BSD-3-Clause.txt"):
            assert len(apk.read("assets/licenses/" + license)) > 1000
        assert not any(name.startswith("assets/engine-licenses/") for name in apk.namelist())
    report[variant] = {"apk_bytes": path.stat().st_size, "vpn_engine": "wireguard-go", "companion_apk_required": False}
target = Path("app/build/reports/placeholder-packaging.json")
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(report, indent=2))
print(json.dumps(report))
