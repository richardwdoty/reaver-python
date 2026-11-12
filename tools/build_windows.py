"""Build a portable Windows folder and ZIP using the active Python environment."""
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    if sys.platform != 'win32':
        raise SystemExit('Build the Windows application on Windows.')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
        '--distpath', str(ROOT/'dist'), '--workpath', str(ROOT/'build'),
        str(ROOT/'packaging/REAVER.spec')], cwd=ROOT, check=True)
    folder = ROOT/'dist/REAVER'
    shutil.copyfile(ROOT/'docs/windows_download.txt', folder/'START HERE.txt')
    # Include the dependency versions and licenses from the build environment.
    licenses = folder/'licenses'
    licenses.mkdir(exist_ok=True)
    shutil.copyfile(ROOT/'packaging/libffi-LICENSE.txt', licenses/'libffi-LICENSE.txt')
    import importlib.metadata as metadata
    versions = []
    for dist in metadata.distributions():
        name = dist.metadata['Name']
        versions.append(f'{name}=={dist.version}')
        for file in dist.files or []:
            if '.dist-info/' in str(file).replace('\\', '/') and any(
                word in file.name.lower() for word in ('license', 'copying', 'notice')):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    target = licenses/name/str(file)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
    (folder/'build-versions.txt').write_text('\n'.join(sorted(versions)), encoding='utf-8')
    archive = Path(shutil.make_archive(str(ROOT/'dist/REAVER-Windows-x64'), 'zip', ROOT/'dist', 'REAVER'))
    archive.with_suffix('.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
    print(archive)

if __name__ == '__main__':
    main()
