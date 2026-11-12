# MATLAB compatibility

The baseline is `public_REAVER` commit
`3abffe8a42e78d4823836268ab23be202ad34bda`, specifically the GUI's
`REAVER GUI/segmentImage.m`, executed with MATLAB R2024a. The original project's
README names R2018b; that runtime has not been verified here.

The implementation was adapted from Richard Doty's original `main.py` and
`morph_luts.py` under `Box Sync/Python/REAVER`. Those originals and the MATLAB
repository remain unchanged. The pipeline is pure computation: it does not
change image state, save files, or create a GUI. It returns a `DerivedLayers`
object, with final masks under `bw_2` and `wire`. Input arrays are not modified.
Grayscale is retained as one channel by the loader and bypasses RGB weighting.
TIFF directories are concatenated as channels, matching the MATLAB loader;
two channels receive a zero third channel. Unsupported dimensions/channel
counts raise an error instead of guessing that a stack is RGB.

## Corrections relative to the prototype/scaffold

- Restored GUI defaults: 8 Conway iterations, 4 bridge/fill rounds, thinning
  to convergence, and vessel thickness threshold 3.
- Matched four-neighbor fill, including background outside the image.
- Used the custom MATLAB thinning implementation in the initial two-iteration
  step as well as skeletonization.
- Filled inverse components strictly smaller than 80 pixels, including boundary
  components; a component of exactly 80 is retained.
- Assigned nonzero wire dilation back to the final vessel mask.
- Corrected one-based to zero-based border exclusions and point ordering.
- Matched the infinite distance result for an entirely foreground image.
- Replaced exploratory field aliases with the application's declared fields.
- Replaced wrapping integer casts with MATLAB-style image intensity conversion.
- Matched the separable SVD averaging-filter computation. Integral-image and
  running-sum alternatives each flipped strict threshold decisions in a real
  sample because of numerical roundoff. No epsilon is added to thresholds.

`segment_image` implements initial segmentation only. MATLAB's `updateWire.m`
historically uses different padding and dilation; see the corrected Update Wire
implementation below. Editing and network measurements have separate validation
sections below.

## Saved reference tests

`tests/fixtures/matlab_reference.mat` contains independently generated MATLAB
outputs for eight deterministic synthetic cases. Its adjacent JSON records the
MATLAB version, source SHA-256, input hashes, dependency versions, and results.
Inputs are reconstructed by `tools/check_matlab_parity.py`: empty/full images,
border-crossing vessels and a hole, and random RGB, with even/odd filter sizes,
single/all channels, and zero/nonzero wire dilation. Morphology tests include
all 512 binary 3x3 neighborhood patterns plus random boundary pixels.

All masks, dilations, grayscale layers, and point arrays must match exactly.
The floating-point local-average layer allows absolute error up to 2e-12;
downstream threshold decisions must still match exactly. References are never
generated from the Python segmentation implementation.

Example regeneration (PowerShell, from the repository):

```powershell
python tools/check_matlab_parity.py `
  --matlab 'C:\Program Files\MATLAB\R2024a\bin\matlab.exe' `
  --matlab-root '..\public_REAVER' `
  --output data/tmp/synthetic_parity `
  --snapshot tests/fixtures/matlab_reference.mat
```

Add repeated `--image-dir` arguments to verify local research images without
creating a committed snapshot. The script selects the first, middle, and last
TIFF by filename from each directory and excludes macOS `._` metadata files.
Outputs and images are kept under ignored `data/tmp`; private research images
are not added to the test fixtures. Nonzero exit status indicates a mismatch.

Initial local verification also covered three original images and three images
from each of `Exp_243 unblind images` and `blind 246`. This is representative
coverage, not certification of every image or parameter combination. Floating
point libraries and MATLAB releases may differ; rerun these checks when changing
scientific dependencies or target platforms. Windows R2024a is the runtime
verified so far; macOS remains untested.

## Update Wire

`core.wire.compute_wire` shares the same mask-to-skeleton implementation with
automatic segmentation. It uses replicated padding and disk radius r. The
conditional mask intersection is retained when the dilation threshold is positive.
`apply_binary_edit(state, mask)` accepts a changed mask and marks the wire stale;
`update_wire(state, params)` consumes that permission only on success. Another
update requires another edit. No-op edits do not enable an update. Saving requires
an up-to-date wire, matching MATLAB's disabled Save button while editing.

