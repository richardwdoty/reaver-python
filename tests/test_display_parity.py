from copy import deepcopy
from dataclasses import fields
from pathlib import Path
import runpy
import numpy as np
import pytest
from scipy.io import loadmat
from reaver.gui.image_viewer import render_view,imadjust_uint8

ROOT=Path(__file__).resolve().parents[1]
CASES=list(runpy.run_path(str(ROOT/'tools/check_display_parity.py'))['cases']())
REF=loadmat(ROOT/'tests/fixtures/display_reference.mat',simplify_cells=True)['results']


@pytest.mark.parametrize('index',range(8))
def test_matlab_display_pixels_and_no_analysis_mutation(index):
    state,settings,channels=CASES[index]
    before=deepcopy(state)
    np.testing.assert_array_equal(render_view(state,'overlay',channels,settings=settings),REF[index]['overlay'])
    np.testing.assert_array_equal(render_view(state,'wire_frame'),REF[index]['wire'].astype(np.uint8)*255)
    np.testing.assert_array_equal(state.base_image.data,before.base_image.data)
    for f in fields(state.derived_layers):
        np.testing.assert_array_equal(getattr(state.derived_layers,f.name),getattr(before.derived_layers,f.name))


def test_flat_contrast_unchanged():
    image=np.full((20,20,3),75,np.uint8)
    np.testing.assert_array_equal(imadjust_uint8(image),image)


@pytest.mark.parametrize('index', range(8))
def test_cached_overlay_exact_through_edits_and_input_replacement(index):
    state, settings, channels = deepcopy(CASES[index])
    cache = {}
    for step in range(5):
        state.derived_layers.bw_2 = state.derived_layers.bw_2.copy()
        state.derived_layers.bw_2[:step+1, :step+2] ^= True
        if step == 2:
            state.derived_layers.wire = ~state.derived_layers.wire
        if step == 3:
            state.base_image.data = 255-state.base_image.data
        np.testing.assert_array_equal(
            render_view(state, 'overlay', channels, settings=settings, cache=cache),
            render_view(state, 'overlay', channels, settings=settings))
