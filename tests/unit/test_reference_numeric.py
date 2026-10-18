"""Typed reference loops retain the independent NumPy equations byte for byte."""
import numpy as np
import pytest

from nohit.engine import compact_wave as source


@pytest.mark.parametrize('count',[1,64,500])
@pytest.mark.parametrize('nonfinite',[False,True])
def test_typed_reference_bones_match_unchanged_numpy_rows_and_geometry(monkeypatch,count,nonfinite):
    accelerated=source._reference_numeric
    if accelerated is None:
        pytest.skip('optional typed numeric module is not installed')
    rng=np.random.default_rng(7309)
    rows=np.zeros((count,8));rows[:,:2]=rng.uniform(-700,700,(count,2))
    rows[:,2:4]=rng.uniform(-100,100,(count,2));rows[:,4:6]=rng.uniform(-300,300,(count,2))
    rows[:,6]=rng.integers(0,3,count);rows[:,7]=rng.integers(0,4,count)
    rows[0]=(-0.,-0.,-0.,0.,-0.,0.,1.,2.)
    if nonfinite and count>1:
        rows[1,:4]=np.nan,np.inf,20.,np.nan
        rows[-1,4]=np.nan
    fast=source._ReferenceBoneBatch();slow=source._ReferenceBoneBatch()
    for batch in (fast,slow):
        batch.rows=np.array(rows,order='F');batch.count=count
    for tick in range(90):
        dt=(1/60,1/30,.016666666666045785)[tick%3]
        monkeypatch.setattr(source,'_reference_numeric',accelerated)
        fast.advance(dt)
        bounds=None if tick%2 else (-2.,-2.,2.,2.)
        actual=fast.geometry(bounds)
        monkeypatch.setattr(source,'_reference_numeric',None)
        slow.advance(dt)
        expected=slow.geometry(bounds)
        assert fast.count==slow.count
        assert fast.rows[:fast.count].tobytes()==slow.rows[:slow.count].tobytes()
        assert all(a.tobytes()==b.tobytes() for a,b in zip(actual,expected))