Eight saved synthetic references compare against a temporary copy of MATLAB
`updateWire.m`, with only the agreed padding/radius corrections and the final
GUI rendering call omitted. Originals are never rewritten. Regenerate with
`python tools/generate_wire_reference.py --matlab <executable> --matlab-root <repo>`.
The fixture includes its masks, constants, MATLAB version, and an adjacent source
provenance JSON. Ordinary tests need no MATLAB installation.

## GUI editing

The GUI implements MATLAB's square brush (displayed setting = radius + 1),
left-add/right-erase, 50 interpolated samples per motion event, MATLAB rounding,
and clipping of sampled centers before brush dilation. The overlay keeps the
previous wire while the binary is being edited; the dedicated wire view is
disabled until Update Wire or Undo. Update Wire uses the corrected replicate/r
path above, including conditional binary modification for positive dilation.

Undo restores the single pre-batch derived-image backup, before or after the
update. A new edit after an update captures a new backup. Multiple strokes before
an update share a backup. Failed computations retain both the edited mask and
the right to retry; controls lock while a worker runs. Each image keeps its own
backup and pending-update state. A deliberate existing safeguard is retained:
a brush gesture that changes no pixels does not unlock Update Wire (the MATLAB
callback enables its button even for such clicks).

`tests/fixtures/editing_reference.mat` contains four MATLAB-generated synthetic
cases with nine brush segments each, including reverse diagonals, verticals,
border crossings, out-of-bounds centers, brush settings 1 and 16, and erasing.
Every intermediate mask and all final wire outputs are compared exactly.
`tests/matlab/editing_reference.m` transcribes the brush rasterization from
`REAVER_GUI.m`; it calls a temporary corrected `updateWire.m`. The adjacent
JSON records hashes of the unchanged MATLAB sources. Regenerate with:

```powershell
python tools/generate_editing_reference.py --matlab 'C:\Program Files\MATLAB\R2024a\bin\matlab.exe' --matlab-root '..\public_REAVER'
```

`tests/test_gui.py` sends Qt mouse/wheel/key events through the actual canvas,
checks placement after zoom/pan, both undo timings, read-only views, image
switching, no-op edits, and worker-failure recovery. `tools/check_gui_editing.py`
runs native Windows Qt on the bundled image and first/middle/last TIFF from each
supplied directory, then compares each recorded brush segment and updated wire
against MATLAB. It exercises zero and positive dilation, both undo timings,
repeat-update rejection, and Fit, and checks source-file hashes before/after.
Run with the same `--matlab` and `--matlab-root` arguments plus repeated
`--image-dir` arguments. Research data, report, and a screenshot stay under
ignored `data/tmp/gui_editing`; real images are not copied into saved fixtures.
This verifies the Python GUI event/state workflow and MATLAB numerical outputs,
not identical rendering or replay of a live MATLAB GUI session. macOS interaction
and packaging remain untested.

The Windows run on 2026-11-01 passed on seven 1024×1024 images: the bundled
example, `10L_I2.ids.tif`, `3R_I1.ids.tif`, `9R_I4.ids.tif`, and blind-246 images
`1.tif`, `51.tif`, and `92.tif`. All 42 recorded brush segments and all seven
updated masks, wires, dilations, and point arrays matched MATLAB R2024a exactly.
Three cases used dilation radius 3 and exercised binary shrinkage; four used 0.
Both undo timings passed, and source-image, MATLAB, and prototype hashes were
unchanged. The full automated suite passed 43 tests. These are representative
cases, not exhaustive image coverage.

## Performance pass (2026-11-01)

Thinning now tracks foreground coordinates for sparse images, with the original
full-image lookup path for dense subiterations. Both MATLAB thinning tables only
delete pixels: skipping background evaluations therefore preserves the same two
ordered, simultaneous subiterations and convergence result. A test checks that
table invariant and compares against the original dense sequence across empty,
full, random, single-row/column, and noncontiguous inputs with finite/infinite
iteration counts. No lookup tables or segmentation parameters changed.

The Conway stage uses uint8 neighbor counts (maximum eight). Since its original
birth and survival sets are both 4..8, a single `neighbors >= 4` produces exactly
the same decision without repeated membership tests and full-width integer
temporaries. The floating-point averaging path remains unchanged. No dependency
was added, and the MATLAB and Box prototype originals remain untouched.

