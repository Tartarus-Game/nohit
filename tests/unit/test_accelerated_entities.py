"""Optional AOT bodies must agree with the independent Python source."""
import importlib.util
from pathlib import Path
import sys
import struct

import numpy as np

from nohit.engine import compact_wave


def test_blaster_acceleration_preserves_original_fields_and_polygons():
    name='nohit.engine._original_compact_wave_for_test'
    path=Path(__file__).resolve().parents[2]/'nohit/engine/compact_wave.py'
    spec=importlib.util.spec_from_file_location(name,path)
    original=importlib.util.module_from_spec(spec);sys.modules[name]=original
    spec.loader.exec_module(original)
    try:
        rng=np.random.default_rng(6741)
        for case in range(40):
            args=(case%3,*rng.uniform(-500,1000,4),rng.uniform(-720,720),
                (case%7)*.05,(case%5)*.1)
            fast=compact_wave._StreamingGasterBlaster(*args)
            slow=original._ActiveGasterBlaster(*args)
            for tick in range(200):
                dt=(1/60,1/30,.016666666666045785)[tick%3]
                assert fast.step(dt)==slow.step(dt)
                assert fast.__dict__.keys()==slow.__dict__.keys()
                assert struct.pack('d'*len(vars(fast)),*vars(fast).values())==struct.pack('d'*len(vars(slow)),*vars(slow).values())
                a,b=fast.polygon(),slow.polygon()
                assert (a is None)==(b is None)
                if a is not None:assert np.asarray(a).tobytes()==np.asarray(b).tobytes()
    finally:
        del sys.modules[name]
