"""Linear monolithic-source verification of an observation-dependent witness."""
import numpy as np

from .compact_wave import compile_wave
from .csv_completion import wave_terminal
from .parametric_environment import ParametricEnvironment
from .source_oracle import scalar_module


def _last_active(rows,polygons=False):
    if not rows.shape[1]:return np.zeros(len(rows),np.int64)
    # A long dense score can have millions of padded slots. Bound temporary
    # masks/indices rather than allocating an int64 copy of the whole score.
    result=np.empty(len(rows),np.int64);indices=np.arange(rows.shape[1])+1
    for start in range(0,len(rows),256):
        block=rows[start:start+256,:,0]
        present=np.isfinite(block) if polygons else ~np.isnan(block)
        result[start:start+256]=np.where(present,indices,0).max(axis=1)
    return result


def scalar_frame_collision(frame,state):
    """Array rectangle predicates; independent original scalar quad bodies."""
    source=scalar_module('cspace')
    if state[10]!=0.:return True
    x,y=state[:2]
    for plane,boxes in enumerate((frame.white,frame.blue)):
        if plane and state[2]==0. and state[3]==0.:continue
        if len(boxes)>=64:
            if np.any((x+2.>=boxes[:,0])&(x-2.<=boxes[:,2])&
                      (y+2.>=boxes[:,1])&(y-2.<=boxes[:,3])):return True
        else:
            for box in boxes.tolist():
                if source._rect_hit(box,x,y,2.):return True
    for poly in frame.polygons.tolist():
        if source.quad_intersects_box(poly,x,y,2.,2.):return True
    return False


def scalar_collision_checker(wave):
    """Original predicates on views with only trailing inert padding removed."""
    source=scalar_module('cspace')
    counts=tuple(_last_active(rows,poly) for rows,poly in
        ((wave.geometry_white,False),(wave.geometry_blue,False),(wave.geometry_polygons,True)))
    cells=np.empty((1,2,0,0),np.uint8)
    def check(tick,state):
        white=wave.geometry_white[tick:tick+1,:counts[0][tick]]
        blue=wave.geometry_blue[tick:tick+1,:counts[1][tick]]
        polygons=wave.geometry_polygons[tick:tick+1,:counts[2][tick]]
        return source.collision_query(white,blue,0,state,0.,(cells,polygons,0.,0.,1.))
    return check


def compile_observed_prefix(path,settings,expected,initial_target_history,*,_frame_observer=None,_suspension_observer=None,_collision_bounds=None):
    """Monolithic source prefix sampled from this proposed physical trace."""
    player=scalar_module('discrete_operator')
    initial_rows=None if initial_target_history is None else iter(initial_target_history)
    def observe(tick,line,teleport,context):
        if tick>=len(expected):raise ValueError('observation outside proposed trace')
        if tick==0 and initial_rows is not None:
            row=next(initial_rows,None)
            if row is None or tuple(row[:2])!=(0,line):raise ValueError('missing initial source observation')
            xy=tuple(row[2:])
            if teleport is not None and xy!=teleport:raise ValueError('initial observation contradicts source teleport')
            return xy
        if teleport is not None:return teleport
        if tick==0:return tuple(expected[0,:2])
        dt,bounds,platforms=context
        environment=np.zeros(22);environment[7]=dt;environment[14:18]=bounds
        return player.sample_position(expected[tick-1].tolist(),environment.tolist(),platforms)
    # All observations come from this word's proposed states and the original
    # source sampling phase. The replay below independently checks every state.
    wave=compile_wave(path,heart_samples=observe,allow_partial=True,
        include_combined_geometry=False,_frame_observer=_frame_observer,
        _suspension_observer=_suspension_observer,_collision_bounds=_collision_bounds,**settings)
    if initial_rows is not None and next(initial_rows,None) is not None:return None
    return wave


def certify_observed(path,initial,settings,actions,expected,initial_target_history):
    player=scalar_module('discrete_operator')
    wave=compile_observed_prefix(path,settings,expected,initial_target_history)
    if wave is None:return None
    if not wave.complete or wave.termination_reason not in ('endattack','eof_hazards_drained') or len(wave.env_schedule)!=len(actions)+1:return None
    check=scalar_collision_checker(wave);state=player.initial_state(initial,wave.env_schedule[0])
    for tick in range(len(expected)):
        if tick:player.step_mask_into(state,actions[tick-1],wave.env_schedule[tick],wave.platform_table[tick],state)
        if not np.isfinite(state).all() or state.tobytes()!=expected[tick].tobytes() or check(tick,state):return None
    template=ParametricEnvironment(path,backend='reference',**settings)
    binding=template.bind(wave.target_history)
    if not binding.complete or binding.history!=wave.target_history:return None
    # A second monolithic run binds the ordinary public identity. It executes
    # the source twice in total, rather than once per growing history prefix.
    for name in ('env_schedule','platform_table','geometry_white','geometry_blue','geometry_polygons'):
        if getattr(binding.wave,name).tobytes()!=getattr(wave,name).tobytes():return None
    return binding,binding.history,wave_terminal(binding.wave),None,None,False