Windows processing times below are medians of three runs after warming the
pipeline; they exclude file loading and GUI rendering. These are local before/
after Python timings, not a measured comparison with MATLAB.

| Image | Segment before → after | Update Wire before → after (radius 0) |
| --- | --- | --- |
| example_rgb.tif | 2.212 → 1.156 s | 1.850 → 0.797 s |
| Exp_243 / 10L_I2.ids.tif | 2.361 → 1.201 s | 1.856 → 0.768 s |
| blind 246 / 51.tif | 2.276 → 1.207 s | 1.788 → 0.750 s |

Radius-3 updates improved from 1.825–1.943 s to 0.775–0.790 s. All returned arrays
matched preserved baseline outputs exactly, including intermediate segmentation
layers and both wire radii. The suite passed 124 tests, including MATLAB fixtures
and the GUI workflow. Local snapshots and timing samples are in ignored
`data/tmp/performance_before` and `data/tmp/performance_after`.

Reproduce with `tools/benchmark_processing.py --output <directory> --image
<image>` (repeat `--image` as needed). On the optimized revision, add `--compare
<baseline-directory>` using the same image order. The script preserves exact
array snapshots, image hashes, individual timings, and medians. Further changes
must retain exact parity; these results do not establish macOS performance.

## Saving and reopening (2026-11-01)

This section records the original MAT persistence pass. The native default and
CSV behavior were superseded by the 2026-11-03 changes below; MAT interchange
calculations and stored reference fixtures remain unchanged.

`io.results` follows `REAVER_GUI.m`'s `saveDataButton_Callback` and saved-file
loading branch. MAT v5/v7 files contain `derivedPic.BW_2`, `wire`, one-based
`branchpoints`/`endpoints`, `constants`, `image_resolution`, `imageSize`,
`imageDirectory`, and the four original save-summary metrics. Sparse MATLAB
wires are accepted. Python writes separate `<image filename>.reaver.mat` files
by default and refuses to overwrite original MATLAB analyses. Directory discovery
prefers that separate file, then falls back to MATLAB's `<stem>.mat` convention.

Python files additionally contain versioned `reaverPython` source metadata and
`reaverLayers` for exact intermediate-view restoration. MATLAB ignores these
extra variables. Native files verify a fingerprint of the normalized source pixels;
all files validate dimensions, binary values, point bounds, and settings before
replacing GUI state. Source images are required, with a locate-image dialog for
missing/moved files. MATLAB v7.3/HDF5 is currently rejected with an explicit error.

Reopening restores the edited binary and saved wire/point arrays directly. Older
MATLAB files rebuild only the initial display layers and wire display dilations,
as MATLAB does; neither segmentation of BW_2 nor wire calculation is repeated.
The original loading defaults for missing thickness/dilation settings are 3/0.
Legacy files without image resolution use 1.0; verify that assumption before
using physical-unit measurements. The original verification table remains untouched.

Saving requires completed segmentation and no pending wire update. Files are
compressed into a same-directory temporary file, flushed, read back for validation,
then atomically replaced. Errors preserve the old save and dirty state. Reopening
sets up a fresh undo baseline, disables Undo/Update Wire, and restores each image's
settings; prior undo history is not persisted. Save/discard/cancel guards protect
cached unsaved results on close, directory change, and explicit reopening.

The save-summary mean diameter follows MATLAB's single-precision distance image,
column-major indexing, and R2024a accumulation order. Independent references in
`tests/fixtures/save_mean_reference.mat` cover 305 synthetic vector lengths;
`tests/matlab/save_mean_reference.m` regenerates them. Other MATLAB releases and
platforms may use different summation order. For strict source fidelity, the
legacy `numBranchPoints = max(size(coords))` expression is retained, including
its surprising result of 2 for zero/one-row coordinate arrays. This is a known
legacy summary-field behavior, not the actual number of stored branchpoints.
The network measurement/export path below is distinct from these save summaries.

