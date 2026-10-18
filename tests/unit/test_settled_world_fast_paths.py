"""Settled worlds retain exact endpoint bits and empty entity inventories."""
import numpy as np
from nohit.engine.compact_wave import _resize_combat_zone
from nohit.engine.resumable_wave import _BlasterArrays,_PlatformArrays


def test_settled_arena_still_recomputes_inconsistent_endpoints_and_signed_zero():
    bounds=[-0.,0.,999.,999.];size=[-0.,10.]
    _resize_combat_zone(bounds,size,[0.,0.,0.,10.],480.,1/60)
    assert np.asarray(bounds).tobytes()==np.asarray([-0.,0.,-0.,10.]).tobytes()
    assert np.asarray(size).tobytes()==np.asarray([-0.,10.]).tobytes()
    bounds=[100.,100.,540.,420.];size=[440.,320.]
    before=np.asarray(bounds+size).tobytes()
    for _ in range(120):_resize_combat_zone(bounds,size,[100.,100.,540.,420.],480.,1/60)
    assert np.asarray(bounds+size).tobytes()==before


def test_empty_owned_entities_do_not_touch_inactive_storage():
    platforms=_PlatformArrays();platforms.rows.fill(np.nan)
    blasters=_BlasterArrays();blasters.rows.fill(np.nan)
    before=[a.rows.tobytes() for a in (platforms,blasters)]
    for dt in (0.,1/60,1/30):
        platforms.advance(dt);blasters.advance(dt)
        assert len(platforms)==len(blasters)==0
        assert platforms.geometry([]).shape==(0,9)
        assert blasters.polygons().shape==(0,8)
    assert before==[a.rows.tobytes() for a in (platforms,blasters)]


def test_empty_blaster_inventory_discards_geometry_from_previous_tick():
    blasters=_BlasterArrays()
    blasters.boxes=np.ones((2,8),np.float64)
    blasters.advance(1/60)
    assert blasters.polygons().shape==(0,8)
