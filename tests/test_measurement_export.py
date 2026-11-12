import csv
from dataclasses import replace
from pathlib import Path
import numpy as np
import pytest
import tifffile
from scipy.io import loadmat,savemat
from skimage.morphology import dilation,disk
from reaver.app.params import SegmentationParams
from reaver.core.segmentation import initial_layers
from reaver.core.metrics import METRIC_LABELS,measure_state,MeasurementError
from reaver.io.images import load_image_state
from reaver.io.results import save_analysis,load_analysis
from reaver.io.measurement_export import COLUMNS,measurement_row,write_results_csv,export_saved_analyses

REFERENCE=loadmat(Path(__file__).parent/'fixtures/measurement_reference.mat',simplify_cells=True)


def make_state(folder,name='vessels',index=2):
    ref=REFERENCE['results'][index]['input']
    d=ref['derivedPic'];path=folder/(name+'.tif')
    tifffile.imwrite(path,d['BW_2'].astype(np.uint8)*255)
    s=load_image_state(path)
    s.params=SegmentationParams(image_resolution=float(ref['image_resolution']))
    s.input_channels=s.segmented_channels=(0,)
    s.image_segmented=s.dirty=True
    wire=d['wire'].astype(bool)
    s.derived_layers=replace(initial_layers(s.base_image.data,s.params),
        bw_2=d['BW_2'].astype(bool),wire=wire,
        branchpoints=np.asarray(d['branchpoints']).reshape(-1,2).astype(int)-1,
        endpoints=np.asarray(d['endpoints']).reshape(-1,2).astype(int)-1,
        dilated_wire=dilation(wire,disk(1)).astype(np.uint8),dilated_wire_2=dilation(wire,disk(2)).astype(np.uint8))
    return s


def test_matlab_csv_column_and_value_parity(tmp_path):
    rows=[]
    for index in range(2,10):
        s=make_state(tmp_path,str(index),index)
        save_analysis(s)
        row=measurement_row(s)
        row['image_name']=REFERENCE['cases'][index]['name']
        rows.append(row)
    path=write_results_csv(tmp_path/'results.csv',rows)
    with path.open(newline='',encoding='utf-8') as stream:
        reader=csv.DictReader(stream);assert tuple(reader.fieldnames)==COLUMNS
        actual=list(reader)
    with (Path(__file__).parent/'fixtures/measurement_reference.csv').open(newline='',encoding='utf-8-sig') as stream:
        reader=csv.DictReader(stream);assert tuple(reader.fieldnames)==COLUMNS
        expected=list(reader)
    assert len(actual)==len(expected)
    for a,b in zip(actual,expected):
        assert a['image_name']==b['image_name']
        for key in METRIC_LABELS:
            np.testing.assert_allclose(float(a[key]),float(b[key]) if b[key] else np.nan,rtol=1e-12,atol=1e-12)


def test_verified_batch_selection_native_and_legacy(tmp_path):
    native=make_state(tmp_path,'native');native.verified=True;save_analysis(native)
    unverified=make_state(tmp_path,'unverified');save_analysis(unverified)
    legacy=make_state(tmp_path,'legacy');save_analysis(legacy,tmp_path/'legacy.reaver.mat')
    data=loadmat(legacy.analysis_path,simplify_cells=True,mat_dtype=True)
    legacy_path=tmp_path/'legacy.mat'
    savemat(legacy_path,{k:v for k,v in data.items() if not k.startswith('_') and not k.startswith('reaver')})
    table=tmp_path/'User Verified Table.mat'
    savemat(table,{'userVerified':np.array([['legacy.tif',True],['unverified.tif',True]],dtype=object)})
    before=table.read_bytes()
    # Explicit native False overrides the old table; native and legacy True survive.
    items=[(native.analysis_path,native.path),(unverified.analysis_path,unverified.path),(legacy_path,legacy.path)]
    rows=export_saved_analyses(items,tmp_path/'results.csv')
    assert [r['image_name'] for r in rows]==[native.path.name,legacy.path.name]
    assert load_analysis(native.analysis_path).verified
    assert not load_analysis(unverified.analysis_path).verified
    assert table.read_bytes()==before


def test_stale_unsaved_and_no_branchpoint_exports_rejected(tmp_path):
    s=make_state(tmp_path)
    with pytest.raises(MeasurementError,match='Save'):measurement_row(s)
    save_analysis(s)
    s.wire_update_pending=True
    with pytest.raises(MeasurementError,match='Update Wire'):measurement_row(s)
    missing=make_state(tmp_path,'no_branches',1);missing.verified=True;save_analysis(missing)
    path=tmp_path/'results.csv';path.write_text('previous results')
    with pytest.raises(MeasurementError,match='no branchpoints'):
        export_saved_analyses([(missing.analysis_path,missing.path)],path)
    assert path.read_text()=='previous results'


def test_atomic_csv_failure_and_non_csv_guard(tmp_path,monkeypatch):
    s=make_state(tmp_path);save_analysis(s);row=measurement_row(s)
    output=tmp_path/'results.csv';output.write_text('previous')
    def fail(*args,**kwargs):raise OSError('disk error')
    monkeypatch.setattr('reaver.io.measurement_export.os.replace',fail)
    with pytest.raises(OSError):write_results_csv(output,[row])
    assert output.read_text()=='previous' and not list(tmp_path.glob('.*.tmp'))
    before=s.path.read_bytes()
    with pytest.raises(ValueError):write_results_csv(s.path,[row])
    assert s.path.read_bytes()==before


def test_resolution_scaling_and_no_input_mutation(tmp_path):
    s=make_state(tmp_path);a=measure_state(s)
    mask=s.derived_layers.bw_2.copy();wire=s.derived_layers.wire.copy()
    s.params.image_resolution*=2
    b=measure_state(s)
    for name in ('vessel_length_um','mean_segment_length_um','mean_segment_diam_um','max_diffusion_dist_um'):
        assert b.metrics[name]==pytest.approx(2*a.metrics[name])
    assert b.metrics['vessel_length_density_mmpmm2']==pytest.approx(a.metrics['vessel_length_density_mmpmm2']/2)
    assert b.metrics['mean_tortuosity']==a.metrics['mean_tortuosity']
    np.testing.assert_array_equal(s.derived_layers.bw_2,mask)
    np.testing.assert_array_equal(s.derived_layers.wire,wire)
