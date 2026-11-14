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


def test_measurement_layout_defaults_and_invalid_data():
    from PySide6.QtCore import QByteArray
    layout = preferences.load_measurement_layout()
    assert layout['floating'] and layout['area'] == 2 and layout['geometry'].isEmpty()
    preferences.save_measurement_layout(False,1,450,QByteArray(b'geometry'))
    layout = preferences.load_measurement_layout()
    assert not layout['floating'] and layout['area'] == 1 and layout['width'] == 450
    assert layout['geometry'] == QByteArray(b'geometry')
    store = preferences.settings_store()
    store.setValue('measurements/dock_area',999)
    store.setValue('measurements/floating_geometry','invalid')
    store.sync()
    layout = preferences.load_measurement_layout()
    assert layout['area'] == 2 and layout['geometry'].isEmpty()


def test_measurement_layout_survives_new_process():
    import subprocess
    import sys
    from PySide6.QtCore import QByteArray
    preferences.save_measurement_layout(False,1,450,QByteArray(b'geometry'))
    code = '''import sys
from PySide6.QtCore import QSettings
from reaver.app import preferences
preferences.settings_store=lambda:QSettings(sys.argv[1],QSettings.IniFormat)
p=preferences.load_measurement_layout()
assert not p['floating'] and p['area']==1 and p['width']==450
assert bytes(p['geometry'])==b'geometry'
'''
    subprocess.run([sys.executable,'-B','-c',code,preferences.settings_store().fileName()],check=True)
