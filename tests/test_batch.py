from dataclasses import replace
import numpy as np
import tifffile
from test_measurement_export import make_state
from reaver.app.params import SegmentationParams
from reaver.core.batch import process_batch
from reaver.core.segmentation import segment_image
from reaver.io.images import load_image_state
from reaver.io.results import save_analysis, load_analysis
from reaver.io.measurement_export import update_directory_results, read_results_csv


def test_batch_default_skips_saved_and_matches_single(tmp_path):
    existing=make_state(tmp_path,'old');existing.verified=True;path=save_analysis(existing)
    before=path.read_bytes()
    raw=tmp_path/'new.tif';tifffile.imwrite(raw,existing.base_image.data.squeeze())
    params=replace(existing.params,grey_to_bw_threshold=.081,averaging_filter_size=17)
    result=process_batch([(existing.path,None),(raw,None)],params,(0,))
    assert result['skipped']==[str(existing.path)] and result['saved']==[str(raw)]
    assert path.read_bytes()==before
    loaded=load_analysis(raw.with_name(raw.name+'.reaver'))
    expected=segment_image(load_image_state(raw).base_image.data,params,(0,))
    np.testing.assert_array_equal(loaded.derived_layers.bw_2,expected.bw_2)
    np.testing.assert_array_equal(loaded.derived_layers.wire,expected.wire)
    assert loaded.params==params and not loaded.verified


def test_batch_replacement_archives_and_invalidates_csv(tmp_path):
    state=make_state(tmp_path);state.verified=True;path=save_analysis(state)
    before=path.read_bytes();source=state.path.read_bytes();csv=update_directory_results(state)
    report=process_batch([(state.path,path)],state.params,(0,))
    assert report['saved']==[str(state.path)] and not report['failed']
    assert next((tmp_path/'.reaver-history').iterdir()).read_bytes()==before
    assert state.path.read_bytes()==source and not load_analysis(path).verified
    assert read_results_csv(csv)==[]


def test_batch_failure_continues_and_cancel_retains_completed(tmp_path):
    state=make_state(tmp_path)
    bad=tmp_path/'bad.tif';bad.write_bytes(b'broken')
    report=process_batch([(bad,None),(state.path,None)],state.params,(0,))
    assert len(report['failed'])==1 and report['saved']==[str(state.path)]
    calls=[]
    def stop():
        calls.append(1);return len(calls)>1
    other=make_state(tmp_path,'other')
    third=make_state(tmp_path,'third')
    report=process_batch([(other.path,None),(third.path,None)],state.params,(0,),cancelled=stop)
    assert report['cancelled'] and report['saved']==[str(other.path)]
    assert not third.path.with_name(third.path.name+'.reaver').exists()


def test_legacy_mat_preserved_and_failed_save_retains_native(tmp_path,monkeypatch):
    state=make_state(tmp_path)
    legacy=save_analysis(state,tmp_path/'vessels.mat');before=legacy.read_bytes()
    report=process_batch([(state.path,legacy)],state.params,(0,))
    assert not report['failed'] and legacy.read_bytes()==before
    native=state.path.with_name(state.path.name+'.reaver');saved=native.read_bytes()
    def fail(*args,**kwargs):raise OSError('disk failure')
    monkeypatch.setattr('reaver.core.batch.save_analysis',fail)
    report=process_batch([(state.path,native)],state.params,(0,))
    assert len(report['failed'])==1 and not report['saved']
    assert native.read_bytes()==saved