Validation passed 138 tests, including exact layer round trips, grayscale/singleton
dimensions, sparse legacy files, moved/mismatched sources, malformed files,
interrupted writes, and GUI editing/save/reopen/undo and cancellation. Native
Windows GUI round trips passed on copies of `example_rgb.tif`, `10L_I2.ids.tif`,
and blind-246 `51.tif`. MATLAB R2024a independently checked the final masks,
points, and all four saved metrics exactly, then re-saved sparse-wire files that
Python reopened with identical layers. Original blind-246 `1.mat` and `51.mat`
also imported/re-saved exactly. Original image/analysis hashes remained unchanged.

`tools/check_analysis_roundtrip.py --matlab <executable> --image <image>` repeats
the native GUI/MATLAB workflow; repeat `--image` and add `--legacy <mat-file>`
as needed. Generated copies, screenshots, and the report stay under ignored
`data/tmp/analysis_roundtrip`. This verifies file interchange and Python GUI
behavior; it does not replay the original MATLAB GUI or certify macOS packaging.

## Vessel measurements and analysis CSV export (2026-11-01)

The source of truth is `Network Quantification/reaver_quantify_network.m`, with
`skel_2_linesegs.m`, `rcind_seg_tortuosity.m`, and `measure_segment_rad.m`.
Python `core.metrics.quantify_network` ports their calculations without altering
binary masks, skeletons, or saved point arrays. The new measurement panel and
CSV exports use this path; the older four Save Analysis summary fields are
retained separately. Calculated network measurements are cached only in memory,
invalidated on edits/undo/wire updates/calibration changes, and recomputed on
request after reopening.

The CSV starts with `image_name` (originally the saved analysis filename; now
the source image filename for stable row updates across format conversion), followed by
these fields in MATLAB's order. Let H and W be image height/width, r the µm/pixel
resolution, L the number of nonzero wire pixels, B the saved branchpoint count,
and S the number of surviving traced segments.

| Field | Preserved MATLAB calculation |
| --- | --- |
| fov_um | r × H |
| umppix | r |
| vessel_area_fraction | foreground binary pixels / (H × W) |
| vessel_length_um | L × (fov_um / H) |
| vessel_length_density_mmpmm2 | L × (fov_mm / H) / fov_mm² |
| branchpoint_count | Number of rows in the saved branchpoint array |
| segment_count | S |
| mean_segment_length_um | Mean number of rows in each traced segment × r |
| mean_tortuosity | Mean of 2 × segment row count / endpoint distance; exclude distances < 5 pixels |
| mean_valency | B / S |
| mean_segment_diam_um | Mean across segments of (2 × mean distance-transform radius + 1) × r |
| max_diffusion_dist_um | Mean maximum distance to vessels in each 8-connected background component × r |

These are legacy definitions, not replacements with geometric centerline length,
graph degree, or conventional tortuosity. Length counts diagonal pixels as one;
tortuosity uses MATLAB `numel(N-by-2)` and thus has a factor of two. Length density
uses the square of the image-height field of view even for rectangular images.
Diffusion components include boundary-connected background, not only enclosed
holes. Network diameter averages segment radii, adds one pixel, and differs
from the older save-summary diameter that averages all positive wire distances.
These behaviors are intentionally retained for fidelity.

Segment extraction reproduces clockwise, eight-connected `bwtraceboundary`
from the first column-major foreground pixel, starting west. Split points are
saved branches/endpoints plus endpoints on the image border. Endpoint-inclusive
trace intervals of at most five rows are discarded. Repeated visits and reverse
segments are retained. Processed traces are removed, split points added back,
and one-pixel components removed. The loop runs at most B times, matching R2024a's
interpretation of the source's nonscalar colon expression. All-zero/no-branchpoint
analyses trigger a legacy MATLAB cell-array error; Python reports a descriptive
`MeasurementError` and produces no partial export. With branchpoints but zero
surviving segments, undefined means remain NaN and valency remains Inf.

Radius samples preserve MATLAB's single-precision distance-transform values and
mean accumulation. Diffusion maxima are converted to double before averaging.
Counts, segment coordinates/order, endpoint classifications, and segment radii
are required to match exactly; final floating-point summaries use rtol/atol 1e-12.
CSV uses the same headers, row values, `NaN`, and `Inf`, with 17 significant digits
instead of MATLAB writetable's 15-digit formatting, so the files are numerically
equivalent rather than byte-identical.

