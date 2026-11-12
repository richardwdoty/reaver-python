# Windows portable preview acceptance — 2026-11-12

Built with Python 3.12.7, PyInstaller 6.22.3 and the pinned dependencies in
`packaging/windows-requirements.txt`. The portable ZIP includes Python,
Qt, scientific libraries, licenses, instructions and a SHA-256 sidecar.

Validation:

- Full regression suite: 232 passed.
- Normal windowed executable startup inspected through Windows accessibility.
- Final ZIP extracted to a separate path containing spaces and a Unicode
  character; child PATH contained only Windows System32, with Python and Qt
  development environment variables removed.
- Two real analyses from the Exp_243 and blind-246 collections were copied
  for testing. Segmentation/binary and wire hashes matched the source run.
- Save/reopen, verified identities during randomized blinded review, hidden
  errors, gamma/view switching, zoom and twelve TIFF display exports passed.
- Source image/analysis hashes remained unchanged. MATLAB checkout remained
  untouched. No research images or temporary outputs are included in Git.

The first isolated test exposed an omitted Conda libffi dependency. The spec
now includes that runtime when building from a Conda-derived environment.
Clean builds are mandatory to avoid stale cached acceptance code.

Evidence is local under ignored `data/tmp/windows_source_20261112/` and
`data/tmp/Windows portable test µ final/results/`. Repeat with
`tools/check_windows_package.py`, supplying the ZIP, analyses, fresh output
directory and the source report as baseline.

This is an unsigned Windows preview, tested on the development computer with
its Python search paths removed. A genuinely clean Windows machine, downloaded
file security prompts, installer/signing and macOS have not been validated.
The GitHub Actions build recipe is provided but has not been executed here.
No public release asset has been published by this change; the local ZIP is
under `dist/REAVER-Windows-x64.zip` and can be distributed separately.
