import json
import zipfile
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
from test_measurement_export import make_state
from reaver.core.editing import paint_segment, undo_edit
from reaver.io.results import (save_analysis, load_analysis, find_analysis,
    analysis_verified, remove_saved_analysis, deletion_marker)
from reaver.io.measurement_export import (update_directory_results, read_results_csv,
    directory_results_path, export_saved_analyses)


def test_compact_roundtrip_and_mat_migration(tmp_path, monkeypatch):
    state = make_state(tmp_path)
    state.verified = True
    old = save_analysis(state, tmp_path/'vessels.tif.reaver.mat')
    original = old.read_bytes()
    migrated = load_analysis(old)
    assert migrated.save_path is None
    native = save_analysis(migrated)
    assert native.suffix == '.reaver' and find_analysis(state.path) == native
    assert old.read_bytes() == original
    with zipfile.ZipFile(native) as archive:
        assert set(archive.namelist()) == {'manifest.json','BW_2.npy','wire.npy','branchpoints.npy','endpoints.npy'}
        manifest = json.loads(archive.read('manifest.json'))
        assert 'metrics' not in manifest and 'reaverLayers' not in manifest
    def forbidden(*args, **kwargs):
        raise AssertionError('Never recompute segmentation or saved wire')
    monkeypatch.setattr('reaver.core.wire.compute_wire', forbidden)
    monkeypatch.setattr('reaver.core.segmentation.segment_image', forbidden)
    loaded = load_analysis(native)
    assert loaded.verified and analysis_verified(native, state.path)
    assert loaded.params == state.params
    for name in ('bw_2','wire','branchpoints','endpoints'):
        np.testing.assert_array_equal(getattr(loaded.derived_layers,name),getattr(state.derived_layers,name))


@pytest.mark.parametrize('damage', ['version','channels','verification','missing_wire'])
def test_damaged_native_rejected(tmp_path, damage):
    state = make_state(tmp_path)
    path = save_analysis(state)
    with zipfile.ZipFile(path) as archive:
        members = {n: archive.read(n) for n in archive.namelist()}
    manifest = json.loads(members['manifest.json'])
    if damage == 'version': manifest['version'] = 100
    if damage == 'channels': manifest['constants']['selectedColors'] = [2,0,0]
    if damage == 'verification': manifest['reaverPython']['userVerified'] = 'false'
    if damage == 'missing_wire': del members['wire.npy']
    members['manifest.json'] = json.dumps(manifest).encode()
    broken = tmp_path/'bad.reaver'
    with zipfile.ZipFile(broken,'w') as archive:
        for name, data in members.items(): archive.writestr(name,data)
    with pytest.raises(ValueError): load_analysis(broken)


def test_verification_cleared_on_edit_and_undo(tmp_path):
    state = make_state(tmp_path); state.verified = True
    state.undo_layers = deepcopy(state.derived_layers)
    state.edit_backup_locked = True
    assert not paint_segment(state,(-100,-100),(-100,-100),1,False)
    assert state.verified
    assert paint_segment(state,(30,20),(40,20),4,False)
    assert not state.verified
    assert undo_edit(state) and not state.verified


def test_remove_preserves_legacy_and_source_and_allows_new_save(tmp_path):
    state = make_state(tmp_path)
    legacy = save_analysis(state,tmp_path/'vessels.tif.reaver.mat')
    original = legacy.read_bytes(); pixels = state.path.read_bytes()
    state = load_analysis(legacy)
    native = save_analysis(state); saved = native.read_bytes()
    archives = remove_saved_analysis(state)
    assert not native.exists() and find_analysis(state.path) is None
    assert len(archives) == 1 and archives[0].read_bytes() == saved
    assert legacy.read_bytes() == original and state.path.read_bytes() == pixels
    assert deletion_marker(state.path).exists()
    assert load_analysis(legacy).image_segmented
    save_analysis(state)
    assert find_analysis(state.path) == native


def test_remove_failure_restores_discovery(tmp_path, monkeypatch):
    state = make_state(tmp_path); path = save_analysis(state)
    def fail(*args): raise OSError('locked')
    monkeypatch.setattr(Path,'rename',fail)
    with pytest.raises(OSError): remove_saved_analysis(state)
    assert path.exists() and find_analysis(state.path) == path
    assert not deletion_marker(state.path).exists()


def test_shared_csv_upsert_and_verified_rebuild(tmp_path):
    a=make_state(tmp_path,'a'); b=make_state(tmp_path,'b')
    a.verified=True
    save_analysis(a); save_analysis(b)
    path=update_directory_results(a)
    assert path == directory_results_path(tmp_path)
    update_directory_results(b); update_directory_results(a)
    assert [r['image_name'] for r in read_results_csv(path)] == ['a.tif','b.tif']
    export_saved_analyses([(a.analysis_path,a.path),(b.analysis_path,b.path)],path)
    assert [r['image_name'] for r in read_results_csv(path)] == ['a.tif']
    a.verified=False;save_analysis(a)
    export_saved_analyses([(a.analysis_path,a.path),(b.analysis_path,b.path)],path)
    assert read_results_csv(path) == []
    assert len(list(tmp_path.glob('*.csv'))) == 1


def test_shared_csv_preserves_unrelated_file(tmp_path):
    state=make_state(tmp_path);save_analysis(state)
    path=directory_results_path(tmp_path);path.write_text('unrelated,data\n1,2\n')
    before=path.read_bytes()
    with pytest.raises(ValueError): update_directory_results(state)
    assert path.read_bytes() == before