The GUI provides Measure Vessels, µm/pixel calibration, single-analysis export,
and verified-directory export. Single export requires a saved, current analysis;
directory export refuses cached unsaved changes and selects only verified saved
analyses. MATLAB `User Verified Table.mat` is read without modification. Python
verification changes are saved in the separate analysis metadata, with explicit
flags overriding old table entries. Image names are matched exactly rather than
using MATLAB's ambiguous prefix matching. Legacy verification tables and analyses
are never overwritten. CSV writes use same-directory temporary files and atomic
replacement, and calculation failure leaves an existing CSV untouched.

Validation: 156 tests passed, including ten synthetic networks, the independently
generated MATLAB CSV, calibration scaling, invalidation, verification persistence,
selection, export cancellation, and write failures. On five real analyses
(`example_rgb`, `10L_I2`, edited `51`, and original blind-246 `1.mat`/`51.mat`),
all 1,218 traced segments, their ordering, per-segment radii, and endpoint flags
matched MATLAB R2024a exactly. The largest absolute difference across all final
measurement values was 4.45e-16. Native Windows measurement/verification/CSV GUI
checks passed on three copied real analyses; original file hashes were unchanged.
The measurement panel was also inspected at the default window size.

Regenerate synthetic MAT/CSV references with:

```powershell
python tools/generate_measurement_reference.py --matlab <executable> --matlab-root <MATLAB-repo> --snapshot
```

The fixture's JSON records hashes of the unchanged MATLAB sources. For real
analyses, omit `--snapshot` and add repeated `--analysis <saved.mat>` arguments;
`--output` selects an ignored temporary directory. Then run
`python tools/check_measurement_parity.py <output>/reference.mat` to compare all
segments and metrics and write the comparison report. Native GUI checks use
`tools/check_measurement_workflow.py --analysis <saved.mat>` (repeat as needed).
Local evidence is in `data/tmp/measurement_reference/comparison.json` and
`data/tmp/measurement_workflow/report.json`. MATLAB is needed only to regenerate
references, not to measure or export in Python. Other MATLAB releases and macOS
remain unverified.


## Compact native format and workflow (2026-11-03)

The default is now `<image filename>.reaver`: a version-1 ZIP archive containing
`manifest.json` and four numeric `.npy` arrays (`BW_2`, `wire`, `branchpoints`,
`endpoints`). No pickle, intermediate-image cache, or measurement summaries are
stored. Coordinates in this archive retain the one-based MATLAB interchange
convention; loading converts to the existing zero-based internal convention.
The manifest records settings, calibrated resolution, source name/path and pixel
fingerprint, verification, and the algorithm identifier. Native saves use the
existing temporary-write/readback/atomic-replace path. Display intermediates
are regenerated during loading, without recomputing saved masks, wire, or points.

Existing Python `.reaver.mat` and MATLAB `.mat` files remain readable. Opening
one and saving normally writes a separate native file. Explicit new MAT copies
remain available and preserve the original four summary calculations for MATLAB
interchange. Existing MAT files are never overwritten. Discovery prefers native,
then Python MAT, then original MATLAB MAT.

File is a toolbar dropdown. Selecting an image by mouse or keyboard resets the
view to Displayed Channels. Saved, verified, and pending states have distinct
icons and descriptive tooltips, including before an analysis is loaded. Binary
edits, wire updates, undo, resegmentation, and calibration changes clear
verification; no-op brush strokes and display changes do not. Discard Current
or Discard All restores saved data/verification, or the unsegmented source if no
save exists. All replacements are loaded before any cached work is discarded.

Remove Saved Analysis asks before discarding work, moves native saves into
`.reaver-trash`, and removes the image's common CSV row. A per-image
`.reaver.deleted` marker suppresses automatic legacy MAT rediscovery; those
original files and all source pixels remain untouched. Explicit Open Analysis
still imports legacy files. Removing the marker restores legacy discovery.

Vessel results share `<directory name>.csv`. Current-result export upserts a row
by source image filename; verified-directory export rebuilds that same file.
MATLAB's numerical columns and ordering are unchanged. Empty verified sets write
only the header. Changed GUI saves remove the old row until the user exports
current measurements. Calculation/write failures leave the previous CSV intact;
unrelated CSV headers are rejected. A CSV failure after a successful analysis
save/removal is reported separately because these are distinct disk writes.

