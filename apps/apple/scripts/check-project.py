"""Portable structural checks; not a substitute for compiling or live VPN acceptance."""
import json
import plistlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "Config").glob("*.entitlements"):
    value = plistlib.loads(path.read_bytes())
    if path.stem == 'Simulator':
        assert value == {'application-identifier': '$(PRODUCT_BUNDLE_IDENTIFIER)',
                         'keychain-access-groups': ['$(PRODUCT_BUNDLE_IDENTIFIER)']}
        continue
    assert value["com.apple.developer.networking.networkextension"] == ["packet-tunnel-provider"]
    assert value["keychain-access-groups"] == ["$(KEYCHAIN_GROUP)"]
    if path.stem.endswith('-iOS'):
        assert not any(key.startswith('com.apple.security.') for key in value), path
    else:
        assert value['com.apple.security.app-sandbox'] is True, path
        assert value['com.apple.security.network.client'] is True, path
        if path.stem == 'Tunnel':
            # Sandboxed UDP transports need permission to receive, not only send.
            assert value['com.apple.security.network.server'] is True, path
project = (ROOT / 'project.yml').read_text()
for target, entitlement in (('PrettyLisaVPN-iOS', 'App-iOS'), ('PacketTunnel-iOS', 'Tunnel-iOS')):
    settings = re.search(
        rf'^  {target}:\n(.*?)(?=^  \S|\Z)', project, re.MULTILINE | re.DOTALL
    ).group(1)
    assert f'CODE_SIGN_ENTITLEMENTS: Config/{entitlement}.entitlements' in settings
for platform, version in {"iOS": "0.2.1", "macOS": "0.2.1"}.items():
    assert f"MARKETING_VERSION = {version}" in (ROOT / f"Config/{platform}.xcconfig").read_text()
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
apple_copy = json.loads((ROOT / 'Config/AppleStrings.json').read_text(encoding='utf-8'))
for index, locale in enumerate(('en', 'ru', 'de', 'es', 'fr', 'zh-Hans')):
    text = (ROOT / f'Resources/{locale}.lproj/Localizable.strings').read_text(encoding='utf-8')
    assert '"apple_simulation"' in text and 'PrettyLisaVPN' in text
    for key in ('billing_portal', 'billing_reference_month'):
        # These labels are now Apple-owned; Android's redesigned screen no longer uses them.
        assert f'"{key}" = {json.dumps(apple_copy[key][index], ensure_ascii=False)};' in text
for path in ROOT.rglob('*'):
    if path.suffix in ('.swift', '.py', '.sh', '.yml', '.xcconfig') and not any(p in path.parts for p in ('.build', 'Vendor', 'DerivedData', 'artifacts')):
        assert not any(line.rstrip() != line for line in path.read_text(encoding='utf-8').splitlines()), path
print('Apple project boundaries, configuration, locales and source whitespace: OK')
