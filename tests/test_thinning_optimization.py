"""Compare sparse execution with the original full-image lookup sequence."""
import numpy as np
import pytest
from reaver.core.morphology import bwmorph_thin_matlab, bwlookup_matlab
from reaver.core.morph_luts import LUT_THIN1, LUT_THIN2


def test_thinning_tables_only_delete():
    background_centers = (np.arange(512) & 16) == 0
    for lut in (LUT_THIN1, LUT_THIN2):
        assert lut.dtype == np.bool_
        assert not lut[background_centers].any()


@pytest.mark.parametrize('density', [0, .02, .2, .5, 1])
@pytest.mark.parametrize('shape', [(1,1), (1,37), (29,1), (48,61)])
@pytest.mark.parametrize('iterations', [0, 1, 2, np.inf])
def test_sparse_thinning_matches_dense(density, shape, iterations):
    image = (np.random.default_rng(246).random(shape) < density)[:, ::-1]
    original = image.copy()
    expected = image
    i = 0
    while i < iterations:
        new = bwlookup_matlab(bwlookup_matlab(expected, LUT_THIN1), LUT_THIN2)
        i += 1
        if np.array_equal(new, expected):
            expected = new
            break
        expected = new
    # Include a noncontiguous input, as used by image crops.
    np.testing.assert_array_equal(bwmorph_thin_matlab(image, iterations), expected)
    np.testing.assert_array_equal(image, original)
