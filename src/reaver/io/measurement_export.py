"""CSV export matching reaver_quantify_network's field names and ordering."""
import csv
import os
from pathlib import Path
import tempfile
import numpy as np
from reaver.core.metrics import METRIC_LABELS, measure_state, MeasurementError
from .results import load_analysis

COLUMNS = ('image_name', *METRIC_LABELS)


def measurement_row(state):
    if state.dirty or state.analysis_path is None:
        raise MeasurementError('Save the current analysis before exporting results')
    result = measure_state(state)
    return dict(image_name=state.path.name, **result.metrics)


def write_results_csv(path, rows):
    path = Path(path)
    if path.suffix.lower() != '.csv':
        raise ValueError('Analysis results must be saved to a separate .csv file')
    # Validate all rows before opening any output file.
    for row in rows:
        if set(row) != set(COLUMNS):
            raise ValueError('Incomplete measurement row')
    def cell(value):
        if isinstance(value,str):return value
        if np.isnan(value):return 'NaN'
        if np.isposinf(value):return 'Inf'
        if np.isneginf(value):return '-Inf'
        return format(value,'.17g')
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',newline='',dir=path.parent,
                prefix='.'+path.name+'.',suffix='.tmp',delete=False) as stream:
            temp = Path(stream.name)
            writer = csv.DictWriter(stream,fieldnames=COLUMNS)
            writer.writeheader()
            for row in rows:writer.writerow({k:cell(row[k]) for k in COLUMNS})
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if temp is not None:temp.unlink(missing_ok=True)
    return path


def export_saved_analyses(items,path,verified_only=True,progress=None):
    """Load one image at a time. Failure leaves the previous CSV untouched."""
    rows = []
    for index,(analysis,source) in enumerate(items):
        if progress:progress(index,len(items),Path(source).name)
        state = load_analysis(analysis,source)
        if verified_only and not state.verified:
            continue
        try:
            rows.append(measurement_row(state))
        except MeasurementError as exc:
            raise MeasurementError(f'{state.path.name}: {exc}') from exc
    read_results_csv(path)  # Refuse to overwrite an unrelated CSV.
    write_results_csv(path,rows)
    return rows


def directory_results_path(directory):
    directory = Path(directory)
    return directory/(directory.name+'.csv')


def read_results_csv(path):
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise ValueError(f'{path.name} is not a REAVER results CSV; it was left unchanged.')
        rows = []
        for row in reader:
            if set(row) != set(COLUMNS) or any(v is None for v in row.values()):
                raise ValueError(f'Invalid results row in {path.name}')
            rows.append(dict(image_name=row['image_name'], **{k: float(row[k]) for k in METRIC_LABELS}))
        return rows


def update_directory_results(state, metrics=None, remove=False):
    """Upsert one image's row; retain other images and MATLAB column ordering."""
    path = directory_results_path(state.path.parent)
    if remove and not path.exists():
        return path
    rows = read_results_csv(path)
    aliases = {state.path.name, state.path.stem+'.mat', state.path.name+'.reaver.mat', state.path.name+'.reaver'}
    if state.analysis_path:
        aliases.add(state.analysis_path.name)
    rows = [r for r in rows if r['image_name'] not in aliases]
    if not remove:
        if state.dirty or state.wire_update_pending or state.analysis_path is None:
            raise MeasurementError('Save the current analysis before exporting results')
        rows.append(dict(image_name=state.path.name, **(metrics if metrics is not None else measure_state(state).metrics)))
    return write_results_csv(path, sorted(rows, key=lambda r: r['image_name']))
