"""Real-image blinded review, display/export and identity checks on isolated copies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import numpy as np
import tifffile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
os.environ.setdefault('QT_QPA_PLATFORM','windows' if sys.platform=='win32' else 'offscreen')
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import QSettings,Qt,QPointF
from reaver.app import preferences
from reaver.gui import main_window
from reaver.io.results import load_analysis,save_analysis
from reaver.io.image_export import export_displayed_image


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis',type=Path,action='append',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    preferences.settings_store=lambda:QSettings(str(args.output/'test_preferences.ini'),QSettings.IniFormat)
    hashes={}
    for index,path in enumerate(args.analysis):
        state=load_analysis(path)
        for original in (path,state.path):hashes[str(original)]=hashlib.sha256(original.read_bytes()).hexdigest()
        source=args.output/(str(index)+'_'+state.path.name)
        shutil.copyfile(state.path,source)
        state=load_analysis(path,source);state.verified=False;save_analysis(state)
    app=QApplication.instance() or QApplication([])
    messages=[]
    for kind in ('critical','warning','information'):
        setattr(QMessageBox,kind,lambda *a:messages.append(a[-1]))
    w=main_window.ReaverMainWindow();w.show();w.open_directory(args.output)
    w.blind_action.setChecked(True)
    cases=[]
    for index in range(w.file_list.count()):
        item=w.file_list.item(index);w.file_list.setCurrentItem(item)
        state=w.app_state.active_image
        assert state.image_id==item.data(Qt.UserRole)
        assert state.path.name not in item.toolTip()+w.statusBar().currentMessage()
        before=state.derived_layers.bw_2.copy()
        w.verified_checkbox.setChecked(True)
        assert load_analysis(state.analysis_path).verified
        for mode in ('displayed_channels','grey','first_binary','segmented','overlay','wire_frame'):
            w.display_mode_combo.setCurrentIndex(w.display_mode_combo.findData(mode))
            pixels=w.current_display_array.copy()
            output=export_displayed_image(state.path,pixels)
            np.testing.assert_array_equal(tifffile.imread(output),pixels)
        w.image_label.zoom_at(QPointF(300,300),2)
        assert w.image_label.zoom==2 and len(w.image_label.markers)==2
        w.gamma_action.setChecked(True)
        w.display_mode_combo.setCurrentIndex(w.display_mode_combo.findData('overlay'))
        assert not state.dirty and state.verified
        np.testing.assert_array_equal(state.derived_layers.bw_2,before)
        secret=str(state.path)
        w.measurement_failed(secret)
        assert secret not in messages[-1] and state.path.name not in messages[-1]
        cases.append(dict(image=state.path.name,alias=item.text(),verified=True,exports=6))
    original_save=main_window.save_analysis
    def fail(*a,**kw):raise OSError(str(w.app_state.active_image.path))
    main_window.save_analysis=fail
    assert not w.save_current_analysis()
    assert w.app_state.active_image.path.name not in messages[-1]
    main_window.save_analysis=original_save
    app.processEvents();w.grab().save(str(args.output/'blinded_review.png'))
    w.blind_action.setChecked(False)
    assert w.file_list.currentItem().text()==w.app_state.active_image.path.name
    w.close()
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
    (args.output/'report.json').write_text(json.dumps(dict(cases=cases,originals_unchanged=True,
        source_sha256=hashes,blinded_error_checks='passed'),indent=2),encoding='utf-8')
    print('Real-image blinded review/export acceptance passed',flush=True)


if __name__=='__main__':main()
