"""Repeatable processing benchmark and exact before/after array comparison."""
import argparse
from dataclasses import fields
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from reaver.io.images import load_image_state
from reaver.core.segmentation import segment_image
from reaver.core.wire import compute_wire
from reaver.app.params import SegmentationParams


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--compare', type=Path)
    parser.add_argument('--image', action='append', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = []
    for index, path in enumerate(args.image):
        image = load_image_state(path).base_image.data
        baseline = None if args.compare is None else np.load(args.compare/f'{index}.npz')
        arrays, timings = {}, {}
        layers = segment_image(image)  # Warm imports, filter-factor cache, allocator.
        for name, fn in [('segment', lambda: segment_image(image)),
                         ('wire0', lambda: compute_wire(layers.bw_2)),
                         ('wire3', lambda: compute_wire(layers.bw_2, SegmentationParams(wire_dilation_threshold=3)))]:
            times = []
            for _ in range(args.repeats):
                start = time.perf_counter()
                result = fn()
                times.append(time.perf_counter()-start)
            timings[name] = dict(seconds=times, median=statistics.median(times))
            for field in fields(result):
                value = getattr(result, field.name)
                if value is not None:
                    key = name+'_'+field.name
                    arrays[key] = value
                    if baseline is not None:
                        np.testing.assert_array_equal(value, baseline[key], err_msg=str(path)+' '+key)
        if baseline is not None:
            baseline.close()
        np.savez_compressed(args.output/f'{index}.npz', **arrays)
        row = dict(image=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), timings=timings,
                   comparison='exact' if args.compare else 'baseline')
        report.append(row)
        print(json.dumps(row), flush=True)
    (args.output/'report.json').write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
