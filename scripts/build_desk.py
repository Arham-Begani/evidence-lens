"""Render a new product view from the public saved-evidence view, never overwriting results."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/saved-development.json'
DATA_SHA = 'f3cae52d16b0150a87ee4867dfa5154d9c610c8d3985593ec7b73bcaee18d883'


class PayloadParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.capture=False; self.parts=[]; self.count=0
    def handle_starttag(self, tag, attrs):
        if tag=='script' and dict(attrs).get('id')=='study-data': self.capture=True; self.count+=1
    def handle_data(self, data):
        if self.capture:self.parts.append(data)
    def handle_endtag(self, tag):
        if tag=='script':self.capture=False


def load_frozen(path=DATA):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Frozen public dataset changed')
    data=json.loads(raw); records=data['outcomes']
    grid={(m,c) for m in ('ordinary','instruction','document','ledger') for c in ('base','repeat','new','mixed')}
    if len(records)!=16 or {(r['method'],r['condition']) for r in records}!=grid:raise ValueError('Incomplete saved response grid')
    for record in records:
        encoded=json.dumps(record['response'],ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
        if hashlib.sha256(encoded).hexdigest()!=record['answer_sha256']:raise ValueError('Saved answer hash mismatch')
        if not re.fullmatch(r'[a-f0-9]{24}(?:/attempt-\d+)?',record['relative_directory']):raise ValueError('Unsafe raw evidence path')
    return data


def render(data, source=ROOT / 'product'):
    payload = json.dumps(data, ensure_ascii=True, allow_nan=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    template = (source / 'desk.html').read_text(encoding='utf-8')
    for marker, value in [('__STYLES__', (source / 'desk.css').read_text(encoding='utf-8')),
                          ('__DATA__', payload), ('__SCRIPT__', (source / 'desk.js').read_text(encoding='utf-8'))]:
        if template.count(marker) != 1:
            raise ValueError('Missing or duplicate template marker: ' + marker)
        template = template.replace(marker, value)
    return template


def build(output):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Output exists; preserve it and use a new candidate path')
    data = load_frozen()
    text = render(data)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(text)
    return {'output': str(output), 'saved_responses': len(data['outcomes']),
            'claims': sum(len(r['response']['claims']) for r in data['outcomes']),
            'new_inference': 0, 'bytes': output.stat().st_size,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'preexisting_preparation': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output')
    print(json.dumps(build(parser.parse_args().output), indent=2))
