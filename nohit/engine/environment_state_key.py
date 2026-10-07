"""Injective typed serialization for conservative future-environment equality.

These are structural bytes, not a probabilistic digest. Dictionary lookup may
hash them, but Python still compares the complete bytes on a hash collision.
No historical evidence is encoded in this future-state representation.
"""
import struct
import numpy as np


REQUIRED_STATE_FIELDS=frozenset({
    'next_tick','pc','loaded_line','time_acc','running','vars','rng_state','heart_pos',
    'cz','cz_size','tgt_cz','cz_speed','heart_mode','gravity_dir','max_fall_speed',
    'slam_damage','active_bones','active_platforms','active_stabs','active_blasters',
    'ended','termination_reason','eof_tick','dt_nominal','unproven_callbacks','end_resize','phase',
})


def _length(n):
    return struct.pack('<Q',n)


def encode_typed(value):
    """An injective encoding over the interpreter's supported value domain."""
    kind=type(value)
    if value is None:return b'N'
    if kind is bool:return b'B'+bytes((int(value),))
    if kind is int:
        data=str(value).encode('ascii')
        return b'I'+_length(len(data))+data
    if kind is float:return b'F'+struct.pack('<d',value)
    if kind is str:
        data=value.encode('utf-8',errors='surrogatepass')
        return b'S'+_length(len(data))+data
    if kind is bytes:return b'Y'+_length(len(value))+value
    if kind in (tuple,list):
        return (b'T' if kind is tuple else b'L')+_length(len(value))+b''.join(encode_typed(v) for v in value)
    if kind is dict:
        if not all(type(key) is str for key in value):
            raise TypeError('environment dictionaries require exact string property keys')
        return b'D'+_length(len(value))+b''.join(encode_typed(key)+encode_typed(value[key]) for key in sorted(value))
    if isinstance(value,np.generic) and value.dtype.kind in 'biuf':
        # Preserve NumPy dtype as well as bits; do not silently identify an
        # overflowing fixed-width scalar with an arbitrary Python integer.
        return b'A'+encode_typed(value.dtype.str)+encode_typed(value.tobytes())
    raise TypeError('unsupported exact environment state value: '+kind.__name__)


def encode_environment_state(snapshot):
    if type(snapshot) is not dict:
        raise TypeError('environment snapshot must be a dictionary')
    missing=REQUIRED_STATE_FIELDS-snapshot.keys()
    if missing:
        raise ValueError('environment snapshot missing fields: '+', '.join(sorted(missing)))
    if snapshot['phase']!='post_world_tick':
        raise ValueError('only a committed post-world tick has a future state key')
    return b'NOHIT-ENV-STATE\x01'+encode_typed(snapshot)
