"""Lossless content-addressed storage for large continuous-game evidence."""
import base64
import hashlib
import json
import re


MAX_PART_BYTES = 2_000_000
PART_STORAGE = 'json-utf8-parts-v1'


def store_evidence_part(data, folder):
    if not isinstance(data, dict) or data.get('evidenceVersion') != 3 or data.get('encoding') != 'base64':
        raise ValueError('Invalid campaign evidence part')
    digest = data.get('sha256')
    if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
        raise ValueError('Invalid evidence part hash')
    raw = base64.b64decode(data.get('data', ''), validate=True)
    if not 0 < len(raw) <= MAX_PART_BYTES or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('Evidence part bytes do not match their size/hash contract')
    relative = 'campaign-evidence/' + digest + '.bin'
    path = folder / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError('Stored evidence part differs from its content identity')
    else:
        path.write_bytes(raw)
    return {'path': relative, 'sha256': digest, 'byte_count': len(raw)}


def read_evidence_manifest(data, folder):
    """Validate every byte reference before accepting a campaign manifest."""
    if data.get('storage') != PART_STORAGE:
        return data
    if data.get('suite') != 'continuous-normal-game' or data.get('evidenceVersion') != 3:
        raise ValueError('Unsupported evidence manifest protocol')
    parts = data.get('evidenceParts')
    if not isinstance(parts, list) or not parts:
        raise ValueError('Evidence manifest has no parts')
    blocks = []
    for index, part in enumerate(parts):
        if not isinstance(part, dict) or type(part.get('index')) is not int or part['index'] != index:
            raise ValueError('Evidence part order is incomplete')
        digest = part.get('sha256')
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('Invalid evidence part hash')
        relative = 'campaign-evidence/' + digest + '.bin'
        if part.get('path') != relative:
            raise ValueError('Evidence part path differs from its content identity')
        raw = (folder / relative).read_bytes()
        if (type(part.get('byte_count')) is not int or len(raw) != part['byte_count'] or
                not 0 < len(raw) <= MAX_PART_BYTES or hashlib.sha256(raw).hexdigest() != digest):
            raise ValueError('Stored evidence part is missing, truncated or altered')
        blocks.append(raw)
    raw = b''.join(blocks)
    if (type(data.get('total_byte_count')) is not int or len(raw) != data['total_byte_count'] or
            hashlib.sha256(raw).hexdigest() != data.get('total_sha256')):
        raise ValueError('Complete evidence bytes differ from the manifest')
    restored = json.loads(raw.decode('utf-8'))
    if not isinstance(restored, dict) or restored.get('storage') == PART_STORAGE:
        raise ValueError('Nested or invalid evidence payload')
    for key in ('suite', 'evidenceVersion', 'seed', 'clock', 'criterion', 'result'):
        if restored.get(key) != data.get(key):
            raise ValueError('Evidence manifest metadata differs from its payload: ' + key)
    return restored
