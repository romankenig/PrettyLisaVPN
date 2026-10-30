"""One APK contains the audited WireGuard and managed cores, without GPL utilities."""
from pathlib import Path
from zipfile import ZipFile
import json

report = {}
expected = {"arm64-v8a", "armeabi-v7a", "x86", "x86_64"}
for variant in ("debug", "release"):
    directory = Path("app/build/outputs/apk") / variant
    metadata = json.loads((directory / "output-metadata.json").read_text())
    seen = set()
    for element in metadata["elements"]:
        abi_filter, = element["filters"]
        assert abi_filter["filterType"] == "ABI"
        abi = abi_filter["value"]
        assert abi in expected and abi not in seen
        seen.add(abi)
        path = directory / element["outputFile"]
        assert path.stat().st_size <= 40_000_000, (variant, abi, "APK exceeds 40 MB")
        with ZipFile(path) as apk:
            assert len(apk.read("assets/licenses/Rubik-OFL.txt")) > 1000
            natives = [name for name in apk.namelist() if name.startswith("lib/") and name.endswith(".so")]
            assert {name.split("/")[1] for name in natives} == {abi}
            assert not any(name.endswith(("libwg.so", "libwg-quick.so")) for name in natives)
            for library in ("libwg-go.so", "libgojni.so"):
                name = f"lib/{abi}/{library}"
                assert name in natives
                assert apk.getinfo(name).compress_type == 8, "Native library must be deflated"
            # Linker debug sections must not be shipped in the managed core.
            native = apk.read(f"lib/{abi}/libgojni.so")
            assert b".debug_info\0" not in native and b".debug_line\0" not in native
            for license in ("WireGuard-Android-Apache-2.0.txt", "WireGuard-Go-MIT.txt", "Go-BSD-3-Clause.txt"):
                assert len(apk.read("assets/licenses/" + license)) > 1000
            assert any(name.startswith("assets/engine-licenses/") for name in apk.namelist())
        report[f"{variant}/{abi}"] = {"apk_bytes": path.stat().st_size, "vpn_engines": ["wireguard-go", "managed-xray"], "companion_apk_required": False}
    assert seen == expected

target = Path("app/build/reports/placeholder-packaging.json")
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(report, indent=2))
print(json.dumps(report))
