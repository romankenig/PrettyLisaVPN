"""Current APK: required ABIs, 16KiB ELF alignment, notices and service ownership."""
from pathlib import Path
from zipfile import ZipFile
import hashlib
import json
import struct
import xml.etree.ElementTree as ET

reports = Path('app/build/reports/vpn')
reports.mkdir(parents=True, exist_ok=True)
result = {}
for variant, filename in [('debug', 'app-debug.apk'), ('release', 'app-release-unsigned.apk')]:
    with ZipFile(Path('app/build/outputs/apk') / variant / filename) as apk:
        entries = {}
        assert not any(n.endswith(('/libwg.so', '/libwg-quick.so')) for n in apk.namelist()), 'unused root tools packaged'
        required = {f'lib/{abi}/libwg-go.so' for abi in ('arm64-v8a', 'x86_64')}
        assert required <= set(apk.namelist())
        for name in sorted(n for n in apk.namelist() if n.startswith(('lib/arm64-v8a/', 'lib/x86_64/')) and n.endswith('.so')):
            data = apk.read(name)
            assert data[:6] == b'\x7fELF\x02\x01', name
            offset = struct.unpack_from('<Q', data, 32)[0]
            size, count = struct.unpack_from('<HH', data, 54)
            alignments = []
            for i in range(count):
                header = struct.unpack_from('<IIQQQQQQ', data, offset + size*i)
                if header[0] == 1:
                    alignments.append(header[7])
                    assert header[7] >= 16384, (name, 'ELF alignment', header[7])
            assert alignments, name
            entries[name] = {'sha256': hashlib.sha256(data).hexdigest(), 'load_alignments': alignments}
        for license_name in ('WireGuard-Android-Apache-2.0.txt', 'wireguard-go-MIT.txt', 'wireguard-tools-GPL-2.0.txt', 'Go-BSD-3-Clause.txt'):
            assert len(apk.read('assets/licenses/' + license_name)) > 1000
        result[variant] = entries
    candidates = list(Path(f'app/build/intermediates/merged_manifests/{variant}').rglob('AndroidManifest.xml'))
    assert len(candidates) == 1, candidates
    manifest = ET.parse(candidates[0]).getroot()
    ns = '{http://schemas.android.com/apk/res/android}'
    services = manifest.find('application').findall('service')
    vpn = [s for s in services if any(a.attrib.get(ns+'name') == 'android.net.VpnService' for f in s.findall('intent-filter') for a in f.findall('action'))]
    assert len(vpn) == 1, [(s.attrib) for s in vpn]
    assert vpn[0].attrib[ns+'name'] == 'com.prettylisavpn.android.vpn.PrettyVpnService'
    assert vpn[0].attrib[ns+'permission'] == 'android.permission.BIND_VPN_SERVICE'
    assert vpn[0].attrib[ns+'exported'] == 'false'
    assert vpn[0].attrib[ns+'foregroundServiceType'] == 'systemExempted'
import os
cache = Path(os.environ.get('GRADLE_USER_HOME', str(Path.home()/'.gradle')))
aars = list((cache/'caches/modules-2/files-2.1/com.wireguard.android/tunnel/1.0.20260102').glob('*/*.aar'))
assert len(aars) == 1, aars
result['wireguard_aar_sha256'] = hashlib.sha256(aars[0].read_bytes()).hexdigest()
assert result['wireguard_aar_sha256'] == '2b9c16db026496123e4db695d26d03d1958a201096c7c4c89b21077dc70f3119', 'reviewed WireGuard AAR changed'
print('WireGuard 1.0.20260102 AAR SHA256:', result['wireguard_aar_sha256'])
(reports / 'native-packaging.json').write_text(json.dumps(result, indent=2)+'\n')
print('Current APK: arm64/x86_64 WireGuard, 16KiB ELF, notices, single protected FGS verified')
