"""Extract and test a Windows ZIP without Python on the child search path."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import zipfile

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip', type=Path, required=True)
    parser.add_argument('--analysis', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(args.zip) as archive:
        archive.extractall(args.output)
    env = os.environ.copy()
    for name in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH'):
        env.pop(name, None)
    env['PATH'] = str(Path(env.get('SYSTEMROOT', r'C:\Windows'))/'System32')
    command = [str(args.output/'REAVER/REAVER.exe'), '--acceptance', '--output', str(args.output/'results')]
    for analysis in args.analysis:
        command += ['--analysis', str(analysis.resolve())]
    subprocess.run(command, env=env, cwd=args.output, timeout=300, check=True)
    report = json.loads((args.output/'results/report.json').read_text())
    baseline = json.loads(args.baseline.read_text())
    assert report['originals_unchanged']
    assert {x['image']: x['segmentation_sha256'] for x in report['cases']} == {x['image']: x['segmentation_sha256'] for x in baseline['cases']}
    print('Extracted Windows package passed; segmentation matches source.')

if __name__ == '__main__':
    main()
