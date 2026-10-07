"""Complete evidence remains verifiable when split across the POST limit."""
import base64
import copy
import hashlib
import json

import pytest

from nohit.dashboard.acceptance_evidence import read_evidence_manifest, store_evidence_part


def make_manifest(tmp_path, payload, chunk_size=53):
    raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    parts = []
    for start in range(0, len(raw), chunk_size):
        part = raw[start:start + chunk_size]
        stored = store_evidence_part({'evidenceVersion': 3, 'encoding': 'base64',
            'sha256': hashlib.sha256(part).hexdigest(),
            'data': base64.b64encode(part).decode()}, tmp_path)
        parts.append(dict(index=len(parts), **stored))
    return {**{key: payload.get(key) for key in ('suite', 'evidenceVersion', 'seed', 'clock', 'criterion', 'result')},
        'storage': 'json-utf8-parts-v1', 'evidenceParts': parts, 'total_byte_count': len(raw),
        'total_sha256': hashlib.sha256(raw).hexdigest()}


def payload():
    return {'suite': 'continuous-normal-game', 'evidenceVersion': 3, 'seed': 42,
        'clock': 'original-runtime-realtime-catchup-240hz', 'criterion': 'test',
        'result': {'passed': True, 'status': 'passed'},
        'tickEvidence': [[i, 92, 0, i % 24, 0, 31, 1, 1 / 240, i * 1000 / 240,
            0, [320, 304, 0, 0, 31, 0, 0, 1, 750, 0, 0]] for i in range(50)],
        'computedPlans': [{'sourceText': '原字节\r\n', 'actions': [1, 2], 'confirm_sequence': [True, False]}]}


def test_complete_utf8_evidence_roundtrips_across_arbitrary_byte_boundaries(tmp_path):
    original = payload()
    manifest = make_manifest(tmp_path, original)
    assert len(manifest['evidenceParts']) > 1
    assert read_evidence_manifest(manifest, tmp_path) == original


@pytest.mark.parametrize('change', ['order', 'missing', 'path', 'part_hash', 'part_size',
    'total_hash', 'total_size', 'metadata'])
def test_manifest_rejects_missing_altered_or_reordered_evidence(tmp_path, change):
    manifest = make_manifest(tmp_path, payload())
    part = manifest['evidenceParts'][0]
    if change == 'order':
        manifest['evidenceParts'][:2] = reversed(manifest['evidenceParts'][:2])
    elif change == 'missing':
        (tmp_path / part['path']).unlink()
    elif change == 'path':
        part['path'] = '../outside.bin'
    elif change == 'part_hash':
        (tmp_path / part['path']).write_bytes(b'x' * part['byte_count'])
    elif change == 'part_size':
        part['byte_count'] += 1
    elif change == 'total_hash':
        manifest['total_sha256'] = '0' * 64
    elif change == 'total_size':
        manifest['total_byte_count'] += 1
    else:
        manifest['result']['passed'] = False
    with pytest.raises((ValueError, FileNotFoundError)):
        read_evidence_manifest(manifest, tmp_path)


def test_part_hash_is_checked_before_any_write_and_repeated_upload_is_immutable(tmp_path):
    data = {'evidenceVersion': 3, 'encoding': 'base64', 'data': base64.b64encode(b'proof').decode(),
        'sha256': hashlib.sha256(b'proof').hexdigest()}
    altered = copy.deepcopy(data)
    altered['sha256'] = '0' * 64
    with pytest.raises(ValueError):
        store_evidence_part(altered, tmp_path)
    assert not list(tmp_path.iterdir())
    first = store_evidence_part(data, tmp_path)
    assert store_evidence_part(data, tmp_path) == first
    assert (tmp_path / first['path']).read_bytes() == b'proof'


def test_an_inline_record_is_not_reinterpreted(tmp_path):
    original = payload()
    assert read_evidence_manifest(original, tmp_path) is original
