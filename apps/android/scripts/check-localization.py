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
for language in ('ru', 'zh', 'es', 'de', 'fr'):
    translated = read('values-' + language)
    assert translated.keys() == base.keys(), language
    for key, source in base.items():
        assert translated[key].strip(), (language, key)
        assert sorted(re.findall(r'%\d+\$[sd]', source)) == sorted(re.findall(r'%\d+\$[sd]', translated[key])), (language, key)
        if 'PrettyLisaVPN' in source:
            assert 'PrettyLisaVPN' in translated[key], (language, key)
print('All six language catalogs are complete; placeholders and brand casing match')
