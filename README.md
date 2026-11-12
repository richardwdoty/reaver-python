# REAVER Python

Python refactor of the MATLAB REAVER vascular-analysis GUI. The automatic
segmentation and wire cores are available. The integrated prototype GUI supports
image browsing, channel selection, segmentation, derived-image inspection,
zoom/pan, square-brush editing, Update Wire, MATLAB-style single-batch undo,
and compact `.reaver` saves, with older MATLAB/Python `.mat` compatibility.
Batch processing defaults to unprocessed images, with confirmation and backups
for replacements. Saved, verified, and pending indicators help track work; File contains discard
and recoverable analysis-removal controls. Original files are preserved.
MATLAB-compatible vessel measurements, calibrated units, and current-image or
verified-directory CSV exports share a single `<directory name>.csv`. Original MATLAB verification
tables are read without modification; Python verification flags stay in separate
analysis files.

Launch with `python -m reaver` or the installed `reaver` launcher. On Windows,
you can also open `.venv/Scripts/reaver.exe` directly after installing.
See [the quick start](docs/quick_start.md).

```python
from reaver.io.images import load_image_state
from reaver.core.segmentation import segment_image
from reaver.app.params import SegmentationParams

state = load_image_state("image.tif")
layers = segment_image(state.base_image.data, SegmentationParams(), channels=(0,))
# layers.bw_2: vessel mask; layers.wire: skeleton
# layers.branchpoints / endpoints: zero-based (x, y), MATLAB column-major order
```

Install for development with `python -m pip install -e ".[test]"` and run
`python -m pytest`. MATLAB is not needed for normal use or the saved-reference
tests. See [MATLAB parity](docs/matlab_parity.md) for reference provenance,
regeneration, and the limits of the current verification.
