"""Native GUI save/reopen and MATLAB interchange checks on local image copies."""
import argparse
from copy import deepcopy
from dataclasses import fields
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import numpy as np
from scipy.io import savemat
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
os.environ.setdefault('QT_QPA_PLATFORM','windows' if sys.platform=='win32' else 'offscreen')
from PySide6.QtWidgets import QApplication, QMessageBox
from reaver.gui.main_window import ReaverMainWindow
from reaver.io.results import load_analysis, save_analysis


def wait(w,app):
    deadline = time.monotonic()+120
    while w.worker is not None and time.monotonic()<deadline:
        app.processEvents()
        time.sleep(.01)
    assert w.worker is None


def equal(a,b):
    for f in fields(a):
        np.testing.assert_array_equal(getattr(a,f.name),getattr(b,f.name),err_msg=f.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matlab',required=True)
    parser.add_argument('--image',action='append',type=Path,required=True)
    parser.add_argument('--legacy',action='append',type=Path,default=[])
    args = parser.parse_args()
    output = ROOT/'data/tmp/analysis_roundtrip'
    output.mkdir(parents=True,exist_ok=True)
    digest = lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    originals = {str(p):digest(p) for p in args.image+args.legacy}
    app = QApplication.instance() or QApplication([])
    report,expected,cases = [],[],[]
    for i,path in enumerate(args.image):
        folder = output/str(i)
        folder.mkdir(exist_ok=True)
        source = folder/path.name
        shutil.copyfile(path,source)
        w = ReaverMainWindow()
        w.show()
        w.open_directory(folder)
        w.load_selected_image(w.file_list.item(0))
        w.segment_button.click()
        wait(w,app)
        state = w.app_state.active_image
        h,width = state.derived_layers.bw_2.shape
        w.brush_size_spinbox.setValue(8)
        w.paint_stroke((width//2-30,h//2),(width//2+30,h//2),True)
        w.brush_size_spinbox.setValue(4)
        w.paint_stroke((width//2,h//2-30),(width//2,h//2+30),False)
        w.app_state.params.wire_dilation_threshold = 0 if i%2 == 0 else 3
        w.update_wire_action.trigger()
        wait(w,app)
        before = deepcopy(state.derived_layers)
        assert w.save_current_analysis()
        saved = state.analysis_path
        assert not state.dirty
        w.close()
        w.deleteLater()
        fresh = ReaverMainWindow()
        fresh.show()
        assert fresh.open_analysis(saved)
        equal(before,fresh.app_state.active_image.derived_layers)
        assert not fresh.undo_action.isEnabled() and not fresh.update_wire_action.isEnabled()
        fresh.display_mode_combo.setCurrentIndex(fresh.display_mode_combo.findData('overlay'))
        fresh.paint_stroke((20,20),(40,40),True)
        fresh.undo_action.trigger()
        equal(before,fresh.app_state.active_image.derived_layers)
        assert fresh.save_current_analysis()
        if i==0:
            app.processEvents()
            fresh.grab().save(str(output/'save_reopen_preview.png'))
        fresh.close()
        fresh.deleteLater()
        compatible = folder/('matlab_compatible_'+str(time.time_ns())+'.mat')
        save_analysis(load_analysis(saved),compatible)
        expected.append(before)
        cases.append(dict(saved=str(compatible),source=str(source),matlab_output=str(folder/'matlab_resaved.mat'),
            binary=before.bw_2,wire=before.wire,branchpoints=before.branchpoints+1,endpoints=before.endpoints+1))
        report.append(dict(image=str(path),gui_roundtrip='exact',dilation_radius=state.params.wire_dilation_threshold))
        print(path.name+': GUI save/reopen EXACT',flush=True)
    savemat(output/'checks.mat',dict(cases=np.array(cases,dtype=object)))
    quote = lambda p:str(p).replace('\\','/').replace("'","''")
    script = """s=load('INPUT');
for k=1:numel(s.cases)
 c=s.cases{k};a=load(c.saved);
 assert(islogical(a.derivedPic.BW_2));assert(islogical(a.derivedPic.wire));
 assert(isequal(a.derivedPic.BW_2,c.binary));assert(isequal(a.derivedPic.wire,c.wire));
 assert(isequal(a.derivedPic.branchpoints,c.branchpoints));assert(isequal(a.derivedPic.endpoints,c.endpoints));
 assert(a.metrics.vesselArea==sum(a.derivedPic.BW_2(:)));
 assert(a.metrics.vesselLength==sum(a.derivedPic.wire(:)));
 distanceImage=bwdist(~a.derivedPic.BW_2);
 distanceValues=distanceImage.*a.derivedPic.wire*2;
 assert(isequaln(a.metrics.meanVesselDiam,mean(distanceValues(distanceValues>0))));
 assert(a.metrics.numBranchPoints==max(size(a.derivedPic.branchpoints)));
 a=rmfield(a,{'reaverPython','reaverLayers'});
 a.derivedPic.wire=sparse(a.derivedPic.wire);
 save(c.matlab_output,'-struct','a','-v7');
end
disp('MATLAB read, metric check, and sparse re-save passed');
""".replace('INPUT',quote(output/'checks.mat'))
    (output/'verify.m').write_text(script)
    subprocess.run([args.matlab,'-wait','-nosplash','-nodesktop','-sd',str(output),'-batch',"run('"+quote(output/'verify.m')+"')"],check=True)
    for case,before,row in zip(cases,expected,report):
        reopened = load_analysis(case['matlab_output'],case['source'])
        equal(before,reopened.derived_layers)
        row['matlab_roundtrip'] = 'exact; MATLAB independently checked masks, points, and save metrics'
    for i,path in enumerate(args.legacy):
        state = load_analysis(path)
        target = output/('legacy_'+str(i)+'_'+str(time.time_ns())+'.reaver.mat')
        save_analysis(state,target)
        reopened = load_analysis(target)
        equal(state.derived_layers,reopened.derived_layers)
        report.append(dict(legacy=str(path),import_and_resave='exact'))
        print(path.name+': legacy import/resave EXACT',flush=True)
    assert originals == {str(p):digest(p) for p in args.image+args.legacy}
    (output/'report.json').write_text(json.dumps(dict(cases=report,originals_unchanged=True,source_sha256=originals),indent=2))


if __name__=='__main__':
    main()
