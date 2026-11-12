from pathlib import Path
import numpy as np
import pytest
from scipy.io import loadmat
from reaver.core.metrics import quantify_network,trace_boundary,MeasurementError

REFERENCE = loadmat(Path(__file__).parent/'fixtures/measurement_reference.mat',simplify_cells=True)


@pytest.mark.parametrize('index',range(10))
def test_matlab_network_measurements(index):
    ref = REFERENCE['results'][index]
    d = ref['input']['derivedPic']
    wire = np.asarray(d['wire'],bool)
    np.testing.assert_array_equal(trace_boundary(wire),np.asarray(ref['first_trace']).reshape(-1,2)-1)
    args = (np.asarray(d['BW_2'],bool),wire,np.asarray(d['branchpoints']).reshape(-1,2).astype(int)-1,
            np.asarray(d['endpoints']).reshape(-1,2).astype(int)-1,ref['input']['image_resolution'])
    if isinstance(ref['error'],str) and ref['error']:
        with pytest.raises(MeasurementError):quantify_network(*args)
        return
    actual = quantify_network(*args)
    expected_segments = ref['segments']
    if not actual.segments: expected_segments = []
    assert len(actual.segments)==len(expected_segments)
    for a,b in zip(actual.segments,expected_segments):
        np.testing.assert_array_equal(a,np.asarray(b)-1)
    np.testing.assert_array_equal(actual.radii,np.asarray(ref['radii']).reshape(-1))
    np.testing.assert_allclose(actual.tortuosity,np.asarray(ref['tortuosity']).reshape(-1),rtol=1e-13,atol=1e-13)
    for name,value in actual.metrics.items():
        np.testing.assert_allclose(value,ref['metrics'][name],rtol=1e-12,atol=1e-12,err_msg=name)
