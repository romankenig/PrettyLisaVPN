"""Check actual Release binaries, including both slices of the macOS download."""
import json
import plistlib
from pathlib import Path

from macho_symbols import symbol_tables

ROOT = Path(__file__).resolve().parents[1]
report = {}


for platform, directory in (("iOS", "Release-iphoneos"), ("macOS", "Release")):
    app = ROOT / "DerivedData/Build/Products" / directory / "PrettyLisaVPN.app"
    binaries = []
    for bundle in (app, *app.rglob("*.appex")):
        content = bundle / "Contents" if platform == "macOS" else bundle
        info = plistlib.loads((content / "Info.plist").read_bytes())
        binary = (content / "MacOS" if platform == "macOS" else content) / info["CFBundleExecutable"]
        tables = symbol_tables(binary.read_bytes())
        expected_cpus = {0x100000c} if platform == "iOS" else {0x100000c, 0x1000007}
        assert {table["cpu"] for table in tables} == expected_cpus, "Missing native architecture"
        for table in tables:
            assert not table["debug"], (platform, binary.name, "Debugger records remain")
            assert not table["local"], (platform, binary.name, "Local symbols remain", table["local"][:10])
            if bundle.suffix == ".appex":
                assert {"_PLStart", "_PLStop", "_PLRunning"} <= table["external"], "Engine C exports missing"
        binaries.append({"path": str(binary.relative_to(app)), "bytes": binary.stat().st_size})
    assert len(binaries) == 2, (platform, "Expected app and tunnel binaries")
    report[platform] = {
        "bundle_bytes": sum(path.stat().st_size for path in app.rglob("*") if path.is_file()),
        "binaries": binaries,
        "local_symbols": 0,
        "engine_exports_preserved": True,
    }

target = ROOT / "artifacts/release-size.json"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(target.read_text(encoding="utf-8"))
