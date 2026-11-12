"""Independent MATLAB brush references; originals are read only."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
from scipy.io import savemat
from check_matlab_parity import ROOT, CONSTANTS, synthetic_cases


def constants(params):
    values = {v: float(getattr(params, k)) for k, v in CONSTANTS.items()}
    values.update(survive=np.arange(4, 9), born=np.arange(4, 9))
    return values


def generate_reference(cases, output, matlab, matlab_root):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_path = Path(matlab_root)/'REAVER GUI/updateWire.m'
    source = source_path.read_text()
    patched = source.replace("'symmetric'", "'replicate'").replace(
        '2*handles.constants.wireDilationThreshold', 'handles.constants.wireDilationThreshold')
    patched = patched.replace('handles.image.CData = createNewBW2( handles ) ;', '% Headless reference.')
    (output/'updateWire.m').write_text(patched)
    (output/'editing_reference.m').write_bytes((ROOT/'tests/matlab/editing_reference.m').read_bytes())
    savemat(output/'inputs.mat', dict(cases=np.array(cases, dtype=object)), do_compression=True)
    quote = lambda p: str(p).replace('\\', '/').replace("'", "''")
    command = "editing_reference('"+quote(output/'inputs.mat')+"','"+quote(output/'reference.mat')+"')"
    subprocess.run([str(matlab), '-wait', '-nosplash', '-nodesktop', '-sd', str(output), '-batch', command], check=True)
    provenance = dict(source=str(source_path), original_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
        brush_source_sha256=hashlib.sha256((Path(matlab_root)/'REAVER GUI/REAVER_GUI.m').read_bytes()).hexdigest(),
        changes=['replicate padding', 'no 2x dilation radius', 'omit GUI renderer'],
        brush='figButtonMotion interpolation, rounding, bounds, and square dilation; coordinates converted to one-based')
    (output/'reference.json').write_text(json.dumps(provenance, indent=2))
    return output/'reference.mat'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matlab', required=True)
    parser.add_argument('--matlab-root', required=True, type=Path)
    args = parser.parse_args()
    # Forward/reverse diagonals, vertical, border clipping, sparse long motion,
    # erase, all brush extremes, and centers outside the image.
    strokes = np.array([[10, 10, 10, 10, 1, 1], [10, 10, 100, 79, 1, 1],
        [100, 79, 10, 10, 4, 1], [64, 10, 64, 90, 2, 0],
        [0, 0, 0, 95, 16, 1], [127, 95, 110, 83, 16, 0],
        [20, 30, -30, -40, 4, 1], [-30, -40, 160, 120, 1, 0],
        [64, 40, 64, 40, 16, 1]], dtype=float)
    cases = []
    for name, image, params, _ in list(synthetic_cases())[4:]:
        binary = (image if image.ndim == 2 else image[:, :, 0]) > 100
        cases.append(dict(name=name, binary=binary, strokes=strokes, constants=constants(params)))
    result = generate_reference(cases, ROOT/'data/tmp/editing_reference', args.matlab, args.matlab_root)
    fixture = ROOT/'tests/fixtures/editing_reference.mat'
    fixture.write_bytes(result.read_bytes())
    fixture.with_suffix('.json').write_bytes(result.with_suffix('.json').read_bytes())


if __name__ == '__main__':
    main()
