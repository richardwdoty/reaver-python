"""Compare Python metrics and segment arrays with a generated MATLAB reference."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
from scipy.io import loadmat
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from reaver.core.metrics import quantify_network,MeasurementError
from reaver.io.measurement_export import write_results_csv


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('reference',type=Path)
    a=p.parse_args()
    data=loadmat(a.reference,simplify_cells=True)
    report=[];rows=[]
    for case,ref in zip(data['cases'],data['results']):
        d=ref['input']['derivedPic']
        args=(np.asarray(d['BW_2'],bool),np.asarray(d['wire'],bool),
              np.asarray(d['branchpoints']).reshape(-1,2).astype(int)-1,
              np.asarray(d['endpoints']).reshape(-1,2).astype(int)-1,ref['input']['image_resolution'])
        error=ref.get('error')
        if isinstance(error,str) and error:
            try:quantify_network(*args)
            except MeasurementError:report.append(dict(name=case['name'],expected_matlab_error=error))
            else:raise AssertionError('MATLAB fails for this case; Python must report it')
            continue
        result=quantify_network(*args)
        segments=ref['segments'] if result.segments else []
        if len(result.segments)==1 and isinstance(segments,np.ndarray) and segments.dtype!=object:
            segments=[segments]
        assert len(result.segments)==len(segments)
        for x,y in zip(result.segments,segments):np.testing.assert_array_equal(x,np.asarray(y)-1)
        np.testing.assert_array_equal(result.radii,np.asarray(ref['radii']).reshape(-1))
        np.testing.assert_array_equal(result.endpoint_segments,np.asarray(ref['index']['end_seg_idx']).reshape(-1).astype(bool))
        np.testing.assert_allclose(result.tortuosity,np.asarray(ref['tortuosity']).reshape(-1),rtol=1e-12,atol=1e-12)
        differences={}
        for key,value in result.metrics.items():
            expected=ref['metrics'][key]
            np.testing.assert_allclose(value,expected,rtol=1e-12,atol=1e-12,err_msg=key)
            differences[key]=float(abs(value-expected)) if np.isfinite(value) else 0
        report.append(dict(name=case['name'],segments=len(segments),segment_coordinates='exact',
            radii='exact',endpoint_classification='exact',metric_absolute_differences=differences))
        rows.append(dict(image_name=case['name'],**result.metrics))
        print(case['name'], 'PASS',flush=True)
    write_results_csv(a.reference.parent/'python_results.csv',rows)
    (a.reference.parent/'comparison.json').write_text(json.dumps(dict(matlab_version=data['matlab_version'],
        tolerance=dict(rtol=1e-12,atol=1e-12),cases=report),indent=2))


if __name__=='__main__':main()
