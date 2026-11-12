"""Windowed executable entry point, including an isolated acceptance mode."""
import multiprocessing
import sys
import traceback
from pathlib import Path

if __name__ == '__main__':
    multiprocessing.freeze_support()
    if '--acceptance' in sys.argv:
        sys.argv.remove('--acceptance')
        try:
            import check_review_acceptance
            check_review_acceptance.main()
        except Exception:
            # Windowed executables have no console. Put diagnostics in the
            # explicitly supplied test output directory instead.
            output = Path(sys.argv[sys.argv.index('--output') + 1])
            output.mkdir(parents=True, exist_ok=True)
            (output / 'failure.txt').write_text(traceback.format_exc(), encoding='utf-8')
            raise SystemExit(1)
    else:
        from reaver.gui.main_window import main
        raise SystemExit(main())
