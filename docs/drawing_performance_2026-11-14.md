# Drawing cache pass — 2026-11-14

The brush rasterizer, interpolation, mask mutation, undo semantics and wire
algorithms are unchanged. Rendering now caches automatic contrast and dilated
wire arrays between brush segments. The cache holds source references, replaces
entries when those arrays change, and is cleared on every non-brush refresh.
Unneeded original-channel background copies are no longer made for other views.

The first changed segment still updates controls, verification/dirty indicators,
measurements and status. Further segments while Update Wire is pending refresh
the display without repeatedly rebuilding that unchanged interface state.

## Measurements

Two copied real RGB analyses, both 1024 x 1024, native Qt window, brush setting
4 (seven-pixel square), 40 alternating draw/erase segments after a first edit.
Each timing includes Qt event processing. cProfile was enabled in both runs;
these are same-machine diagnostic timings, not mouse-to-screen latency or a
guarantee of performance on other hardware.

| View | Image A before / after | Image B before / after |
| --- | --- | --- |
| Overlay | 75.1 / 58.2 ms | 86.8 / 57.2 ms |
| Overlay, Gamma Adjust | 133.2 / 57.1 ms | 123.9 / 56.6 ms |
| Binary mask | 13.4 / 5.0 ms | 11.4 / 5.0 ms |

First edits still pay for the undo snapshot, cache population and control state
transition. Subsequent profiles contain no repeated contrast calculation or
saved-file/measurement refresh. Full-image edge calculation and overlay color
composition remain the dominant cost; regional rendering is not part of this pass.

## Validation

- 241 regression tests passed, including cached/uncached synthetic display
  equivalence, replaced input arrays and GUI state transition checks.
- Compared against the committed pre-change renderer and brush code on both
  copied real analyses: 18 segments each, brush settings 1/4/16, draw/erase,
  image borders, contrast/channel/color changes and undo. All derived arrays
  and rendered pixels matched exactly.
- Real source image/analysis hashes unchanged; MATLAB originals untouched.
- Local evidence remains ignored in `data/tmp/drawing_profile_20261114/` and
  `data/tmp/drawing_profile_20261114_cached/`, including profiles, JSON timings
  and `equivalence.json`. Research images are not committed.

This validates the source application. The earlier Windows ZIP has not been
rebuilt as part of this source-only performance pass.

## Regional rendering follow-up

Subsequent brush segments now replace only the affected portion of the display
array. The conservative endpoint rectangle includes brush radius, rounding
allowance and the two-pixel reach of boundary erosion followed by dilation.
An additional two-pixel input margin makes patch-edge calculations identical
to full-image rendering. Only the real image border is suppressed. The original
brush rasterizer and its 50 interpolation samples remain unchanged.

The first changed segment and non-brush actions still perform a full refresh.
Color/channel/contrast/view changes, image switches, Update Wire and undo therefore
rebuild the display and caches. The complete display array stays current for
TIFF export. Qt pixmap conversion and canvas painting still use the full image;
this pass reduces overlay computation, not the Qt paint region.

The same two images and 40-segment profile produced these median timings:

| View | Image A cached / regional | Image B cached / regional |
| --- | --- | --- |
| Overlay | 58.2 / 5.45 ms | 57.2 / 5.22 ms |
| Overlay, Gamma Adjust | 57.1 / 4.84 ms | 56.6 / 5.11 ms |
| Binary mask | 4.96 / 3.85 ms | 5.03 / 3.96 ms |

The first overlay edit remained approximately 93–133 ms, including full rendering,
undo backup and interface updates. Long image-spanning strokes can still require
an image-sized patch. These figures describe continuing short strokes rather
than a guaranteed frame rate or end-to-end input latency.

Validation: 262 tests passed. Regional/full comparisons cover randomized paths,
all brush sizes, repeated no-op edits, fractional/outside coordinates, image
borders, tiny grayscale inputs, custom colors and contrast. GUI tests cover
settings/view/image transitions, Update Wire and undo.

`tools/check_regional_drawing.py` additionally compared the GUI with the committed
pre-regional implementation (`91ca257`) on copied real analyses: 72 edited states
per image, four TIFF exports per image, then Update Wire and undo. All derived
arrays and display pixels matched exactly; source hashes remained unchanged.
Evidence is under ignored `data/tmp/regional_drawing_equivalence_20261114/`
and `data/tmp/drawing_profile_20261114_regional/`. The earlier Windows ZIP is
unchanged; no release or standalone rebuild was performed in this pass.