Validation: 168 tests passed, including native corruption, migration, atomic
write failures, source identity, verification transitions, metadata-only status
lookup, discard/removal, shared CSV updates, and all existing MATLAB parity tests.
`tools/check_native_workflow.py --analysis <file>` exercises isolated copies in
`data/tmp/native_workflow_<timestamp>` and verifies hashes of every original.
Three real analyses passed native Windows GUI workflows, including exact
all-layer reopening, edit/update/save/reopen, verification, discard, shared CSV
upserts, and removal:

| Original analysis | Original bytes | Compact bytes |
| --- | ---: | ---: |
| Exp_243 `10R_I3.ids.tif.reaver.mat` | 8,838,084 | 49,969 |
| Exp_243 `10R_I1.ids.mat` | 69,214 | 61,504 |
| blind 246 `51.mat` | 63,840 | 59,768 |

All original image/analysis hashes remained unchanged. The earlier MATLAB
reference fixtures still establish algorithm parity; this pass changes storage
and workflow only. macOS runtime behavior remains untested.


### Simplified file controls and replacement confirmation

The GUI now exposes directory-based opening and fixed native saving only. Open
Analysis and Save Analysis As (including their shortcuts) were removed. Save uses
`<image filename>.reaver` beside the source even if the state previously came from
a differently named save. The internal MAT import/export API remains available
for compatibility and reference testing. Existing data requires confirmation
before resegmentation; cancellation changes neither memory nor disk. Selection
shows Overlay for segmented images, Displayed Channels for raw images. Image
list tooltips explicitly use a light background and dark foreground. All 170
tests pass, including confirmation cancellation/acceptance and fixed save naming.


## Threshold and segmentation settings controls

The threshold slider uses MATLAB's x range 0–0.4: t=x through 0.2, then
 t=4x−0.6. Slider coordinates and values use nonnegative half-up rounding to
three decimals. Numeric entry accepts 0–1 and retains the rounded numeric value
even if the slider's rounded coordinate cannot represent it exactly. Settings
expose the four fields from `settingsButton_Callback`; validation rejects
nonfinite/negative values and fractional sizes/radii that the processing core
cannot accept. No processing algorithm changed.

Proposed parameters are separate from result parameters and persist in memory
per image. Segment Image applies them on success. Save continues to record the
actual result's parameters. Update Wire uses that same parameter set, avoiding
mixing new preprocessing proposals with an already edited binary image.

Six independent MATLAB R2024a cases, including threshold endpoints, values on
both sides of 0.2, odd/even filter sizes, nonzero wire dilation, and fractional
thickness thresholds, are stored separately in `tests/fixtures/settings_reference.mat`.
Regenerate with `tools/check_matlab_parity.py --settings-only --matlab <exe>
--matlab-root <original repo> --output <working directory> --snapshot
 tests/fixtures/settings_reference.mat`. All final arrays/coordinates match;
local means use the existing 2e-12 tolerance. Original reference fixtures remain
unchanged. `tools/check_settings_workflow.py` checks the same path through the
native GUI and saved files using an isolated copy of a real image.

Validation passed 199 tests. A native Windows GUI run on a copy of Exp_243
`10R_I3.ids.tif` used threshold 0.081, filter size 33, minimum area 200,
wire dilation 2, and thickness 1.5. Save/reopen preserved the arrays and settings;
independent MATLAB comparison passed, and the original image hash was unchanged.
Evidence is under `data/tmp/settings_workflow_20261103_120823`.


## Batch processing

Batch processing calls the same validated loader, segment_image, and atomic
native save functions, with a snapshot of the current settings/channels. Default
scope skips saved and in-memory analyses; replacement requires confirmation and
pending edits must first be saved or discarded. Native replacements are copied
to `.reaver-history`; MAT originals are not overwritten. Each new result is
unverified. Newly appearing saved analyses are skipped unless their path was
approved for replacement. Cancellation completes the current image and stops
before the next. Per-image failures do not roll back completed images.

Validation: 205 tests passed. `tools/check_batch_workflow.py` exercised native
Windows GUI batches on copies of Exp_243 `10R_I3.ids.tif`, `10R_I1.ids.tif`, and
blind-246 `51.tif`, using threshold 0.081. The default run processed two unsaved
images and preserved the existing verified save byte-for-byte. A confirmed
replacement run processed all three and retained prior native saves in history.
All final binary/wire/point arrays matched individual segmentation exactly.
Every original image and analysis hash remained unchanged. Evidence is under
`data/tmp/batch_workflow_20261103_121356`; MATLAB algorithms were not changed.


