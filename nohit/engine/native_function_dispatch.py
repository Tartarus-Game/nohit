"""Native Timeline call slots and a source-bound absent-function proof.

The complete inventory has 116 matching XML/exported-data handler SIDs and
names, all literal. None registers "0". Keep the proof restricted to this name
and this original source version; it is not permission to ignore callbacks.
"""
from functools import lru_cache
import hashlib
from pathlib import Path


NO_ACTION_FUNCTION_AUDIT = 'jcw87-zero-function-absent-full-inventory-20261007'
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
    root = Path(__file__).resolve().parents[2] / 'c2-sans-fight'
    try:
        return all(hashlib.sha256((root / name).read_bytes()).hexdigest() == expected
                   for name, expected in NATIVE_SOURCE_SHA256)
    except OSError:
        return False


def audited_no_action_function(name):
    return name.lower() == '0' and _original_registry_matches()


# Timeline run-state functions. Timeline.xml implements ``TLResume`` as exactly
# ``Running = 1`` and ``TLPause`` as exactly ``Running = 0``, and this model
# already executes both as CSV commands. A ``CombatZoneResize`` may name either
# one as its completion callback, so both are callbacks whose effect the model
# actually applies -- they are executable, not unproven. Anything else still
# falls through to the unproven-callback record.
MODELED_TIMELINE_CALLBACKS = ('tlresume', 'tlpause')


def modeled_timeline_callback(name):
    return str(name).strip().lower() in MODELED_TIMELINE_CALLBACKS


def executable_resize_callback(name):
    """A resize completion callback this model can execute to completion."""
    return modeled_timeline_callback(name) or audited_no_action_function(name)
