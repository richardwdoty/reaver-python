# Prototype GUI

Install with `python -m pip install -e ".[test]"`, then run `python -m reaver`.
The Windows development environment also has `.venv/Scripts/reaver.exe`.

1. Choose **File → Open Directory**, then click an image in the list.
2. Select segmentation channels (red by default). Grayscale needs no channel selection.
3. Click **Segment Image**. Replacing existing analysis data requires confirmation;
   cancellation preserves the current work. Processing runs in a background worker; file and
   segmentation controls are locked until it finishes.
4. Choose a display mode: **Original Image**, **Segmentation Input**, **Vessel Mask**,
   **Segmentation Overlay**, or **Wire Frame**. Original Image shows the selected
   display channels; Segmentation Input shows the currently selected segmentation
   channels. Vessel Mask shows white vessel pixels on a black background. Overlay
   adds boundaries and centerlines to the image; Wire Frame shows the centerlines.
   Intermediate processing views are omitted from the selector; their calculations
   and diagnostic renderers are preserved.
5. Display channels affect visualization only. Changing segmentation channels
   requires clicking Segment Image again; the status bar identifies stale results.
6. In **Vessel Mask** or **Segmentation Overlay**, left-drag to add vessel pixels
   and right-drag to erase. Brush settings match MATLAB: 1–16 means a square
   footprint of 1–31 pixels (`2 × setting − 1`), not a circular brush.
7. Choose **Update Wire** (U) after editing. It runs once per changed edit batch;
   another update requires another binary change. While edits are pending, the
   overlay retains the old wire and the dedicated Wire Frame view is disabled.
8. **Undo** (Ctrl+Z) restores the complete pre-edit batch, including its binary,
   wire, and point arrays. It works before or after Update Wire. Multiple strokes
   belong to one batch; this is MATLAB's single backup, not a multi-step history.
   After an update, the next edit starts a new batch. Segment Image resets undo.
9. **Save Analysis** (Ctrl+S) saves the current segmentation and edits once its wire
   is up to date, always as `<image filename>.reaver` beside the image.
10. Use **File → Open Directory**, then select an image to reopen its saved analysis
    automatically. There are no separate Open Analysis or Save Analysis As commands.
11. Set **µm / pixel** under Analysis to the image's calibrated resolution, then
    click **Measure Vessels**. The panel shows area fraction, length/density,
    branchpoints, segments, mean segment length, tortuosity, valency, diameter,
    and diffusion distance, plus calibration metadata.
12. Save the analysis, then use **File → Update Directory CSV with Current Results**.
    It creates or updates the current image's row in `<directory name>.csv` beside
    the images, retaining the other rows. For a directory, mark saved images
    **User verified**, then choose **File → Export All Verified Results to Directory CSV**.
    This rebuilds that same CSV using only verified saved analyses. It retains
    MATLAB's measurement columns and ordering; `image_name` identifies the source
    image, so converting its analysis format does not create a duplicate row.
13. **File → Discard Current Changes…** restores the last saved analysis, or the
    original unsegmented image if there is no save. **Discard All Pending Changes…**
    does this for every pending image. Both ask before discarding work.
14. **File → Remove Saved Analysis…** removes the current saved analysis from
    normal browsing and its row from the directory CSV, and discards pending work
    after confirmation. Native saves move into `.reaver-trash`; original images
    and `.mat` files remain unchanged. A `<image filename>.reaver.deleted` marker
    prevents old MAT data from reopening automatically. Delete that marker to
    rediscover legacy data; an archived native file can be restored
    by copying it back under its original name.

Measurements and exports run in the background. Editing, updating the wire,
undoing, or changing calibration clears displayed measurements; measure again
afterward. Export requires saved, up-to-date analyses. Directory export stops
if cached analyses have unsaved changes, and includes only verified saved images.
No partial CSV replaces an existing export when a calculation or write fails.
Saving changed results removes that image's old CSV row; export again to insert
current measurements. An empty verified set produces a header-only CSV, removing
previously verified rows. An unrelated CSV with a different header is left untouched.
The measurements panel is a calculated view; reopening an analysis requires
clicking Measure Vessels again. Changing resolution scales measurements without
rerunning segmentation, and Save Analysis preserves the new resolution.

The **User verified** checkbox is available after saving. Toggling it immediately
saves the flag in the Python analysis file; importing an original MATLAB analysis
creates a separate Python save. Existing `User Verified Table.mat` entries are
read for older analyses, but that original table is never rewritten. Explicit
Python flags take precedence. A failed verification save restores the prior flag.
A binary edit, resegmentation, Update Wire, Undo, or calibration change clears
verification. Discard restores the saved verification status. Changing display
channels or zoom does not affect verification.

