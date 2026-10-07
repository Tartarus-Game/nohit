"""Conservative, opt-in future-state keys; route evidence is never rewritten.

This initial certificate accepts only straight-line, fixed-delay programs.
Target values may affect objects erased by BlackScreen(1), but may not affect
persistent arena/dynamics state. Variables must all be dead after the clear.
Unsupported programs retain exact history identity, including RealHELL until
its CFG and native argument-capture semantics receive an integrated proof.
"""
from dataclasses import dataclass
import csv
import math
from pathlib import Path
import re


_NAME=re.compile(r'[A-Za-z_][A-Za-z_0-9]*\Z')
_ASSIGN={'set','add','sub','mul','div','mod','floor','sin','cos','deg','rad','angle','rnd'}
_SPAWN={'bonev','boneh','bonevrepeat','bonehrepeat','platform','platformrepeat',
        'bonestab','sinebones','gasterblaster'}
_PERSISTENT={'heartteleport','heartmode','combatzoneresize','combatzoneresizeinstant',
             'combatzonespeed','heartmaxfallspeed','sansslamdamage','sansslam'}
_ALLOWED=_ASSIGN|_SPAWN|_PERSISTENT|{'getheartpos','blackscreen','endattack',''}


@dataclass(frozen=True,slots=True)
class ClearCertificate:
    event_index: int
    source_line: int


def certify_clears(path):
    """Return proved reset events, or no certificates for unsupported syntax.

The rejection path is deliberately conservative: no target-dependent delays,
branches, text pauses, indirect variable names, or unclassified commands.
"""
    rows=list(csv.reader(Path(path).read_text(encoding='utf-8-sig').splitlines()))
    program=[]
    for line,row in enumerate(rows,1):
        if not any(cell.strip() for cell in row):continue
        row=[cell.strip() for cell in row]
        cmd=row[1].lower() if len(row)>1 else ''
        if cmd not in _ALLOWED:return ()
        try:
            delay=float(row[0] or 0)
            if not math.isfinite(delay) or delay<0:return ()
        except (ValueError,IndexError):return ()
        args=row[2:]
        # The optional resize callback can invoke another source function.
        # Its effects are not covered by this restricted operator proof, even
        # when the callback name happens to look like a numeric literal.
        if cmd in ('combatzoneresize','combatzoneresizeinstant') and any(args[4:]):return ()
        count=2 if cmd=='getheartpos' else 1 if cmd in _ASSIGN else 0
        writes=args[:count]
        if len(writes)!=count or any(not _NAME.fullmatch(name) for name in writes):return ()
        reads=set()
        for arg in args[count:]:
            if arg.startswith('$') and _NAME.fullmatch(arg[1:]):reads.add(arg[1:])
            else:
                try:
                    if not math.isfinite(float(arg or 0)):return ()
                except ValueError:return ()
        clear=False
        if cmd=='blackscreen':
            try:clear=int(float(args[0] or 0))==1
            except (ValueError,IndexError):return ()
        program.append((line,cmd,set(writes),reads,clear))

    # A read on any subsequent instruction makes a variable live until its
    # next unconditional write. The accepted CFG is one straight-line path.
    live=set();live_after=[None]*len(program)
    for index in range(len(program)-1,-1,-1):
        _,_,writes,reads,_=program[index]
        live_after[index]=frozenset(live)
        live=(live-writes)|reads

    tainted=set();persistent_independent=True;certificates=[]
    for index,(line,cmd,writes,reads,clear) in enumerate(program):
        depends=bool(tainted&reads)
        if cmd=='getheartpos':tainted|=writes
        elif cmd in _ASSIGN:
            tainted-=writes
            if depends:tainted|=writes
        elif cmd in _PERSISTENT and depends:
            persistent_independent=False
        # Target-dependent BlackScreen was already rejected as nonliteral.
        if clear and persistent_independent and not live_after[index]:
            certificates.append(ClearCertificate(index,line))
        if cmd=='endattack':break
    return tuple(certificates)


class FutureHistoryKey:
    """Proved future identity, separate from a binding's full evidence history.

The template base identity retains source, seed, initial environment, clock,
termination policy, and dt budget. A fixed straight-line program implies the
same pc, elapsed delay, RNG state, arena state, and event phase at a given tick
for all target histories admitted by the certificate. Complete suffix target
samples then determine identical future operators from the erased-object cut.
"""
    def __init__(self,template):
        self.certificates=certify_clears(template.path)
        self.base_identity=template.bind().identity

    def __call__(self,binding,tick):
        selected=None
        events=binding.wave.source_events
        for certificate in self.certificates:
            index=certificate.event_index
            if index>=len(events):continue
            at,cmd,args=events[index]
            if cmd!='blackscreen':continue
            # End-of-tick state only. Keep the entire clear tick's target
            # reads, including observations AFTER the clear in the same tick.
            if tick>at:
                selected=(certificate,at)
        if selected is None:return ('exact_history',binding.identity)
        certificate,at=selected
        suffix=tuple(row for row in binding.history if row[0]>=at)
        # Pack exact floating bits through the original serialized identity;
        # Python float equality would incorrectly equate signed zeros here.
        suffix_bytes=binding.identity[-32*len(suffix):] if suffix else b''
        return ('proved_clear',self.base_identity,certificate.source_line,at,suffix_bytes)
