"""Native GUI measurement/export checks using copies of real saved analyses."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
os.environ.setdefault('QT_QPA_PLATFORM','windows' if sys.platform=='win32' else 'offscreen')
from PySide6.QtWidgets import QApplication,QFileDialog,QMessageBox
from reaver.gui.main_window import ReaverMainWindow
from reaver.io.results import load_analysis,save_analysis,default_analysis_path


def wait(w,app):
    deadline=time.monotonic()+180
    while w.worker is not None and time.monotonic()<deadline:
        app.processEvents();time.sleep(.01)
    assert w.worker is None


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--analysis',action='append',required=True,type=Path)
    a=p.parse_args()
    out=ROOT/'data/tmp/measurement_workflow';out.mkdir(parents=True,exist_ok=True)
    app=QApplication.instance() or QApplication([])
    errors=[]
    QMessageBox.critical=lambda *args:errors.append(args[-1])
    hashes={};report=[]
    for index,path in enumerate(a.analysis):
        s=load_analysis(path)
        for original in (path,s.path):hashes[str(original)]=hashlib.sha256(original.read_bytes()).hexdigest()
        folder=out/str(index);folder.mkdir(exist_ok=True)
        image=folder/s.path.name;shutil.copyfile(s.path,image)
        target=default_analysis_path(image)
        s.verified=False;save_analysis(s,target)
        w=ReaverMainWindow();w.show();w.open_directory(folder);w.load_selected_image(w.file_list.item(0))
        w.measure_action.trigger();wait(w,app)
        state=w.app_state.active_image
        assert len(state.measurements)==12 and not errors
        assert not state.dirty
        w.verified_checkbox.setChecked(True)
        assert load_analysis(target).verified
        output=folder/(folder.name+'.csv')
        QFileDialog.getSaveFileName=lambda *args,**kwargs:(str(output),'CSV')
        w.export_directory_action.trigger();wait(w,app)
        assert not errors
        with output.open(newline='') as stream:rows=list(csv.DictReader(stream))
        assert len(rows)==1
        for key,value in state.measurements.items():
            np.testing.assert_allclose(float(rows[0][key]),value,rtol=1e-12,atol=1e-12)
        if index==0:
            app.processEvents();w.grab().save(str(out/'measurement_preview.png'))
        report.append(dict(analysis=str(path),measurement_display='passed',verification_saved=True,
            directory_export='passed',csv=str(output),measurements=state.measurements))
        w.close();w.deleteLater()
        print(path.name,'GUI measure/verify/export PASS',flush=True)
    assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest for path,digest in hashes.items())
    (out/'report.json').write_text(json.dumps(dict(cases=report,originals_unchanged=True,source_sha256=hashes),indent=2))


if __name__=='__main__':main()
