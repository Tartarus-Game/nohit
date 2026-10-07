"""C2 System.int contracts independently checked against the native V8 branch."""
import math

import pytest

from nohit.engine.native_numbers import native_int


@pytest.mark.parametrize('value,expected',[
    (-10.4,-11.),('-10.4',-10.),('-1e3',-1.),(-1e3,-1000.),
    ('+12.9abc',12.),('0x10',0.),('nonnumeric',0.),('',0.),
    ('  \t\n-12.5',-12.),('\ufeff-12.5',-12.),('\u00a0+12',12.),
    ('\u0085-12',0.),('\u001c-12',0.),('\u180e-12',0.),
    ('１２',0.),('+-12',0.),('-.5',0.),('-123tail',-123.),
    (10.9,10.),('-99999999999999999999999999',-1e26),
])
def test_native_int_preserves_string_vs_numeric_rules(value,expected):
    assert native_int(value)==expected


@pytest.mark.parametrize('value',[-0.,'-0','-0.4','-0e3'])
def test_native_int_preserves_negative_zero(value):
    result=native_int(value)
    assert result==0. and math.copysign(1.,result)==-1.


@pytest.mark.parametrize('value',[float('inf'),-float('inf'),float('nan')])
def test_numeric_nonfinite_is_not_silently_replaced_by_zero(value):
    result=native_int(value)
    assert math.isnan(result) if math.isnan(value) else result==value
