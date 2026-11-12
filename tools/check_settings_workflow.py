"""Non-default GUI settings and MATLAB parity on an isolated real-image copy."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import numpy as np
from scipy.io import savemat, loadmat
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
os.environ.setdefault('QT_QPA_PLATFORM','windows' if sys.platform=='win32' else 'offscreen')
from PySide6.QtWidgets import QApplication
from reaver.gui.main_window import ReaverMainWindow
from reaver.gui.segmentation_settings import validated_settings
from reaver.io.results import load_analysis
from check_matlab_parity import CONSTANTS, compare, morphology_input


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',required=True,type=Path)
    parser.add_argument('--matlab',required=True)
    parser.add_argument('--matlab-root',required=True,type=Path)
    args=parser.parse_args()
    digest=hashlib.sha256(args.image.read_bytes()).hexdigest()
    out=ROOT/'data/tmp'/('settings_workflow_'+time.strftime('%Y%m%d_%H%M%S'))
    out.mkdir(parents=True)
    shutil.copyfile(args.image,out/args.image.name)
    app=QApplication.instance() or QApplication([])
    w=ReaverMainWindow();w.show();w.open_directory(out)
    w.file_list.setCurrentItem(w.file_list.item(0))
    w.threshold_edit.setText('0.0805');w.threshold_text_changed()
    w.app_state.params=validated_settings(w.app_state.params,dict(averaging_filter_size=33,
        min_connected_component_area=200,wire_dilation_threshold=2,vessel_thickness_threshold=1.5))
    w.proposed_settings_changed()
    w.segment_button.click()
    deadline=time.monotonic()+180
    while w.worker is not None and time.monotonic()<deadline:
        app.processEvents();time.sleep(.01)
    assert w.worker is None
    state=w.app_state.active_image
    assert state.image_segmented and state.params.grey_to_bw_threshold==.081
    assert w.save_current_analysis()
    reopened=load_analysis(state.analysis_path)
    assert reopened.params==state.params
    for name in ('bw_2','wire','branchpoints','endpoints'):
        np.testing.assert_array_equal(getattr(state.derived_layers,name),getattr(reopened.derived_layers,name))
    w.open_directory(out);w.file_list.setCurrentItem(w.file_list.item(0))
    assert w.threshold_edit.text()=='0.081' and w.app_state.params==state.params
    app.processEvents();w.grab().save(str(out/'settings_preview.png'));w.close()
    image=state.base_image.data
    constants={v:float(getattr(state.params,k)) for k,v in CONSTANTS.items()}
    constants.update(survive=np.arange(4,9),born=np.arange(4,9))
    case=dict(image=image,constants=constants,channels=np.array([True,False,False]))
    savemat(out/'inputs.mat',dict(cases=np.array([case],dtype=object),morph_input=morphology_input()))
    quote=lambda p:str(p).replace('\\','/').replace("'","''")
    command=f"addpath('{quote(ROOT/'tests/matlab')}'); generate_reference('{quote(out/'inputs.mat')}','{quote(out/'reference.mat')}','{quote(args.matlab_root)}')"
    subprocess.run([args.matlab,'-wait','-nosplash','-nodesktop','-sd',str(out),'-batch',command],check=True)
    reference=loadmat(out/'reference.mat',simplify_cells=True)['results']
    failures=compare(image,state.params,state.segmented_channels,reference)
    assert not failures,failures
    assert hashlib.sha256(args.image.read_bytes()).hexdigest()==digest
    (out/'report.json').write_text(json.dumps(dict(image=str(args.image),original_sha256=digest,
        originals_unchanged=True,gui_roundtrip='exact',matlab_failures=failures),indent=2),encoding='utf-8')
    print('GUI save/reopen and MATLAB non-default parity passed:',out,flush=True)


if __name__=='__main__':main()
