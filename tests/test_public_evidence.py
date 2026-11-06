"""Check that the public verifier detects corruption and false review completion."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('public_verifier',ROOT/'scripts/verify_public_evidence.py')
verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)


def test_public_release_integrity():
    result=verifier.verify()
    assert result['raw_files_verified']==32 and result['blank_reviews']==16


@pytest.mark.parametrize('mutation,expected',[
    ('prompt','Raw evidence hash mismatch'),
    ('human-decision','contains a decision'),
    ('page','differs from reproducible build'),
])
def test_public_verifier_rejects_mutation(tmp_path,mutation,expected):
    for name in ('data','product','site'):
        shutil.copytree(ROOT/name,tmp_path/name)
    manifest_path=tmp_path/'site/publication.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    if mutation=='prompt':
        row=next(r for r in manifest['preserved_original_files'] if r['path'].endswith('/prompt.txt'))
        with (tmp_path/row['path']).open('a',encoding='utf-8') as stream:stream.write('\nChanged')
    elif mutation=='page':
        with (tmp_path/'site/desk/index.html').open('a',encoding='utf-8') as stream:stream.write('\nChanged')
    else:
        path=tmp_path/'site/semantic-review-blank.csv'
        with path.open(encoding='utf-8',newline='') as stream:rows=list(csv.DictReader(stream))
        rows[0]['reviewer']='SCRIPTED_TEST_NOT_HUMAN'
        with path.open('w',encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        manifest['blank_review_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest),encoding='utf-8')
    with pytest.raises(ValueError,match=expected):verifier.verify(tmp_path)
