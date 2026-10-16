"""Default import cleanup changes only explicit scripted health commands."""
import hashlib

from nohit.engine.csv_preparation import prepare_csv_bytes


def test_disables_scripted_damage_and_healing_without_changing_delays_or_other_rows():
    raw = b'\xef\xbb\xbf0,HeartMode,0\r\n1.25,DaMaGePlAyEr,-10000,,,,\r\n0,DamagePlayer,5,1\r\n0,SansSlamDamage,1\n0,BoneV,1,2,3,4,5\n'
    result = prepare_csv_bytes(raw)
    expected = raw.replace(b'DaMaGePlAyEr', b'').replace(b'DamagePlayer', b'')
    assert result['raw'] == expected
    assert result['text'] == expected.decode('utf-8-sig').replace('\r\n', '\n')
    assert [(row['line'], row['command'], row['reason']) for row in result['warnings']] == [
        (2, 'DaMaGePlAyEr', 'scripted_damage_disabled'), (3, 'DamagePlayer', 'scripted_damage_disabled')]
    preparation = result['preparation']
    assert preparation['original_raw_sha256'] == hashlib.sha256(raw).hexdigest()
    assert preparation['executable_raw_sha256'] == hashlib.sha256(expected).hexdigest()
    assert [change['action'] for change in preparation['changes']] == ['disable_command_keep_delay'] * 2


def test_cleanup_is_idempotent_and_does_not_treat_text_or_near_names_as_commands():
    raw = b'0,SansText,DamagePlayer,\n0,DamagePlayers,2\n0,damageplayer,NaN,\n'
    first = prepare_csv_bytes(raw)
    second = prepare_csv_bytes(first['raw'])
    assert second['raw'] == first['raw']
    assert second['warnings'] == [] and second['preparation']['changes'] == []
    assert b'0,SansText,DamagePlayer,' in first['raw']
    assert b'0,DamagePlayers,2' in first['raw']


def test_unchanged_input_keeps_every_byte_and_native_line_numbers():
    raw = '0,SansText,你好\r\n\n0,EndAttack\r'.encode('utf-8')
    result = prepare_csv_bytes(raw)
    assert result['raw'] == raw
    assert result['warnings'] == []


def test_lone_cr_is_not_a_native_timeline_line_separator():
    raw = b'0,Sound,a\r0,DamagePlayer,5\n'
    assert prepare_csv_bytes(raw)['raw'] == raw


def test_command_without_arguments_preserves_crlf():
    result=prepare_csv_bytes(b'1,DamagePlayer\r\n0,EndAttack\r\n')
    assert result['raw']==b'1,\r\n0,EndAttack\r\n'
    assert result['warnings'][0]['command']=='DamagePlayer'
