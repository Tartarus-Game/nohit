"""Prepare an explicit no-hit script without disabling native collision damage."""
import hashlib


def prepare_csv_bytes(raw):
    """Disable CSV DamagePlayer calls, preserving every delay and line boundary.

    Native Timeline has no comment syntax. An empty command cell has no effect;
    keeping the remaining cells preserves the user's source for precise diffs.
    This never changes the game's DamagePlayer handler or collision events.
    """
    lines=raw.split(b'\n');changes=[];warnings=[]
    for number,line in enumerate(lines,1):
        ending=b'\r' if line.endswith(b'\r') else b''
        content=line[:-1] if ending else line
        cells=content.split(b',')
        if len(cells)<2 or cells[1].strip().lower()!=b'damageplayer':
            continue
        command=cells[1].decode('utf-8')
        changes.append(dict(line=number,command=command,action='disable_command_keep_delay'))
        warnings.append(dict(line=number,command=command,reason='scripted_damage_disabled'))
        cells[1]=b'';lines[number-1]=b','.join(cells)+ending
    executable=b'\n'.join(lines)
    return dict(raw=executable,text=executable.decode('utf-8-sig').replace('\r\n','\n'),
        warnings=warnings,preparation=dict(schema_version=1,policy='disable-scripted-damage-v1',
            original_raw_sha256=hashlib.sha256(raw).hexdigest(),
            executable_raw_sha256=hashlib.sha256(executable).hexdigest(),changes=changes))
