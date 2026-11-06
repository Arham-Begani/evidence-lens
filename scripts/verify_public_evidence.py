"""Verify public evidence hashes and blank human-review fields; no network or inference."""
import csv
import hashlib
import json
from pathlib import Path

from build_desk import load_frozen, render

ROOT=Path(__file__).resolve().parents[1]


def verify(root=ROOT):
    root=Path(root).resolve()
    manifest=json.loads((root/'site/publication.json').read_text(encoding='utf-8'))
    data=load_frozen(root/'data/saved-development.json')
    for path,field in (('data/saved-development.json','source_payload_sha256'),('site/semantic-review-blank.csv','blank_review_sha256')):
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=manifest[field]:
            raise ValueError('Public manifest hash mismatch: '+path)
    raw=manifest['preserved_original_files']
    expected={'site/'+r['relative_directory']+'/'+name for r in data['outcomes'] for name in ('answer.json','prompt.txt')}
    if len(raw)!=32 or {r['path'] for r in raw}!=expected:
        raise ValueError('Incomplete raw evidence manifest')
    for record in raw:
        path=(root/record['path']).resolve()
        if not path.is_relative_to(root/'site'):
            raise ValueError('Unsafe evidence path')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:
            raise ValueError('Raw evidence hash mismatch: '+record['path'])
    for record in data['outcomes']:
        answer=json.loads((root/'site'/record['relative_directory']/'answer.json').read_text(encoding='utf-8-sig'))
        if answer!=record['response']:
            raise ValueError('Public view differs from recorded answer')
    with (root/'site/semantic-review-blank.csv').open(encoding='utf-8',newline='') as stream:
        rows=list(csv.DictReader(stream))
    if len(rows)!=16 or {r['task_id'] for r in rows}!={r['task_id'] for r in data['outcomes']}:
        raise ValueError('Incomplete blank review sheet')
    for row in rows:
        if any(row[field] for field in ('reviewer','a_retained','b_retained','citations_supported','false_independence','unsupported_claim','notes')):
            raise ValueError('Blank review sheet contains a decision')
    if render(data,root/'product').encode('utf-8')!=(root/'site/desk/index.html').read_bytes():
        raise ValueError('Published page differs from reproducible build')
    return {'status':'passed','saved_responses':16,'claims':sum(len(r['response']['claims']) for r in data['outcomes']),
            'raw_files_verified':32,'blank_reviews':16,'page_byte_reproducible':True,'new_model_calls':0,
            'scope':'Integrity of stored public evidence, not independent semantic validation or exact model regeneration.'}


if __name__=='__main__':print(json.dumps(verify(),indent=2))