## TIFF image exports (2026-11-07)

Exports follow `exportBinarySegmentation_Callback` (saved BW_2 for all analyses,
`bw` subdirectory, TIFF) and `exportDisplayedImage_Callback` (full image CData,
timestamped TIFF beside the source). Native and MAT masks are supported directly;
no intermediate views or original pixels need regeneration for binary export.
The current Python rendered display is exported exactly; previously documented
MATLAB overlay-styling differences remain. Collision suffixes deliberately replace
MATLAB's overwrite behavior to preserve originals. No existing export is replaced.

211 tests passed, covering binary TIFF depth, RGB/grayscale pixel identity,
collisions, failed writes, saved-vs-unsaved mask semantics, and GUI exports.
Windows GUI exports on copies of Exp_243 `10R_I3.ids.tif` and blind-246 `51.tif`
matched saved masks and displayed pixels exactly, with unchanged original hashes.
Evidence: `data/tmp/image_exports_20261107_112829/report.json`.
MATLAB R2024a independently read both exported TIFF masks as logical arrays and verified exact equality with the original saved BW_2 arrays.


## Visual parity (2026-11-07)

`gui.image_viewer` now matches the fresh-overlay branch of original
`createNewBW2.m`: remove the 4-connected interior of the complemented binary,
suppress its outermost border, dilate by disk radius 1, and combine with the
radius-1 wire. Per-channel zero-value background filling, selected display
channels, custom colors, and the red-only grayscale background follow MATLAB.
Gamma Adjust uses the same per-channel imadjust default: stretchlim at 1%/99%,
strict lower CDF bound and inclusive upper bound, flat-plane fallback, gamma 1,
and uint8 half-up conversion. This is display-only processing.

Wire pixels match MATLAB disk-radius-2 dilation. The Qt canvas draws red filled
branchpoint circles followed by cyan filled endpoint circles, centered on the
saved coordinates, using MATLAB's six-point marker diameter independent of zoom.
Marker raster antialiasing is platform dependent; pixel parity covers image
CData, not Qt-vs-MATLAB window screenshots. Exported image pixels omit marker
objects just as MATLAB's CData-only export does.

221 tests passed. Eight synthetic reference cases are separately preserved in
`tests/fixtures/display_reference.mat`, generated by invoking the unchanged
MATLAB `createNewBW2` function via `tests/matlab/display_reference.m`.
`tools/check_display_parity.py` regenerates these with --snapshot, or adds real
analyses with repeated --analysis arguments. Sixteen cases (synthetic plus
Exp_243 10R_I3 and blind-246 51) matched overlay and wire pixels exactly, with
gamma off/on and default/custom colors. Source/analysis hashes remained unchanged.
Native Windows overlay/wire screenshots were visually checked using copied
analysis data. Evidence: `data/tmp/display_parity/report.json`,
`overlay_preview.png`, and `wire_preview.png`. Existing segmentation and
measurement algorithms and saved originals were not changed.


## Remaining shortcuts and calibration default (2026-11-08)

Added MATLAB's R/G/B channel toggles (retaining one visible channel), Space
previous/current-view swap, and Ctrl+W close with existing unsaved-work guards.
Text editing, brush strokes, disabled wire views, and busy workers are guarded.
The previous view resets on selecting a different image to avoid carrying stale
view history between analyses.

MATLAB's remembered default_image_resolution behavior now uses a per-user Qt INI
preference rather than a MATLAB file in the project. Valid user calibration edits
persist immediately; saved-analysis calibration remains authoritative when loading.
The default is applied only to previously uninitialized image settings, and an
unchanged loaded field never rewrites the default. Invalid stored values use 1.0.
Tests isolate the preference store so they do not alter user defaults.
Validation: the 229-test regression suite passed, followed by the new separate-process persistence test (230 tests total). Tests cover channel/view keyboard events, text focus, close cancellation/discard, invalid stored values, and saved-analysis calibration preservation.

## Final Windows acceptance pass (2026-11-08)

See [the acceptance report](acceptance_2026-11-08.md) for the refreshed real-image
MATLAB comparisons, 232 passing tests, blinded-error fixes, original-file hash
checks, and the remaining platform/distribution validation boundary.
