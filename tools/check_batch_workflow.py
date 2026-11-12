"""Batch GUI verification using isolated real-image copies and original-file hashes."""
import argparse
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
from PySide6.QtWidgets import QApplication,QMessageBox
from reaver.gui.main_window import ReaverMainWindow
from reaver.gui.batch_processing import BatchDialog
from reaver.core.segmentation import segment_image
from reaver.io.results import load_analysis,save_analysis,default_analysis_path


def wait(w,app):
    deadline=time.monotonic()+300
    while w.worker is not None and time.monotonic()<deadline:
        app.processEvents();time.sleep(.01)
    app.processEvents()
    assert w.worker is None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis',action='append',required=True,type=Path)
    args=parser.parse_args()
    out=ROOT/'data/tmp'/('batch_workflow_'+time.strftime('%Y%m%d_%H%M%S'));out.mkdir(parents=True)
    hashes={};images=[]
    for i,path in enumerate(args.analysis):
        state=load_analysis(path)
        for original in (path,state.path):hashes[str(original)]=hashlib.sha256(original.read_bytes()).hexdigest()
        image=out/(str(i)+'_'+state.path.name);shutil.copyfile(state.path,image);images.append(image)
        if i==0:
            state=load_analysis(path,image);state.path=image;state.verified=True
            save_analysis(state)
    existing=default_analysis_path(images[0]);before=existing.read_bytes()
    app=QApplication.instance() or QApplication([])
    errors=[]
    QMessageBox.critical=lambda *args:errors.append(args[-1])
    QMessageBox.warning=lambda *args:errors.append(args[-1])
    QMessageBox.information=lambda *args:None
    QMessageBox.question=lambda *args:QMessageBox.Yes
    BatchDialog.exec=lambda self:1
    w=ReaverMainWindow();w.show();w.open_directory(out)
    w.file_list.setCurrentItem(w.file_list.item(0))
    w.threshold_edit.setText('0.081');w.threshold_text_changed()
    params=w.app_state.params
    w.batch_action.trigger();wait(w,app)
    first=w.batch_report
    assert len(first['saved'])==len(images)-1 and not first['failed'] and not errors
    assert existing.read_bytes()==before
    def all_images(dialog):dialog.scope.setCurrentIndex(1);return 1
    BatchDialog.exec=all_images
    w.batch_action.trigger();wait(w,app)
    second=w.batch_report
    assert len(second['saved'])==len(images) and not second['failed'] and not errors
    for image in images:
        state=load_analysis(default_analysis_path(image))
        assert not state.verified and state.params==params
        expected=segment_image(state.base_image.data,params,(0,))
        for name in ('bw_2','wire','branchpoints','endpoints'):
            np.testing.assert_array_equal(getattr(state.derived_layers,name),getattr(expected,name))
    assert any(p.read_bytes()==before for p in (out/'.reaver-history').iterdir())
    app.processEvents();w.grab().save(str(out/'batch_preview.png'));w.close()
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
    (out/'report.json').write_text(json.dumps(dict(default_run=first,replacement_run=second,
        individual_segmentation_parity='exact',originals_unchanged=True,source_sha256=hashes),indent=2),encoding='utf-8')
    print('Real-image batch workflow passed:',out,flush=True)


if __name__=='__main__':main()
