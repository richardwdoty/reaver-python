"""Independent MATLAB R2024a reference outputs; MATLAB is not needed to run these."""
from pathlib import Path
import runpy

import numpy as np
import pytest
from scipy.io import loadmat

ROOT = Path(__file__).resolve().parents[1]
helper = runpy.run_path(str(ROOT / 'tools/check_matlab_parity.py'))
REFERENCE = loadmat(ROOT / 'tests/fixtures/matlab_reference.mat', simplify_cells=True)
CASES = list(helper['synthetic_cases']())


@pytest.mark.parametrize('index', range(len(CASES)), ids=[c[0] for c in CASES])
def test_segmentation_matches_matlab(index):
    _, image, params, channels = CASES[index]
    original = image.copy()
    assert helper['compare'](image, params, channels, REFERENCE['results'][index]) == {}
    np.testing.assert_array_equal(image, original)


@pytest.mark.parametrize('op', list(REFERENCE['morphology']))
def test_morphology_matches_matlab(op):
    morph = helper['morph']
    image = helper['morphology_input']()
    if op == 'branchpoints':
        result = morph.bwmorph_branchpoints_matlab(image)
    elif op == 'endpoints':
        result = morph.bwlookup_matlab(image, morph.LUT_ENDPOINTS)
    else:
        suffix = '_matlab' if op in ('thin', 'spur', 'clean') else ''
        result = getattr(morph, 'bwmorph_' + op + suffix)(image, iterations=1)
    np.testing.assert_array_equal(result, REFERENCE['morphology'][op])
