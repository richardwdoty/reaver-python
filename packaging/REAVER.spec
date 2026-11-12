from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH).parent
# A venv created from Conda hides its Library/bin from dependency discovery.
ffi = Path(sys.base_prefix)/'Library/bin/ffi.dll'
a = Analysis([str(root/'packaging/windows_entry.py')],
    pathex=[str(root/'src'), str(root/'tools')],
    datas=[(str(root/'LICENSE'), '.')]+collect_data_files('skimage'),
    binaries=[(str(ffi), '.')] if ffi.exists() else [],
    hiddenimports=[], excludes=['pytest', 'matplotlib', 'tkinter'],
    noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='REAVER',
    console=False, debug=False, strip=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='REAVER')
