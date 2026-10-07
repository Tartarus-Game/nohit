"""Audited number-local assignment and pre-int parameter guard semantics."""
from pathlib import Path
import math
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import pytest

from nohit.engine.native_numbers import (native_local_number,
    native_parameter_in_range, native_for_count_indices)


@pytest.mark.parametrize('value,expected',[
    ('-12.9',-12.9),(-12.9,-12.9),('1e1',10.),('1e+',1.),
    ('12.5suffix',12.5),('0x10',0.),('\ufeff\u200912.5',12.5),
    ('Infinity!',math.inf),('-Infinity',-math.inf),
])
def test_numeric_local_uses_parsefloat_prefix(value,expected):
    assert native_local_number(value)==expected


@pytest.mark.parametrize('value',['','x','\u008512','\u001c12','１２'])
def test_invalid_numeric_local_is_nan(value):
    assert math.isnan(native_local_number(value))


@pytest.mark.parametrize('value',['-0.0','-0suffix',-0.])
def test_numeric_local_preserves_negative_zero(value):
    assert math.copysign(1.,native_local_number(value))==-1.


@pytest.mark.parametrize('value,expected',[
    ('-0.1',False),(-0.1,False),('3.9',False),('1e1',False),
    ('1junk',False),('1e0',True),('0x2',True),('',True),
    ('Infinity',False),('NaN',False),(math.nan,False),('2',True),
])
def test_bonestab_parameter_comparison_precedes_int(value,expected):
    assert native_parameter_in_range(value,0.,3.) is expected


@pytest.mark.parametrize('value',[math.nan,math.inf,-math.inf])
def test_nonfinite_for_count_is_explicitly_unsupported(value):
    with pytest.raises(ValueError,match='unsupported_nonfinite_for_count'):
        native_for_count_indices(value)
