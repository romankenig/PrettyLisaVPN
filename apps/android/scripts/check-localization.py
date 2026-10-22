"""Every supported locale must have the same resource keys and format arguments."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET

res = Path('app/src/main/res')
def read(folder):
    nodes = ET.parse(res / folder / 'strings.xml').getroot()
    result = {n.attrib['name']: n.text or '' for n in nodes if n.attrib.get('translatable') != 'false'}
    assert len(result) == len([n for n in nodes if n.attrib.get('translatable') != 'false']), folder
    return result

base = read('values')
# Lowercase starts are an editorial rule on templates, never a runtime transform
# of formatted email, device names, API messages or other user/server content.
proper_prefixes = ('PrettyLisaVPN', 'Android', 'WireGuard', 'VPN', 'IP:', 'ID:',
                   'UTC', 'PNG', 'JPEG', 'WebP', 'Alipay', 'WeChat', 'Mir ', 'MIR',
                   'Premium', 'Platinum', 'Free')
for folder in ('values', 'values-ru', 'values-zh', 'values-es', 'values-de', 'values-fr'):
    for key, text in read(folder).items():
        assert not text[0].isupper() or text.startswith(proper_prefixes), (folder, key, 'uppercase start')
        assert not re.match(r'[a-zа-яà-ÿ][A-ZА-ЯÀ-Ý]{2}', text), (folder, key, 'mixed initial case')
        for word in re.findall(r'[.!?] +([A-ZА-ЯЁÀ-Ý][\w-]*)', text):
            assert word.startswith(proper_prefixes + ('BANK_CARD', 'LIVE', 'SANDBOX', 'DISABLED', 'IP', 'ID')), (folder, key, 'uppercase sentence start', word)
        if folder in ('values-zh', 'values-es', 'values-fr', 'values-de'):
            assert not re.search(r'\bemail\b', text, re.I), (folder, key, 'unlocalized email')
for language in ('ru', 'zh', 'es', 'de', 'fr'):
    translated = read('values-' + language)
    assert translated.keys() == base.keys(), language
    for key, source in base.items():
        assert translated[key].strip(), (language, key)
        assert sorted(re.findall(r'%\d+\$[sd]', source)) == sorted(re.findall(r'%\d+\$[sd]', translated[key])), (language, key)
        if 'PrettyLisaVPN' in source:
            assert 'PrettyLisaVPN' in translated[key], (language, key)
print('All six catalogs: parity, placeholders, brand casing, lowercase sentence starts and email terminology verified')
