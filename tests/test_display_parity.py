from copy import deepcopy
from dataclasses import fields
from pathlib import Path
import runpy
import numpy as np
import pytest
from scipy.io import loadmat
from reaver.gui.image_viewer import render_view,imadjust_uint8,update_brush_view
from reaver.core.editing import paint_segment

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


@pytest.mark.parametrize('index', range(8))
@pytest.mark.parametrize('mode', ['overlay', 'segmented'])
def test_regional_strokes_match_full_render(index, mode):
    state, settings, channels = deepcopy(CASES[index])
    state.image_segmented = True
    cache = {}
    output = render_view(state, mode, channels, settings=settings, cache=cache)
    h, w = state.derived_layers.bw_2.shape
    rng = np.random.default_rng(58)
    # Corners, crossing the image, outside endpoints, fractional rounding,
    # repeated no-op strokes, and randomized paths and all brush sizes.
    strokes = [((0,0),(0,0),1,True), ((w-1,h-1),(w-1,h-1),16,False),
               ((-4,-3),(w+2,h+5),4,True), ((-.5,.5),(4.5,3.5),2,False)]
    strokes += [(tuple(rng.integers((-20,-20),(w+20,h+20))),
                 tuple(rng.integers((-20,-20),(w+20,h+20))),
                 int(rng.integers(1,17)), bool(rng.integers(2))) for _ in range(60)]
    for start, end, size, add in strokes:
        for _ in range(2):
            changed = paint_segment(state, start, end, size, add)
            if changed:
                update_brush_view(state, mode, output, start, end, size, channels, settings, cache)
            np.testing.assert_array_equal(output, render_view(state, mode, channels, settings=settings))


@pytest.mark.parametrize('shape', [(1,1), (1,9), (9,1), (3,4)])
def test_regional_small_grayscale_images(shape):
    state, settings, channels = deepcopy(CASES[0])
    state.base_image.data = np.arange(np.prod(shape), dtype=np.uint8).reshape(shape)
    state.derived_layers.bw_2 = np.zeros(shape, bool)
    state.derived_layers.wire = np.zeros(shape, bool)
    state.image_segmented = True
    cache = {}
    output = render_view(state, 'overlay', settings=settings, cache=cache)
    for add in (True, False):
        paint_segment(state, (0,0), (0,0), 1, add)
        update_brush_view(state, 'overlay', output, (0,0), (0,0), 1, settings=settings, cache=cache)
        np.testing.assert_array_equal(output, render_view(state, 'overlay', settings=settings))
