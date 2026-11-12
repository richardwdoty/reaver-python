from pathlib import Path
import runpy
import numpy as np
import pytest
from scipy.io import loadmat
from reaver.app.image_state import ReaverImageState, DerivedLayers
from reaver.app.params import SegmentationParams
from reaver.core.wire import compute_wire, apply_binary_edit, update_wire

ROOT=Path(__file__).resolve().parents[1]
REF=loadmat(ROOT/'tests/fixtures/wire_reference.mat',simplify_cells=True)
MAP=runpy.run_path(str(ROOT/'tools/check_matlab_parity.py'))['CONSTANTS']

@pytest.mark.parametrize('index',range(8))
def test_wire_matlab_parity(index):
    c=REF['cases'][index];ref=REF['results'][index]
    params=SegmentationParams(**{k:(float(c['constants'][v]) if k in ('thin_iterations','grey_to_bw_threshold','vessel_thickness_threshold') else int(c['constants'][v])) for k,v in MAP.items()})
    binary=c['binary'].astype(bool);original=binary.copy()
    result=compute_wire(binary,params)
    for py,mat in [('bw_2','BW_2'),('wire','wire'),('dilated_wire','dilated'),('dilated_wire_2','dilated2')]:
        np.testing.assert_array_equal(getattr(result,py),ref[mat])
    for field in ('branchpoints','endpoints'):
        np.testing.assert_array_equal(getattr(result,field),np.asarray(ref[field]['coords']).reshape(-1,2)-1)
    np.testing.assert_array_equal(binary,original)
    if params.wire_dilation_threshold==0:
        np.testing.assert_array_equal(result.bw_2,binary)
        np.testing.assert_array_equal(compute_wire(result.bw_2,params).wire,result.wire)

def test_edit_unlocks_only_one_successful_update():
    mask=np.zeros((96,128),bool)
    state=ReaverImageState('test',Path('test.tif'),image_segmented=True,derived_layers=DerivedLayers(bw_2=mask))
    with pytest.raises(ValueError):update_wire(state)
    assert not apply_binary_edit(state,mask)
    edited=mask.copy();edited[20:40,:]=True
    assert apply_binary_edit(state,edited)
    edited[:]=False  # edit input was copied
    assert state.wire_update_pending
    with pytest.raises(ValueError):update_wire(state,SegmentationParams(thin_iterations=-1))
    assert state.wire_update_pending
    update_wire(state)
    assert not state.wire_update_pending
    with pytest.raises(ValueError):update_wire(state)
    second=state.derived_layers.bw_2.copy();second[25:30,30:40]=False
    assert apply_binary_edit(state,second)
    update_wire(state)

def test_nonzero_dilation_can_remove_binary_pixels():
    mask=np.ones((96,128),bool)
    result=compute_wire(mask,SegmentationParams(wire_dilation_threshold=1))
    assert result.bw_2.sum()<mask.sum()
