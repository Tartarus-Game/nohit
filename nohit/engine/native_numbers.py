"""Typed Construct 2 numeric coercions used by audited source commands."""
import math
import re


# ECMAScript WhiteSpace and LineTerminator characters, not Python's broader
# Unicode whitespace set. parseInt(..., 10) accepts only ASCII decimal digits.
_DECIMAL_PREFIX=re.compile(r'^[\u0009-\u000d\u0020\u00a0\u1680\u2000-\u200a'
    r'\u2028\u2029\u202f\u205f\u3000\ufeff]*([+-]?[0-9]+)')


def native_int(value):
    """C2 System.int: strings use parseInt(value,10), numbers use floor.

    Native expression return values are JavaScript numbers. Preserve negative
    zero and nonfinite numeric values; only an unparseable string becomes +0.
    In particular, '-1e3' is -1 while the numeric value -1e3 is -1000.
    """
    if isinstance(value,str):
        match=_DECIMAL_PREFIX.match(value)
        if match is None:return 0.
        number=float(match.group(1))
    else:
        number=float(value)
    if not math.isfinite(number) or number==0.:return number
    return float(math.floor(number))


_JS_WHITESPACE = ('\u0009\u000a\u000b\u000c\u000d\u0020\u00a0\u1680'
    '\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a'
    '\u2028\u2029\u202f\u205f\u3000\ufeff')
_FLOAT_PREFIX = re.compile(r'[+-]?(?:Infinity|(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)'
    r'(?:[eE][+-]?[0-9]+)?)')


def native_local_number(value):
    """System number-local SetValue: keep numbers; parseFloat other values.

    This is intentionally different from Timeline dictionary SET and int.
    Invalid strings become numeric NaN; fractions and negative zero survive.
    """
    if not isinstance(value, str):
        return float(value)
    match = _FLOAT_PREFIX.match(value.lstrip(_JS_WHITESPACE))
    return float(match.group(0)) if match is not None else math.nan


def native_parameter_in_range(value, lower, upper):
    """Function.CompareParam with numeric >= / <= guards, before int(P0).

    JS relational comparison ToNumbers a string against these numeric bounds.
    Unlike parseFloat, the whole string must be numeric. This narrow helper is
    only used by BoneStab's two original entry conditions.
    """
    if isinstance(value, str):
        value = value.strip(_JS_WHITESPACE)
        if not value:
            number = 0.
        elif _FLOAT_PREFIX.fullmatch(value) is not None:
            number = float(value)
        elif re.fullmatch(r'0[xX][0-9a-fA-F]+|0[bB][01]+|0[oO][0-7]+', value):
            try:
                number = float(int(value, 0))
            except OverflowError:
                number = math.inf
        else:
            number = math.nan
    else:
        number = float(value)
    return lower <= number <= upper


def native_for_count_indices(count):
    """Audited System.For(0, Count-1), after Count's typed int conversion.

    The native loop is inclusive and descends when the end is below zero.
    Repeat and SineBones have no positive-count guard. Nonfinite loops remain
    unsupported instead of silently generating no children.
    """
    if not math.isfinite(count):
        raise ValueError('unsupported_nonfinite_for_count')
    count = int(count)
    return range(count) if count > 0 else range(0, count - 2, -1)
