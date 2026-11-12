import numpy as np
import pytest
import tifffile
from test_measurement_export import make_state
from reaver.io.results import save_analysis
from reaver.io.image_export import export_saved_masks,export_displayed_image,write_new_tiff


def test_saved_mask_exact_binary_native_and_mat(tmp_path):
    a=make_state(tmp_path,'a');save_analysis(a)
    b=make_state(tmp_path,'b');save_analysis(b,tmp_path/'b.mat')
    expected=a.derived_layers.bw_2.copy()
    a.derived_layers.bw_2[:]=False
    before={p:p.read_bytes() for p in (a.path,b.path,a.analysis_path,b.analysis_path)}
    report=export_saved_masks([(a.analysis_path,a.path),(b.analysis_path,b.path)],tmp_path)
    assert not report['failed'] and len(report['saved'])==2
    for path in report['saved']:
        np.testing.assert_array_equal(tifffile.imread(path),expected)
        with tifffile.TiffFile(path) as tif:assert tif.pages[0].bitspersample==1
    again=export_saved_masks([(a.analysis_path,a.path)],tmp_path)
    assert again['saved'][0]!=report['saved'][0]
    assert all(p.read_bytes()==data for p,data in before.items())


@pytest.mark.parametrize('shape',[(17,23),(17,23,3)])
def test_display_pixels_exact_and_no_overwrite(tmp_path,shape):
    pixels=np.random.default_rng(3).integers(0,256,shape,dtype=np.uint8)
    source=tmp_path/'original.tif';source.write_bytes(b'original')
    first=export_displayed_image(source,pixels)
    second=export_displayed_image(source,pixels)
    assert first!=second and source.read_bytes()==b'original'
    np.testing.assert_array_equal(tifffile.imread(first),pixels)
    with pytest.raises(FileExistsError):write_new_tiff(first,pixels)
    assert not list(tmp_path.glob('*.tmp'))


def test_failed_export_preserves_existing(tmp_path,monkeypatch):
    state=make_state(tmp_path);save_analysis(state)
    def fail(*args):raise OSError('disk unavailable')
    monkeypatch.setattr('reaver.io.image_export.os.link',fail)
    report=export_saved_masks([(state.analysis_path,state.path)],tmp_path)
    assert len(report['failed'])==1 and not report['saved']
    assert not list((tmp_path/'bw').iterdir())
