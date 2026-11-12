from copy import deepcopy
from pathlib import Path
import runpy
import numpy as np
import pytest
from scipy.io import loadmat
from reaver.app.image_state import ReaverImageState, DerivedLayers
from reaver.app.params import SegmentationParams
from reaver.core.editing import paint_segment, undo_edit
from reaver.core.wire import update_wire

ROOT = Path(__file__).resolve().parents[1]
MAP = runpy.run_path(str(ROOT/'tools/check_matlab_parity.py'))['CONSTANTS']


@pytest.mark.parametrize('index', range(4))
def test_brush_and_update_matlab_parity(index):
    reference = loadmat(ROOT/'tests/fixtures/editing_reference.mat', simplify_cells=True)
    case, expected = reference['cases'][index], reference['results'][index]
    params = SegmentationParams(**{k: (float(case['constants'][v]) if k in
        ('thin_iterations', 'grey_to_bw_threshold', 'vessel_thickness_threshold') else int(case['constants'][v]))
        for k, v in MAP.items()})
    state = ReaverImageState('test', Path('test.tif'), image_segmented=True,
        derived_layers=DerivedLayers(bw_2=case['binary'].astype(bool)))
    for stroke, mask in zip(case['strokes'], expected['masks']):
        paint_segment(state, stroke[:2], stroke[2:4], int(stroke[4]), bool(stroke[5]))
        np.testing.assert_array_equal(state.derived_layers.bw_2, mask)
    update_wire(state, params)
    for py, mat in [('bw_2','BW_2'), ('wire','wire'), ('dilated_wire','dilated'), ('dilated_wire_2','dilated2')]:
        np.testing.assert_array_equal(getattr(state.derived_layers, py), expected['updated'][mat])
    for name in ('branchpoints', 'endpoints'):
        np.testing.assert_array_equal(getattr(state.derived_layers, name),
            np.asarray(expected['updated'][name]['coords']).reshape(-1,2)-1)
    assert not state.edit_backup_locked


def test_undo_restores_batch_before_and_after_update():
    state = ReaverImageState('test', Path('test.tif'), image_segmented=True,
        derived_layers=DerivedLayers(bw_2=np.zeros((96,128),bool), wire=np.zeros((96,128),bool)))
    original = deepcopy(state.derived_layers)
    for after_update in (False, True):
        paint_segment(state, (10,20), (100,20), 8, True)
        paint_segment(state, (50,10), (50,80), 8, True)
        assert state.undo_available and state.wire_update_pending
        if after_update:
            update_wire(state)
        assert undo_edit(state)
        np.testing.assert_array_equal(state.derived_layers.bw_2, original.bw_2)
        np.testing.assert_array_equal(state.derived_layers.wire, original.wire)
        assert not state.wire_update_pending and not state.undo_available
        assert not undo_edit(state)
    # After an accepted update, a new batch backs up that updated result.
    paint_segment(state, (10,20), (100,20), 8, True)
    update_wire(state)
    accepted = deepcopy(state.derived_layers)
    paint_segment(state, (50,10), (50,80), 8, True)
    update_wire(state)
    assert undo_edit(state)
    for field in ('bw_2', 'wire', 'branchpoints', 'endpoints'):
        np.testing.assert_array_equal(getattr(state.derived_layers, field), getattr(accepted, field))
