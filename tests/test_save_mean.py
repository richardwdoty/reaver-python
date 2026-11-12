from pathlib import Path
import numpy as np
from scipy.io import loadmat
from reaver.io.results import _matlab_single_mean


def test_saved_mean_matches_matlab_single_precision():
    data = loadmat(Path(__file__).parent/'fixtures/save_mean_reference.mat',simplify_cells=True)
    for case in data['cases']:
        np.testing.assert_array_equal(_matlab_single_mean(case['values']),case['expected'])
