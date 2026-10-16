"""Native Timeline call slots and a source-bound absent-function proof.

The complete inventory has 116 matching XML/exported-data handler SIDs and
names, all literal. The callback proof is restricted to "0"; top-level CSV
calls have a separate exact allowlist. Both require this original source.
"""
from functools import lru_cache
import hashlib
from pathlib import Path


NO_ACTION_FUNCTION_AUDIT = 'jcw87-zero-function-absent-full-inventory-20261007'
NO_ACTION_SOURCE_AUDIT = 'jcw87-absent-function-registry-20261017'
AUDITED_NO_ACTION_COMMANDS = frozenset((
    'score', 'mus_zz_megalovania', 'setmaxhp', 'damafeeplayer', 'notooth'))
EVENT_SHEET_MANIFEST_SHA256 = '9d418baa1e26df68c7dd9d888722187ff27b04511b26c4617888ca161a9dd5ac'
NATIVE_SOURCE_SHA256 = (
    ('data.js', '9f70e7179fe4260002321a75e5170e96583439bb39988b92ed93da42a0a402c7'),
    ('c2runtime.js', '664b5d93dbd5159976d490663ac64c49c8eb7dc68c9aac92fba940b6fa2a3de9'),
)


def call_arguments(loaded_args):
    """Array.At(2..10): preserve present values; missing cells are numeric zero.

    Loaded storage remains unchanged, including resolved cells beyond P8.
    This is applied after TLLoadLine's single variable substitution.
    """
    present = tuple(loaded_args[:9])
    return present + (0.,) * (9 - len(present))


@lru_cache(maxsize=1)
def _original_registry_matches():
    return _current_registry_matches()


def _current_registry_matches():
    root = Path(__file__).resolve().parents[2] / 'c2-sans-fight'
    try:
        return all(hashlib.sha256((root / name).read_bytes()).hexdigest() == expected
                   for name, expected in NATIVE_SOURCE_SHA256)
    except OSError:
        return False


def audited_no_action_function(name):
    return name.lower() == '0' and _original_registry_matches()


def audited_no_action_command(name):
    """Only these literal Timeline calls lack handlers in this native export.

    Do not reuse this permission for arbitrary unknown commands or callbacks.
    Function dispatch lowercases the whole name before its exact-name lookup.
    Recheck current bytes: a dashboard may outlive changes to the native export.
    """
    return name.lower() in AUDITED_NO_ACTION_COMMANDS and _current_registry_matches()
