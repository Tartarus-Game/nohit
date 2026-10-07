"""Compose a finite control witness and its certified physical-tick EOF tail."""


def execution_schedule(result):
    actions=list(result['actions'])
    hold=result.get('control_ticks',4)
    if type(hold) is not int or hold not in (1,4):
        raise ValueError('invalid control domain')
    physics_hz=result.get('physics_hz',240)
    clock={key:result[key] for key in ('physics_hz','clock_protocol','dt_schedule_count',
           'dt_schedule_sha256','dt_sequence') if key in result}
    tail=result.get('terminal_tail')
    if tail is None:
        return dict(actions=actions,control_ticks=hold,
                    control_hz=None if physics_hz is None else physics_hz/hold,
                    trajectory=result.get('trajectory',[]),has_terminal_tail=False,**clock)
    if result.get('status')!='candidate_found' or tail.get('status')!='proven':
        raise ValueError('cannot execute an unproved EOF tail')
    boundary=tail.get('start_tick')
    if type(boundary) is not int or boundary<0 or len(actions)!=(boundary+hold-1)//hold:
        raise ValueError('EOF boundary does not match the finite witness')
    bridge=tail.get('actions')
    if tail.get('control_ticks')!=1 or not isinstance(bridge,list):
        raise ValueError('EOF bridge must contain physical-tick inputs')
    if any(type(mask) is not int or not 0<=mask<32 for mask in actions+bridge):
        raise ValueError('invalid physical input mask')
    carry=(-boundary)%hold
    if tail.get('carry_ticks')!=carry or len(bridge)<carry:
        raise ValueError('EOF carry does not complete the control block')
    if carry and bridge[:carry]!=[actions[-1]]*carry:
        raise ValueError('EOF bridge changes the unfinished control block')
    if len(tail.get('states',[]))!=len(bridge)+1 or len(tail.get('dt_sequence',[]))!=len(bridge):
        raise ValueError('EOF bridge evidence length mismatch')
    # The compiler ended INSIDE the final hold. Its bridge already contains
    # the remaining ticks: truncation here prevents executing those twice.
    physical=[mask for mask in actions for _ in range(hold)][:boundary]+bridge
    if 'dt_sequence' in clock:
        clock['dt_sequence']=clock['dt_sequence'][:boundary+1]+tail['dt_sequence']
    return dict(actions=physical,control_ticks=1,control_hz=physics_hz,
                trajectory=[],has_terminal_tail=True,terminal_start_tick=boundary,**clock)
