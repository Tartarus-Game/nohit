"""Immutable CSV transport shared by the native custom loader and solver."""
import hashlib
from pathlib import Path

from nohit.engine.csv_preparation import prepare_csv_bytes
from nohit.engine.source_contract import native_source_diagnostics
from nohit.engine.timeline_csv import parse_timeline_rows


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
    original_raw = raw
    prepared = prepare_csv_bytes(raw)
    raw, text = prepared['raw'], prepared['text']
    identity = hashlib.sha256(raw).hexdigest()
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    # This is admission only; a supported source still needs search, completion
    # proof and native replay. Inspect the immutable bytes we actually serve.
    diagnostics = native_source_diagnostics(parse_timeline_rows(text),
        allow_player_history=True, termination_policy='eof_hazards_drained')
    item = dict(id=identity, name=name, sha256=digest, raw_sha256=identity,
                text=text, byte_count=len(raw), url='/api/csv-source/'+identity+'.csv',
                preflight=dict(supported=not diagnostics['issues'], **diagnostics, scope='source_admission_only',
                               termination_policy='eof_hazards_drained'))
    sources.setdefault(identity, (raw, item))
    if prepared['preparation']['changes']:
        # Several imports may prepare to the same executable bytes. Keep the
        # content-addressed executable descriptor independent of any one origin.
        import_id = prepared['preparation']['original_raw_sha256']
        import_url = '/api/csv-source/import/' + import_id
        warnings = sorted(diagnostics['warnings'] + prepared['warnings'],
                          key=lambda warning: warning['line'])
        item = dict(item, import_id=import_id, import_url=import_url,
                    original_url=import_url+'.original.csv',
                    original_byte_count=len(original_raw),
                    preparation=prepared['preparation'], warnings=warnings,
                    preflight=dict(item['preflight'], warnings=warnings))
        sources.setdefault('import:'+import_id, (raw, item, original_raw))
    return {key:value for key,value in item.items() if key != 'text'}
