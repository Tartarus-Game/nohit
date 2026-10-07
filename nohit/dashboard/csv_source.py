"""Immutable CSV transport shared by the native custom loader and solver."""
import hashlib
from pathlib import Path


def register_csv_source(data, sources):
    if not isinstance(data, dict):
        raise ValueError('Request must be an object')
    path, content = data.get('csv_path'), data.get('custom_csv')
    if bool(path) == bool(content):
        raise ValueError('Provide exactly one csv_path or custom_csv')
    if path:
        if not isinstance(path, str):
            raise ValueError('csv_path must be a string')
        source = Path(path).expanduser().resolve()
        if source.suffix.lower() != '.csv':
            raise ValueError('A CSV file is required')
        raw, name = source.read_bytes(), source.name
    else:
        if not isinstance(content, str):
            raise ValueError('custom_csv must be a string')
        raw, name = content.encode('utf-8'), 'custom.csv'
    # Match the native UTF-8 AJAX text decoding, including its BOM handling.
    # The downloaded source retains every original byte.
    text = raw.decode('utf-8-sig').replace('\r\n', '\n')
    identity = hashlib.sha256(raw).hexdigest()
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    item = dict(id=identity, name=name, sha256=digest, raw_sha256=identity,
                text=text, byte_count=len(raw), url='/api/csv-source/'+identity+'.csv')
    sources.setdefault(identity, (raw, item))
    return {key:value for key,value in item.items() if key != 'text'}
