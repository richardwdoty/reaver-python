# Windows portable application

Extract `REAVER-Windows-x64.zip` completely, then run `REAVER/REAVER.exe`.
Keep the accompanying `_internal` folder. No Python or MATLAB installation
is required. This unsigned preview may trigger a Windows publisher warning.

## Building on Windows

In a Python 3.12 project virtual environment, install
`-r packaging/windows-requirements.txt` and then install the project with
`pip install --no-deps .`. Run
`python tools/build_windows.py`. The portable folder, ZIP and SHA-256 checksum
are written under ignored `dist/`. Build outputs and research images must
not be committed. Use GitHub release assets to distribute the ZIP.

The build uses PyInstaller's one-folder layout, which keeps startup simple
and avoids extracting the complete runtime on every launch. See
https://pyinstaller.org/en/stable/operating-mode.html.

The executable's `--acceptance --analysis PATH --output NEW_DIRECTORY`
mode runs the copied-data review/export checks and writes `report.json`
or `failure.txt`. Use a fresh output directory. This is a developer check,
not part of normal researcher startup.
