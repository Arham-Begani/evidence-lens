"""Keep the new UI bound to immutable evidence and safe standalone output."""
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('desk_builder',ROOT/'scripts/build_desk.py')
desk=importlib.util.module_from_spec(spec)
spec.loader.exec_module(desk)


def test_frozen_answers_preserve_exact_grid_and_hashes():
    data=desk.load_frozen()
    assert len(data['outcomes'])==16
    assert sum(len(r['response']['claims']) for r in data['outcomes'])==35
    for row in data['outcomes']:
        raw=json.dumps(row['response'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
        assert hashlib.sha256(raw).hexdigest()==row['answer_sha256']


def test_data_cannot_close_the_script_element():
    html=desk.render({'outcomes':[], 'test':'</script><script>alert(1)</script>&'})
    assert '</script><script>alert(1)' not in html
    assert '\\u003c/script\\u003e' in html
    parser=desk.PayloadParser();parser.feed(html)
    assert json.loads(''.join(parser.parts))['test']=='</script><script>alert(1)</script>&'


def test_wrong_archive_rejected(tmp_path):
    altered=tmp_path/'wrong.zip';altered.write_bytes(b'not the frozen research release')
    with pytest.raises(ValueError,match='dataset changed'):desk.load_frozen(altered)


def test_existing_output_preserved(tmp_path):
    out=tmp_path/'index.html';out.write_bytes(b'existing evidence')
    with pytest.raises(ValueError,match='Output exists'):desk.build(out)
    assert out.read_bytes()==b'existing evidence'


def test_standalone_build_is_deterministic(tmp_path):
    a,b=tmp_path/'a.html',tmp_path/'b.html'
    desk.build(a);desk.build(b)
    assert a.read_bytes()==b.read_bytes()
    html=a.read_text(encoding='utf-8')
    assert '__DATA__' not in html
    assert '<script src=' not in html
    assert '<link rel="stylesheet"' not in html


def test_missing_template_marker_rejected(tmp_path):
    for name in ['desk.html','desk.css','desk.js']:
        text=(ROOT/'product'/name).read_text(encoding='utf-8')
        if name=='desk.html':text=text.replace('__DATA__','')
        (tmp_path/name).write_text(text,encoding='utf-8')
    with pytest.raises(ValueError,match='marker'):desk.render({'outcomes':[]},tmp_path)
