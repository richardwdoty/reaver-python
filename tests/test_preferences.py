import pytest
from reaver.app.preferences import load_default_resolution,save_default_resolution
from reaver.app import preferences


def test_default_calibration_persistence_and_invalid_data():
    assert load_default_resolution()==1
    save_default_resolution(.67381)
    assert load_default_resolution()==.67381
    for bad in ('bad',0,-1,float('nan'),float('inf')):
        store=preferences.settings_store();store.setValue('calibration/default_um_per_pixel',bad);store.sync()
        assert load_default_resolution()==1


@pytest.mark.parametrize('bad',[0,-1,float('nan'),float('inf')])
def test_invalid_calibration_does_not_replace_default(bad):
    save_default_resolution(.5)
    with pytest.raises(ValueError):save_default_resolution(bad)
    assert load_default_resolution()==.5


def test_calibration_survives_new_process():
    import subprocess
    import sys
    save_default_resolution(.812345)
    path=preferences.settings_store().fileName()
    code="""import sys
from PySide6.QtCore import QSettings
from reaver.app import preferences
preferences.settings_store=lambda:QSettings(sys.argv[1],QSettings.IniFormat)
print(preferences.load_default_resolution())
"""
    result=subprocess.run([sys.executable,'-B','-c',code,path],capture_output=True,text=True,check=True)
    assert float(result.stdout)==.812345
