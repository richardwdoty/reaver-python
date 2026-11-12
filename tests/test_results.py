from copy import deepcopy
from dataclasses import fields, replace
from pathlib import Path
import numpy as np
import pytest
import tifffile
from scipy.io import loadmat, savemat
from scipy.sparse import csc_matrix
from reaver.app.params import SegmentationParams
from reaver.core.segmentation import segment_image
from reaver.core.editing import paint_segment, undo_edit
from reaver.core.wire import update_wire
from reaver.io.images import load_image_state
from reaver.io.results import save_analysis, load_analysis, default_analysis_path, find_analysis


@pytest.fixture
def segmented(tmp_path):
    image = np.zeros((64,80,3),np.uint8)
    image[12:40,:,0] = 255
    image[:,25:50,1] = 255
    path = tmp_path/'vessels.tif'
    tifffile.imwrite(path,image,photometric='rgb')
    state = load_image_state(path)
    state.params = SegmentationParams(averaging_filter_size=16,min_connected_component_area=10)
    state.segmented_channels = state.input_channels = (0,1)
    state.derived_layers = segment_image(state.base_image.data,state.params,state.segmented_channels)
    state.image_segmented = state.dirty = True
    return state


def equal_layers(a,b):
    for field in fields(a):
        np.testing.assert_array_equal(getattr(a,field.name),getattr(b,field.name),err_msg=field.name)


def test_roundtrip_edited_layers_settings_and_matlab_fields(segmented):
    s = segmented
    original_image = s.path.read_bytes()
    paint_segment(s,(3,45),(70,45),6,True)
    with pytest.raises(ValueError,match='Update Wire'):
        save_analysis(s)
    s.params.wire_dilation_threshold = 3
    update_wire(s,s.params)
    expected = deepcopy(s.derived_layers)
    # A proposed input change must not mislabel the saved segmentation.
    s.input_channels = (2,)
    path = save_analysis(s)
    assert path == default_analysis_path(s.path) and find_analysis(s.path) == path
    assert not s.dirty
    reopened = load_analysis(path)
    equal_layers(expected,reopened.derived_layers)
    assert reopened.params == s.params
    assert reopened.segmented_channels == reopened.input_channels == (0,1)
    assert not reopened.dirty and not reopened.undo_available and not reopened.wire_update_pending
    assert not undo_edit(reopened)
    paint_segment(reopened,(10,10),(50,10),8,False)
    assert undo_edit(reopened)
    equal_layers(reopened.derived_layers,expected)
    mat_path = save_analysis(s, s.path.with_name('compatible.mat'))
    saved = loadmat(mat_path,simplify_cells=True,mat_dtype=True)
    np.testing.assert_array_equal(saved['derivedPic']['branchpoints'],(expected.branchpoints+1).squeeze())
    assert saved['metrics']['vesselArea'] == expected.bw_2.sum()
    assert s.path.read_bytes() == original_image


def test_legacy_sparse_wire_defaults_and_original_preservation(segmented,monkeypatch):
    native = save_analysis(segmented, segmented.path.with_name('compatible.mat'))
    data = loadmat(native,simplify_cells=True,mat_dtype=True)
    data = {k:v for k,v in data.items() if not k.startswith('_') and not k.startswith('reaver')}
    data['derivedPic']['wire'] = csc_matrix(data['derivedPic']['wire'])
    # Old files used one-based numeric input channels and lacked newer options.
    data['constants']['selectedColors'] = np.array([1,2])
    del data['constants']['vesselThicknessThreshold']
    del data['constants']['wireDilationThreshold']
    del data['image_resolution']
    legacy = segmented.path.with_suffix('.mat')
    savemat(legacy,data)
    before = legacy.read_bytes()
    def forbidden(*args,**kwargs):
        raise AssertionError('Saved wire must never be recomputed')
    monkeypatch.setattr('reaver.core.wire.compute_wire',forbidden)
    reopened = load_analysis(legacy)
    for field in ('bw_2','wire','branchpoints','endpoints'):
        np.testing.assert_array_equal(getattr(reopened.derived_layers,field),getattr(segmented.derived_layers,field))
    assert reopened.params.image_resolution == 1 and reopened.params.vessel_thickness_threshold == 3
    assert reopened.save_path is None
    with pytest.raises(ValueError,match='original MATLAB'):
        save_analysis(reopened,legacy)
    assert legacy.read_bytes() == before


@pytest.mark.parametrize('failure',['write','replace'])
def test_failed_save_preserves_previous_file_and_dirty_state(segmented,monkeypatch,failure):
    path = save_analysis(segmented)
    previous = path.read_bytes()
    segmented.dirty = True
    def fail(*args,**kwargs):
        raise OSError('simulated disk failure')
    monkeypatch.setattr('reaver.io.results.'+('_write_native' if failure=='write' else 'os.replace'),fail)
    with pytest.raises(OSError):
        save_analysis(segmented)
    assert segmented.dirty and path.read_bytes() == previous
    assert not list(path.parent.glob('.*.tmp'))


def test_moved_files_and_changed_source(segmented,tmp_path):
    path = save_analysis(segmented)
    moved = tmp_path/'moved'
    moved.mkdir()
    (moved/segmented.path.name).write_bytes(segmented.path.read_bytes())
    (moved/path.name).write_bytes(path.read_bytes())
    reopened = load_analysis(moved/path.name)
    assert reopened.path == moved/segmented.path.name
    changed = segmented.base_image.data.copy()
    changed[0,0,0] ^= 255
    tifffile.imwrite(moved/segmented.path.name,changed,photometric='rgb')
    with pytest.raises(ValueError,match='differs'):
        load_analysis(moved/path.name)


@pytest.mark.parametrize('damage',['version','dimensions','wire','points','parameter'])
def test_invalid_analysis_rejected(segmented,tmp_path,damage):
    path = save_analysis(segmented, tmp_path/'compatible.mat')
    data = loadmat(path,simplify_cells=True,mat_dtype=True)
    if damage == 'version': data['reaverPython']['formatVersion'] = 99
    if damage == 'dimensions': data['imageSize'] = [2,2]
    if damage == 'wire': data['derivedPic']['wire'] = np.full((64,80),2)
    if damage == 'points': data['derivedPic']['endpoints'] = [[-1,2]]
    if damage == 'parameter': data['constants']['averagingFilterSize'] = -5
    bad = tmp_path/'bad.mat'
    savemat(bad,{k:v for k,v in data.items() if not k.startswith('_')})
    with pytest.raises(ValueError): load_analysis(bad)


def test_grayscale_singleton_roundtrip(tmp_path):
    for shape in ((1,1),(1,7),(8,1),(20,25)):
        path = tmp_path/('gray_'+str(shape)+'.tif')
        tifffile.imwrite(path,np.zeros(shape,np.uint16))
        s = load_image_state(path)
        s.params = SegmentationParams()
        s.derived_layers = segment_image(s.base_image.data,s.params)
        s.image_segmented = True
        s.segmented_channels = (0,)
        reopened = load_analysis(save_analysis(s))
        equal_layers(s.derived_layers,reopened.derived_layers)
