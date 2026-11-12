# MATLAB fidelity acceptance pass — 2026-11-08

The tested Windows development build passes the sampled MATLAB fidelity and
workflow checks. This is acceptance of the current desktop implementation on
Windows with MATLAB R2024a references, not certification of standalone packaging,
macOS, every possible image, or a complete manual replay of the original MATLAB
GUI. MATLAB algorithm/renderer functions were invoked independently through the
reference harnesses; Python workflows were exercised through native Qt controls
and mouse/keyboard events.

## Samples and results

Research inputs were copied into isolated working directories. The real sample
was Exp_243 `10R_I1.ids.tif`, `10R_I3.ids.tif`, and blind-246 `51.tif`, with
`example_rgb.tif` added for editing. No original was used as an output target.

| Check | Result |
| --- | --- |
| Full regression suite | 232 passed |
| Initial segmentation | All 3 real images and 8 synthetic cases passed MATLAB comparisons; final arrays and point coordinates exact, local means within the established 2e-12 tolerance |
| Native editing workflow | Zoom/pan, brush strokes, undo/replay, one-update rule, wire views and fit passed on 4 images |
| MATLAB editing comparison | Every recorded brush mask, updated binary, wire, display dilation and point coordinate matched; both zero and positive wire-dilation settings exercised |
| Saving/reopening | 3 real analyses preserved all layers and edited results; verification, discard, removal and directory CSV workflows passed |
| Network measurements | 816 real segment paths, radii and endpoint classifications matched exactly; all 12 summary values had zero absolute difference on these 3 edited analyses |
| Measurement edge cases | Synthetic cases include empty/no-branchpoint inputs, short segments, disconnected structures, loops and borders; inherited MATLAB failures remain explicit |
| Batch processing | Default skipped saved work; confirmed replacement archived earlier native saves; 3 real results matched individual processing exactly |
| Blinded review | Correct image identities retained through shuffling, saving and verification; native GUI screenshot and injected errors checked |
| Display | 16 synthetic/real overlay and wire pixel cases matched MATLAB exactly, including gamma off/on and default/custom colors |
| Image export | 18 real full-resolution TIFF exports across 6 display modes reopened with exact pixels; saved binary TIFF regression coverage retained |
| Preservation | 23 original source/image/analysis hashes checked and unchanged; original MATLAB checkout remains clean |

The Update Wire reference uses the previously approved replicate padding and
single dilation radius on a copied MATLAB function. Those intentional corrections
remain separate from the untouched original source.

## Gaps fixed

1. Error dialogs could expose original filenames during blinded review. Load,
   save, segmentation, wire, measurement/export, discard and removal errors now
   hide dynamic details in blinded mode. CSV cleanup warnings preserve their
   success/failure context while hiding identifying details. Full diagnostic
   messages remain available when blinding is disabled and the operation retried.
2. The source-statistics Save dialog disclosed the original filename. That
   filename-bearing dialog now requires leaving blinded review. Normal TIFF and
   analysis exports continue working in blinded review with anonymous progress.
3. A failed image load could leave a different row selected from the image still
   visible on the canvas. Failure now restores the previous active selection (or
   clears selection when no image is active), without changing cached work.
4. The editing acceptance driver still changed proposed wire settings immediately
   before Update Wire. It now sets the parameter before segmentation, matching
   the implemented distinction between proposed and result settings.

## Boundaries retained

- Original filenames remain in saved analyses and CSV/TIFF exports. Blinded
  review is a UI review aid, not an anonymized dataset or security boundary.
  Choosing a directory necessarily exposes its filesystem names.
- MATLAB's no-branchpoint network measurement failure remains explicit. No new
  measurement definition was introduced to hide that failure.
- Marker locations/colors/sizes follow MATLAB; Qt antialiasing can differ.
- The macOS runtime, packaged executables, installers, signing and clean-machine
  installation remain release-validation work.

## Evidence and repeatability

Primary evidence is under ignored `data/tmp/acceptance_20261108/`:
`summary.json`, `original_hashes.json`, `segmentation/report.json`,
`editing/report.json`, `measurements/comparison.json`, `review/report.json`,
`review/blinded_review.png`, and copies of the native/batch/display reports.
The summary records exact paths to the original reports.

Reusable drivers: `check_matlab_parity.py`, `check_gui_editing.py` (now accepts
`--output`), `check_native_workflow.py`, `generate_measurement_reference.py`,
`check_measurement_parity.py`, `check_batch_workflow.py`,
`check_review_acceptance.py`, and `check_display_parity.py` under `tools/`.
Saved fixtures and the original MATLAB/prototype implementations were preserved.