These calculations intentionally follow MATLAB's legacy definitions, including
its nonstandard tortuosity and valency formulas. The network-export diameter is
also different from the older diameter summary in MATLAB-compatible exports.
An analysis with no branchpoints hits a known MATLAB segment-tracing failure:
Python reports it and stops measurement/export, rather than inventing results.
Undefined means from zero surviving segments remain `NaN`; infinite values remain
`Inf` in the panel and CSV. See the measurement section of the parity notes for
the exact definitions and limitations.

Use the mouse wheel to zoom around the pointer, middle-button drag to pan, and
**Fit Image** to restore the whole image. Ctrl+wheel or Up/Down adjusts the brush.
Zoom is retained while editing, updating, undoing, or changing display modes;
selecting an image fits it to the window. The yellow outline shows the brush's
actual footprint. Editing is disabled in source and intermediate-layer views.

Image intensities use the validated loader, with no automatic min/max stretching.
Segmentation results, pending edits, and the undo backup remain cached separately
for each image when switching within the directory.
The overlay follows MATLAB rendering with green outer vessel edges and a white
dilated centerline by default. Wire Frame uses a radius-two dilation with red
branchpoint and cyan endpoint markers.

New saves default to `<image filename>.reaver` beside the source image. These
compact files contain final results and settings, not intermediate image caches
or measurement summaries. Existing Python `.reaver.mat` and MATLAB `.mat` files
remain readable; normal saving converts them into a separate native file. Native
`.reaver` files take precedence during automatic discovery.

**File** is now a dropdown button at the left of the top toolbar. The image list
shows a disk for saved analyses, a checkmark for verified saves, and a warning
symbol for unsaved changes (including pending wire updates). Hover for status
and the save path. These indicators appear before loading an image. Clicking or
using the keyboard to select an image switches to **Segmentation Overlay** when
analysis data exists, or **Original Image** otherwise, and fits the image.
Cached pending work is retained. Image tooltips use a light background and dark text.

Keep the source image with its analysis when moving files. Analyses do not embed
the source image; keep the original image beside its saved analysis. New files check the
image's dimensions and normalized pixel fingerprint to prevent mismatches.
Older MATLAB files have only a dimension check because they contain no fingerprint.

Saving preserves the final binary, wire, points, calibration, segmentation settings,
and verification. Reopening restores saved results without rerunning segmentation
or Update Wire; intermediate display layers are rebuilt from the original image
and saved settings during loading. As in MATLAB, reopening starts a fresh undo history: your edits
are preserved in the binary, but earlier undo snapshots are not saved. Input
channels reopen to those actually used for the saved segmentation.

Closing or changing directories offers **Save**, **Discard**, and **Cancel** for
all unsaved analyses. If any image has pending edits, choose Cancel and Update
Wire or Undo before saving. A failed save leaves the previous file intact and
keeps the analysis marked unsaved. Export Image Statistics, now under File,
remains a separate export of basic source-image statistics.

MATLAB v5/v7 analysis files, including sparse wires and older missing-option
defaults, are supported. MATLAB v7.3 files are not yet supported. Native files use a versioned ZIP archive with JSON metadata and lossless NumPy
arrays, without pickle. The GUI saves only native files. The Python I/O API
retains explicit MAT export for interoperability and parity testing, including
the legacy MATLAB summaries. For automatic discovery
in the original MATLAB GUI, save a copy as `<image stem>.mat` alongside a copy of
the source image in a separate working directory. Existing MAT files cannot be overwritten by this app; choose a new copy filename.

The layout is adapted from the original Box Sync `prototype_GUI.py`; that file
is unchanged. Qt is constrained to the 6.8 series because the initially installed
6.12 runtime failed to load on the development Windows environment. macOS has
not yet been tested.


## Threshold and segmentation settings

The Segmentation panel includes a threshold slider and numeric entry (0–1).
Both follow MATLAB's three-decimal rounding. The slider gives finer steps up to
0.2 and coarser steps above it; numeric entry can select any three-decimal value.
**Segmentation Settings…** exposes averaging filter size, minimum connected-
component area, wire dilation radius, and vessel thickness threshold. Cancel
leaves values unchanged; invalid input is rejected. Pixel sizes/areas/radii must
be whole numbers, with filter size at least 1; thickness may be fractional.

These are proposed settings until **Segment Image** completes successfully.
The panel and status bar identify differences from the current analysis.
Changing a proposal does not invalidate, relabel, or alter existing saved results
or verification. Re-segmenting requires confirmation and clears verification.
Proposals stay with each image while browsing; saved files retain the settings
actually used to produce their results. Reopening restores those saved settings.
**Update Wire** uses the existing analysis settings, not unapplied proposals.

