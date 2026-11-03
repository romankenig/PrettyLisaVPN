"""Portable structural checks; not a substitute for compiling or live VPN acceptance."""
import json
import plistlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "Config").glob("*.entitlements"):
    value = plistlib.loads(path.read_bytes())
    assert value["com.apple.developer.networking.networkextension"] == ["packet-tunnel-provider"]
    assert value["keychain-access-groups"] == ["$(KEYCHAIN_GROUP)"]
for platform in ("iOS", "macOS"):
    assert "MARKETING_VERSION = 0.1.0" in (ROOT / f"Config/{platform}.xcconfig").read_text()
model = (ROOT / "App/AppModel.swift").read_text()
assert '#if DEBUG' in model
assert '#if targetEnvironment(simulator)' in model
assert 'case .connected' in (ROOT / "App/Views.swift").read_text()
provider = (ROOT / "Extension/PacketTunnelProvider.swift").read_text()
assert 'createTCPConnectionThroughTunnel' in provider
assert 'ipv6.includedRoutes = [.default()]' in provider
assert 'passwordReference' in provider
assert not re.search(r'value\(forKeyPath:|NSAllowsArbitraryLoads|allowInsecure.*true', '\n'.join(p.read_text() for p in ROOT.rglob('*.swift') if '.build' not in p.parts))
for path in (ROOT / "Resources").rglob("*.json"):
    json.loads(path.read_text(encoding="utf-8"))
for locale in ('en', 'ru', 'de', 'es', 'fr', 'zh-Hans'):
    text = (ROOT / f'Resources/{locale}.lproj/Localizable.strings').read_text(encoding='utf-8')
    assert '"apple_simulation"' in text and 'PrettyLisaVPN' in text
for path in ROOT.rglob('*'):
    if path.suffix in ('.swift', '.py', '.sh', '.yml', '.xcconfig') and not any(p in path.parts for p in ('.build', 'Vendor', 'DerivedData', 'artifacts')):
        assert not any(line.rstrip() != line for line in path.read_text(encoding='utf-8').splitlines()), path
print('Apple project boundaries, configuration, locales and source whitespace: OK')
