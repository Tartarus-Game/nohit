"""V8/fdlibm atan2 for Timeline angles that subsequently undergo floor.

Python's platform libm may differ by one ULP, changing an integer beam angle.
Adapted from Chromium 138 third_party/fdlibm/ieee754.cc, atan and atan2:
https://chromium.googlesource.com/chromium/src/+/refs/tags/138.0.7204.174/third_party/fdlibm/ieee754.cc

Copyright (C) 1993 by Sun Microsystems, Inc. All rights reserved.
Developed at SunSoft, a Sun Microsystems, Inc. business.
Permission to use, copy, modify, and distribute this software is freely
granted, provided that this notice is preserved.
The original source was modified significantly by Google Inc.
Copyright 2016 the V8 project authors. All rights reserved.
Copyright 2020 The Chromium Authors.
"""
import math
import struct

_HI=(4.63647609000806093515e-1,7.85398163397448278999e-1,
     9.82793723247329054082e-1,1.57079632679489655800)
_LO=(2.26987774529616870924e-17,3.06161699786838301793e-17,
     1.39033110312309984516e-17,6.12323399573676603587e-17)
_A=(3.33333333333329318027e-1,-1.99999999998764832476e-1,
    1.42857142725034663711e-1,-1.11111104054623557880e-1,
    9.09088713343650656196e-2,-7.69187620504482999495e-2,
    6.66107313738753120669e-2,-5.83357013379057348645e-2,
    4.97687799461593236017e-2,-3.65315727442169155270e-2,
    1.62858201153657823623e-2)


def _high(x):
    return struct.unpack('>Q',struct.pack('>d',x))[0]>>32


def _atan(x):
    hx=_high(x);ix=hx&0x7fffffff
    if ix>=0x44100000:
        if math.isnan(x):return x+x
        return math.copysign(_HI[3]+_LO[3],x)
    if ix<0x3fdc0000:
        if ix<0x3e400000:return x
        index=-1
    else:
        x=abs(x)
        if ix<0x3ff30000:
            if ix<0x3fe60000:index=0;x=(2.*x-1.)/(2.+x)
            else:index=1;x=(x-1.)/(x+1.)
        elif ix<0x40038000:index=2;x=(x-1.5)/(1.+1.5*x)
        else:index=3;x=-1./x
    z=x*x;w=z*z;a=_A
    s1=z*(a[0]+w*(a[2]+w*(a[4]+w*(a[6]+w*(a[8]+w*a[10])))))
    s2=w*(a[1]+w*(a[3]+w*(a[5]+w*(a[7]+w*a[9]))))
    if index<0:return x-x*(s1+s2)
    z=_HI[index]-((x*(s1+s2)-_LO[index])-x)
    return -z if hx>>31 else z


def native_atan2(y,x):
    """V8's signed atan2, preserving binary64 expression order and signed zero."""
    if math.isnan(x) or math.isnan(y):return x+y
    if x==1.:return _atan(y)
    hx=_high(x);hy=_high(y);ix=hx&0x7fffffff;iy=hy&0x7fffffff
    m=(hy>>31)|((hx>>30)&2);pi=math.pi;pi_lo=1.2246467991473531772e-16
    if y==0.:return y if m<2 else math.copysign(pi,y)
    if x==0.:return math.copysign(pi/2.,y)
    if math.isinf(x):
        if math.isinf(y):return math.copysign(pi/4. if m<2 else 3.*(pi/4.),y)
        return math.copysign(0. if m<2 else pi,y)
    if math.isinf(y):return math.copysign(pi/2.,y)
    k=(iy-ix)>>20
    if k>60:z=pi/2.+.5*pi_lo;m&=1
    elif hx>>31 and k< -60:z=0.
    else:z=_atan(abs(y/x))
    if m==0:return z
    if m==1:return -z
    if m==2:return pi-(z-pi_lo)
    return (z-pi_lo)-pi