**Used for this result** shows the threshold that generated the current analysis,
including a newly segmented result that has not yet been saved. **Restore** sets
the threshold control back to that value without running segmentation, changing
other proposed settings, discarding brush edits, or altering verification, undo,
wire results or saved files. It is disabled when the threshold already matches,
when there is no segmented result, or while processing. Imported result values
retain their original precision when restored, even if the slider cannot exactly
represent them; the numeric field shows the restored value.


## Batch processing

Choose **File → Batch Process Images…**. The default processes only images with
no saved or in-memory analysis; existing work is skipped. The dialog lists the
current threshold, segmentation settings, channels, and calibration that will
be applied to every selected image. Results save automatically beside their
images as `.reaver` files and start unverified.

Choose **All images** to reprocess the directory. A separate confirmation is
required before replacing existing analyses. Save or discard pending edits first.
Previous native saves are copied to `.reaver-history`; source images and legacy
MAT files remain untouched. The old CSV rows are cleared so subsequent exports
use the new results. A CSV update failure is reported separately from a successful
analysis save.

Progress shows the current image. **Stop after current image** finishes that
image's save and leaves the remaining images untouched. A failed image is reported
and processing continues with the others; completed saves remain available.
The final report lists counts, failures, and any CSV warnings. Successful images
refresh in the list, and the active image reloads its new analysis.


## Blinded review

Enable **File → Blind Image Names** to randomize the image list and display
`Image_001`, `Image_002`, and so on. The same permutation is retained while
switching blinding off/on in a directory session; reopening the directory creates
a new permutation. Turning blinding off restores the original ordering and names.
The active image remains selected during either transition.

Saves, edits, calibration, and verification remain attached to original image
identities. No source files are renamed. Tooltips, status, measurement headings,
and processing progress conceal source names during review. Saved filenames and
exported CSV image names retain original identities, as in MATLAB; exported files
are not anonymized datasets. This is a review aid, not access control.


## Image exports

**File → Export Saved Binary Masks as TIFFs** writes each saved analysis's final
binary mask into `bw/<image stem>.tif`, including unverified analyses, as MATLAB
does. The mask comes directly from the saved file, without segmentation or wire
recalculation. Save or discard pending edits before this directory export.
Binary TIFFs contain one-bit black/white pixels.

**File → Export Displayed Image as TIFF** writes the full-resolution rendered
image beside its source using `<image stem> - <timestamp>.tif`. It includes the
selected display mode and channel visibility. It does not include window controls,
brush cursor, zoom resampling, or a crop of the viewport. Unsaved edits visible
in the current view are included; this export does not save the analysis.

Both exports preserve existing files by adding a numbered suffix on collisions.
Files are validated before publication. Binary export reports individual failures
and retains successful exports. Blinded review hides names in progress/completion
messages, but exported filenames retain original image identities, as in MATLAB.


## Display appearance

The toolbar **Display** menu contains **Gamma Adjust**, **Center Line Color…**,
and **Edge Line Color…**. Gamma Adjust follows MATLAB's overlay-only automatic
per-channel contrast stretch (1%–99%, gamma exponent 1). It does not change source
pixels, segmentation, measurements, saves, or verification. Colors also affect
only the overlay. Defaults are white centerlines and green edges. Grayscale
overlays use MATLAB's red-channel background convention.

Wire Frame shows radius-two-dilated white lines and six-point red/cyan markers
for branchpoints/endpoints. Markers retain their screen size as you zoom, with
positions following pixel centers. They are hidden in other modes. As in MATLAB,
markers are graphics above the image, so TIFF display exports contain the wire
pixels but not point markers. Gamma and colors are session display preferences.


## Keyboard shortcuts and remembered calibration

R/G/B toggle the corresponding display channel for color images; the shortcut
keeps at least one channel visible. Space swaps between the current and previous
view without changing zoom. View history resets when selecting a different image,
and a pending wire update cannot be bypassed to show the disabled wire view.
Character shortcuts do not interfere with typing in numeric/text fields, active
brush strokes, or background processing. Ctrl+W closes the window through the
usual Save/Discard/Cancel protection; processing must finish before closing.

Editing µm/pixel also remembers the value as your default for newly opened,
unprocessed images, including after restarting REAVER. Saved analyses always
restore their own calibration. Merely opening an analysis or leaving its unchanged
calibration field does not change the remembered default. Each open image retains
its chosen calibration while you browse. Calibration changes to existing analyses
still require saving and clear verification/measurements as before.

The default is kept in REAVER's per-user preferences, separate from images and
analysis files. Missing or invalid preferences fall back to 1 µm/pixel. A failed
preference write is reported without preventing calibration of the current image.

During blinded review, error dialogs conceal identifying details. Turn blinding
off and retry for full diagnostics. The source-statistics Save dialog requires
unblinded mode because it exposes original filenames. A failed image load restores
the selection to the image still displayed.
