"""Sequential batch segmentation with per-image atomic saves and recoverable replacement."""
from dataclasses import replace
from pathlib import Path
import shutil
from uuid import uuid4
from reaver.io.images import load_image_state
from reaver.io.results import find_analysis, default_analysis_path, save_analysis
from reaver.io.measurement_export import update_directory_results
from reaver.core.segmentation import segment_image


def process_batch(items, params, channels, cancelled=lambda: False, progress=lambda *args: None):
    """items: (image path, existing analysis path approved for replacement).

    Cancellation finishes the current image. Failure on one image never erases
    prior saves or prevents other images from being processed.
    """
    params = replace(params)
    channels = tuple(channels)
    report = dict(saved=[], skipped=[], failed=[], warnings=[], cancelled=False)
    for index, (source, approved) in enumerate(items):
        if cancelled():
            report['cancelled'] = True
            break
        source = Path(source)
        progress(index, len(items), source.name)
        try:
            current = find_analysis(source)
            if current is not None and (approved is None or current.resolve() != Path(approved).resolve()):
                report['skipped'].append(str(source))
                continue
            state = load_image_state(source)
            state.params = replace(params)
            state.input_channels = state.segmented_channels = channels
            state.derived_layers = segment_image(state.base_image.data, state.params, channels)
            state.image_segmented = state.dirty = True
            # Recheck discovery immediately before writing (a save may have appeared).
            current = find_analysis(source)
            if current is not None and (approved is None or current.resolve() != Path(approved).resolve()):
                report['skipped'].append(str(source))
                continue
            target = default_analysis_path(source)
            if target.exists():
                archive = target.parent/'.reaver-history'
                archive.mkdir(exist_ok=True)
                shutil.copy2(target, archive/(uuid4().hex+'.'+target.name))
            save_analysis(state)
            report['saved'].append(str(source))
            try:
                update_directory_results(state, remove=True)
            except Exception as exc:
                report['warnings'].append(f'{source.name}: saved, but CSV row could not be cleared: {exc}')
        except Exception as exc:
            report['failed'].append(f'{source.name}: {exc}')
    return report
