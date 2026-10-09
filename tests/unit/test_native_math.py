import json
import math
import random
import shutil
import struct
import subprocess

import pytest

from nohit.engine.native_math import native_atan2


def test_original_random_beam_angle_floor():
    # Real engine replay: this blaster previously became 102 degrees in libm,
    # while original JavaScript produced 103; the false-safe route lost HP.
    angle=(180./math.pi)*native_atan2(377.-182.12598704295294,420.-464.990210868773)
    assert angle==103.


@pytest.mark.skipif(shutil.which('node') is None,reason='JavaScript oracle requires Node')
def test_binary64_against_v8_atan2():
    rng=random.Random(42)
    pairs=[(math.ldexp(rng.uniform(-1.,1.),rng.randrange(-1000,1000)),
            math.ldexp(rng.uniform(-1.,1.),rng.randrange(-1000,1000))) for _ in range(3000)]
    pairs += [(y,x) for y in (0.,-0.,1.,-1.,math.inf,-math.inf)
                   for x in (0.,-0.,1.,-1.,math.inf,-math.inf)]
    # JSON does not retain signed zero or infinities; transmit exact bytes.
    encode=lambda v:struct.pack('>d',v).hex()
    payload=[[encode(y),encode(x)] for y,x in pairs]
    script="""let s='';process.stdin.on('data',x=>s+=x);process.stdin.on('end',()=>{
      const rows=JSON.parse(s).map(([y,x])=>{const b=Buffer.alloc(8);
        b.writeDoubleBE(Math.atan2(Buffer.from(y,'hex').readDoubleBE(),Buffer.from(x,'hex').readDoubleBE()));
        return b.toString('hex');});process.stdout.write(JSON.stringify(rows));});"""
    result=subprocess.run(['node','-e',script],input=json.dumps(payload),text=True,capture_output=True,check=True)
    assert [encode(native_atan2(y,x)) for y,x in pairs]==json.loads(result.stdout)


def test_timeline_degree_conversion_preserves_native_integer_beam_angle(tmp_path):
    from nohit.engine import resumable_wave as world
    from nohit.engine.compact_wave import compile_wave
    path=tmp_path/'rounding.csv'
    path.write_text('0,SET,hx,445.00000000014495\n0,SET,hy,224.8333333332415\n'
        '0,COS,x,201\n0,SIN,y,201\n0,MUL,x,$x,200\n0,MUL,y,$y,200\n'
        '0,ADD,x,$x,$hx\n0,ADD,y,$y,$hy\n0,ANGLE,a,$x,$y,$hx,$hy\n'
        '0,GasterBlaster,2,0,0,$x,$y,$a,0.1,1\n0.5,EndAttack\n')
    state=world.initialize(path,dt_schedule=[1/60]*100,max_ticks=100)
    result=world._advance_owned_tick(state)
    assert result.state.vm.vars['a']==20.99999999999999
    assert result.state.data['active_blasters'][0].end_ang==20
    # Independent monolithic interpreter executes the same native expression order.
    wave=compile_wave(path,dt_schedule=[1/60]*100,max_ticks=100)
    blaster=next(args for _,cmd,args in wave.source_events if cmd=='gasterblaster')
    assert blaster[5]==20.99999999999999
