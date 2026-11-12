"""Generate independent MATLAB references and compare all segmentation layers.

Run from any directory; outputs contain local research data and belong in data/tmp.
Use --snapshot only for the synthetic suite (no --image-dir).
"""
import argparse
from dataclasses import asdict
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.io import loadmat, savemat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from reaver.app.params import SegmentationParams
from reaver.core.segmentation import segment_image
from reaver.core import morphology as morph
from reaver.io.images import load_image_state

FIELDS = dict(gray='grey', gray_neighbors='greynbrs', local_mean='mean',
              bw_1='BW_1', bw_1_neighbors='BW_1nbrs', bw_2='BW_2', wire='wire',
              dilated_wire='dilated', dilated_wire_2='dilated2')
CONSTANTS = dict(averaging_filter_size='averagingFilterSize',
    grey_to_bw_threshold='grey2BWthreshold', min_connected_component_area='minCCArea',
    conway_iterations='ConwaysIterations', bridge_fill_iterations='bridgeFillIterations',
    bridge_iterations='bridgeIterations', fill_iterations='fillIterations',
    majority_iterations='majorityIterations', thin_iterations='thinIterations',
    vessel_thickness_threshold='vesselThicknessThreshold', wire_dilation_threshold='wireDilationThreshold')


def synthetic_cases():
    rng = np.random.default_rng(243)
    vessel = np.zeros((96, 128), np.uint8)
    vessel[20:40, :] = 255
    vessel[:, 50:70] = 255
    vessel[55:80, 10:110] = 190
    vessel[60:68, 40:50] = 0  # exactly 80 background pixels
    noise = rng.integers(0, 256, (96, 128, 3), dtype=np.uint8)
    for name, image in [('empty', np.zeros_like(vessel)), ('full', np.full_like(vessel, 255)),
                        ('vessels', vessel), ('rgb', noise)]:
        for variant in (0, 1):
            params = SegmentationParams(min_connected_component_area=10,
                averaging_filter_size=16 if variant == 0 else 17,
                wire_dilation_threshold=0 if variant == 0 else 3,
                vessel_thickness_threshold=3 if variant == 0 else 1)
            yield name + str(variant), image, params, (0,) if variant == 0 else (0, 1, 2)


def settings_cases():
    image = list(synthetic_cases())[4][1]
    for i, threshold in enumerate((0, .045, .2, .201, .603, 1)):
        params = SegmentationParams(averaging_filter_size=(9,16,17,32,7,12)[i],
            grey_to_bw_threshold=threshold, min_connected_component_area=(0,5,20,80,12,1)[i],
            wire_dilation_threshold=i % 4, vessel_thickness_threshold=(0,1.5,2,3.5,4,1)[i])
        yield 'settings_'+str(i), image, params, (0,)


def morphology_input():
    # Every 3x3 binary neighborhood, plus random pixels touching all boundaries.
    rng = np.random.default_rng(246)
    a = rng.random((100, 170)) > .5
    for i in range(512):
        y, x = divmod(i, 32)
        a[2+y*6:5+y*6, 2+x*5:5+x*5] = ((i >> np.arange(9)) & 1).reshape(3, 3, order='F')
    return a


def compare(image, params, channels, ref):
    actual = segment_image(image, params, channels)
    failures = {}
    for field, matlab_field in FIELDS.items():
        a, b = getattr(actual, field), ref[matlab_field]
        equal = np.isclose(a, b, rtol=0, atol=2e-12) if field == 'local_mean' else a == b
        if not np.all(equal):
            failures[field] = int(np.count_nonzero(~equal))
    for field in ('branchpoints', 'endpoints'):
        expected = np.asarray(ref[field]['coords']).reshape(-1, 2).astype(int) - 1
        if not np.array_equal(getattr(actual, field), expected):
            failures[field] = 'coordinates or order differ'
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matlab', required=True)
    parser.add_argument('--matlab-root', required=True, type=Path)
    parser.add_argument('--output', type=Path, default=ROOT/'data/tmp/parity')
    parser.add_argument('--image-dir', action='append', type=Path, default=[])
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--settings-only', action='store_true')
    args = parser.parse_args()
    if args.snapshot and args.image_dir:
        parser.error('Snapshots are synthetic only; do not commit private image data')
    args.output.mkdir(parents=True, exist_ok=True)
    cases = list(settings_cases() if args.settings_only else synthetic_cases())
    for directory in args.image_dir:
        paths = sorted(p for p in directory.iterdir() if not p.name.startswith('._') and p.suffix.lower() in ('.tif', '.tiff'))
        if not paths:
            raise ValueError(f'No TIFF images in {directory}')
        for index in sorted({0, len(paths)//2, len(paths)-1}):
            path = paths[index]
            image = load_image_state(path).base_image.data
            if image.shape[-1] == 1:
                image = image[..., 0]
            cases.append((str(path), image, SegmentationParams(), (0,)))
    mat_cases = np.empty(len(cases), dtype=object)
    for i, (name, image, params, channels) in enumerate(cases):
        constants = {v: float(getattr(params, k)) for k, v in CONSTANTS.items()}
        constants.update(survive=np.arange(4, 9), born=np.arange(4, 9))
        mat_cases[i] = dict(image=image, constants=constants,
                            channels=np.array([c in channels for c in range(3)]))
    inputs, outputs = args.output/'inputs.mat', args.output/'reference.mat'
    binary = morphology_input()
    savemat(inputs, dict(cases=mat_cases, morph_input=binary), do_compression=True)
    quote = lambda p: str(p.resolve()).replace('\\', '/').replace("'", "''")
    command = (f"addpath('{quote(ROOT/'tests/matlab')}'); "
               f"generate_reference('{quote(inputs)}','{quote(outputs)}','{quote(args.matlab_root)}')")
    subprocess.run([args.matlab, '-wait', '-nosplash', '-nodesktop', '-sd', str(args.output.resolve()), '-batch', command], check=True)
    data = loadmat(outputs, simplify_cells=True)
    report = dict(matlab_version=data['matlab_version'],
        versions={p: importlib.metadata.version(p) for p in ('numpy', 'scipy', 'scikit-image', 'tifffile')},
        source_sha256=hashlib.sha256((args.matlab_root/'REAVER GUI/segmentImage.m').read_bytes()).hexdigest(), cases=[])
    for case, reference in zip(cases, data['results']):
        name, image, params, channels = case
        failure = compare(image, params, channels, reference)
        report['cases'].append(dict(name=name, input_sha256=hashlib.sha256(image.tobytes()).hexdigest(), failures=failure))
        print(name, failure or 'EXACT', flush=True)
    report['morphology'] = {}
    for op, expected in data['morphology'].items():
        if op == 'branchpoints': result = morph.bwmorph_branchpoints_matlab(binary)
        elif op == 'endpoints': result = morph.bwlookup_matlab(binary, morph.LUT_ENDPOINTS)
        else:
            fn = getattr(morph, 'bwmorph_' + op + ('_matlab' if op in ('thin','spur','clean') else ''))
            result = fn(binary, iterations=1)
        report['morphology'][op] = int(np.count_nonzero(result != expected))
    print('Morphology:', report['morphology'])
    (args.output/'report.json').write_text(json.dumps(report, indent=2))
    failed = any(c['failures'] for c in report['cases']) or any(report['morphology'].values())
    if args.snapshot and not failed:
        args.snapshot.parent.mkdir(parents=True, exist_ok=True)
        args.snapshot.write_bytes(outputs.read_bytes())
        args.snapshot.with_suffix('.json').write_text(json.dumps(report, indent=2))
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
