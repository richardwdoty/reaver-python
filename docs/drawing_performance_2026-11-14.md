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
