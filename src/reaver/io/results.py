"""Compact native analyses and legacy MAT interoperability; saved wires are authoritative."""
from copy import deepcopy
from dataclasses import fields
import hashlib
import io
import json
import zipfile
from uuid import uuid4
import os
from pathlib import Path
import tempfile
import numpy as np
from scipy import ndimage as ndi
from scipy.io import loadmat, savemat
from scipy.sparse import issparse
from skimage.morphology import dilation, disk
from reaver.app.image_state import DerivedLayers
from reaver.app.params import SegmentationParams
from reaver.core.segmentation import initial_layers
from .images import load_image_state

CONSTANTS = dict(averaging_filter_size='averagingFilterSize',
    grey_to_bw_threshold='grey2BWthreshold', min_connected_component_area='minCCArea',
    conway_iterations='ConwaysIterations', bridge_fill_iterations='bridgeFillIterations',
    bridge_iterations='bridgeIterations', fill_iterations='fillIterations',
    majority_iterations='majorityIterations', thin_iterations='thinIterations',
    vessel_thickness_threshold='vesselThicknessThreshold', wire_dilation_threshold='wireDilationThreshold')
IMAGE_SUFFIXES = ('.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp')


def default_analysis_path(image_path):
    path = Path(image_path)
    return path.with_name(path.name + '.reaver')


def find_analysis(image_path):
    path = Path(image_path)
    for candidate in (default_analysis_path(path), path.with_name(path.name+'.reaver.mat'), path.with_suffix('.mat')):
        if candidate.suffix.lower() == '.mat' and deletion_marker(path).exists():
            continue
        if candidate.is_file():
            return candidate
    return None


def image_digest(image):
    return hashlib.sha256(str(image.shape).encode('ascii') + image.tobytes()).hexdigest()


def _read(path):
    try:
        if zipfile.is_zipfile(path):
            return _read_native(path)
        return loadmat(path, simplify_cells=True, mat_dtype=True)
    except NotImplementedError as exc:
        raise ValueError('MATLAB v7.3 files are not supported yet. Save a copy in MATLAB v7 format.') from exc
    except (OSError, ValueError, TypeError, IndexError, EOFError) as exc:
        raise ValueError(f'Could not read analysis: {exc}') from exc


def _array(value, shape, name, binary=False):
    a = value.toarray() if issparse(value) else np.asarray(value)
    squeezed = tuple(n for n in shape if n != 1)
    if a.shape not in (shape, squeezed) or a.dtype.kind not in 'biuf' or not np.isfinite(a).all():
        raise ValueError(f'Invalid {name}: expected a finite array of shape {shape}')
    if binary and not np.isin(a, (0, 1)).all():
        raise ValueError(f'Invalid {name}: expected binary values')
    return a.reshape(shape).astype(bool) if binary else a.reshape(shape).copy()


def _points(value, shape, name):
    a = np.asarray(value)
    if a.size == 0:
        return np.empty((0, 2), dtype=np.int64)
    if a.shape != (2,) and (a.ndim != 2 or a.shape[1] != 2):
        raise ValueError(f'Invalid {name} coordinates')
    if a.dtype.kind not in 'iuf' or not np.isfinite(a).all() or not np.equal(a, np.floor(a)).all():
        raise ValueError(f'Invalid {name} coordinates')
    a = a.reshape(-1, 2)
    if np.any(a < 1) or np.any(a > (shape[1], shape[0])):
        raise ValueError(f'{name} coordinates are outside the image')
    return a.astype(np.int64)-1


def _parameters(data):
    values = data['constants']
    if not isinstance(values, dict):
        raise ValueError('Invalid analysis constants')
    params = SegmentationParams()
    for py, mat in CONSTANTS.items():
        if mat not in values:
            if py in ('vessel_thickness_threshold', 'wire_dilation_threshold'):
                continue  # Same older-file defaults as MATLAB.
            raise ValueError(f'Missing analysis constant: {mat}')
        raw = np.asarray(values[mat])
        if raw.size != 1 or raw.dtype.kind not in 'iuf':
            raise ValueError(f'Invalid analysis constant: {mat}')
        value = float(raw.item())
        integer = py not in ('grey_to_bw_threshold', 'vessel_thickness_threshold', 'thin_iterations')
        if (np.isnan(value) or value < 0 or (not np.isfinite(value) and py != 'thin_iterations')
                or (integer and value != int(value))
                or (py == 'thin_iterations' and np.isfinite(value) and value != int(value))
                or (py == 'averaging_filter_size' and value < 1)):
            raise ValueError(f'Invalid analysis constant: {mat}')
        setattr(params, py, int(value) if integer else value)
    params.image_resolution = float(data.get('image_resolution', 1.0))
    if not np.isfinite(params.image_resolution) or params.image_resolution <= 0:
        raise ValueError('Image resolution must be positive and finite')
    colors = np.asarray(values['selectedColors']).reshape(-1)
    if colors.dtype == np.bool_:
        if colors.size != 3:
            raise ValueError('Invalid selectedColors mask')
        channels = tuple(np.flatnonzero(colors).tolist())
    else:
        if colors.dtype.kind not in 'iuf' or not np.isin(colors, (1,2,3)).all():
            raise ValueError('Invalid selectedColors indices')
        channels = tuple(int(v)-1 for v in colors)
    if len(set(channels)) != len(channels):
        raise ValueError('Duplicate selected channels')
    return params, channels


def _source_path(path, data, explicit):
    if explicit is not None:
        return Path(explicit)
    meta = data.get('reaverPython', {})
    if meta:
        name = str(meta['sourceName'])
        if Path(name).name != name or '/' in name or '\\' in name:
            raise ValueError('Invalid source image name')
        candidates = [path.parent/name, Path(str(meta['sourcePath']))]
    else:
        candidates = [p for p in path.parent.iterdir() if p.stem == path.stem and p.suffix.lower() in IMAGE_SUFFIXES]
        if len(candidates) > 1:
            raise FileNotFoundError('Several matching source images exist. Select the original image.')
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError('Source image not found. Keep the analysis beside its image, or select the original image.')


def load_analysis(path, image_path=None):
    """Load into a new state; failed loads cannot alter an existing GUI analysis."""
    path = Path(path).resolve()
    data = _read(path)
    try:
        params, channels = _parameters(data)
        meta = data.get('reaverPython')
        if meta is not None and (not isinstance(meta, dict) or meta.get('formatVersion') != 1):
            raise ValueError('Unsupported REAVER analysis version')
        source = _source_path(path, data, image_path)
        state = load_image_state(source)
        shape = state.base_image.data.shape[:2]
        if not np.array_equal(np.asarray(data['imageSize']).reshape(-1), shape):
            raise ValueError('The analysis dimensions do not match the source image')
        if meta and meta['imageSha256'] != image_digest(state.base_image.data):
            raise ValueError('The source image differs from the image used for this analysis')
        if state.base_image.n_channels != 1 and not channels:
            raise ValueError('The analysis has no selected input channels')
        saved = data['derivedPic']
        bw = _array(saved['BW_2'], shape, 'BW_2', True)
        wire = _array(saved['wire'], shape, 'wire', True)
        branch = _points(saved['branchpoints'], shape, 'branchpoints')
        ends = _points(saved['endpoints'], shape, 'endpoints')
        if meta and 'reaverLayers' in data:
            # Python extensions preserve the intermediate views bit-for-bit.
            stored = data['reaverLayers']
            layers = DerivedLayers()
            for field in fields(layers):
                if field.name in ('bw_2','wire','branchpoints','endpoints'):
                    continue
                expected = shape
                if field.name == 'selected_channels' and state.base_image.n_channels == 3:
                    expected = (*shape, 3)
                value = _array(stored[field.name], expected, field.name,
                    field.name in ('bw_1','bw_1_neighbors','dilated_wire','dilated_wire_2'))
                # Retain display dilation's uint8 convention.
                if field.name.startswith('dilated_wire'):
                    value = value.astype(np.uint8)
                if field.name == 'bw_1':
                    value = value.astype(np.int64)
                setattr(layers, field.name, value)
        else:
            layers = initial_layers(state.base_image.data, params, channels)
            layers.dilated_wire = dilation(wire, disk(1)).astype(np.uint8)
            layers.dilated_wire_2 = dilation(wire, disk(2)).astype(np.uint8)
        layers.bw_2, layers.wire = bw, wire
        layers.branchpoints, layers.endpoints = branch, ends
        state.derived_layers = layers
        state.image_segmented = True
        state.input_channels = state.segmented_channels = channels
        state.params = params
        state.analysis_path = path
        state.save_path = path if path.suffix.lower() == '.reaver' else None
        state.verified = bool(meta['userVerified']) if meta and 'userVerified' in meta else read_verification(state.path)
        state.undo_layers = deepcopy(layers)
        state.edit_backup_locked = True
        state.metrics = {str(k): float(v) for k,v in data.get('metrics', {}).items()}
        return state
    except (KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise ValueError(f'Invalid or incomplete REAVER analysis: {exc}') from exc


def save_analysis(state, path=None):
    """Save consistent results atomically. State becomes clean only on success."""
    if not state.image_segmented or state.base_image is None or state.params is None:
        raise ValueError('Segment the image before saving an analysis')
    if state.wire_update_pending:
        raise ValueError('Update Wire or Undo before saving the edited analysis')
    path = Path(path) if path is not None else default_analysis_path(state.path)
    path = path.resolve()
    if path.suffix.lower() not in ('.mat', '.reaver') or path == state.path.resolve():
        raise ValueError('Save analyses as a separate .reaver or .mat file')
    digest = image_digest(state.base_image.data)
    if path.exists() and path.suffix.lower() == '.mat':
        raise ValueError('Preserve the original MATLAB / Python MAT file. Choose a new filename.')
    if path.exists():
        prior = _read(path).get('reaverPython', {})
        if (not isinstance(prior, dict) or prior.get('formatVersion') != 1
                or prior.get('imageSha256') != digest or prior.get('sourceName') != state.path.name):
            raise ValueError('This file is an original MATLAB analysis or belongs to another image. Choose a new filename.')
    p = state.params
    constants = {mat: float(getattr(p, py)) for py,mat in CONSTANTS.items()}
    channels = state.segmented_channels
    if channels is None:
        raise ValueError('Missing segmentation channel settings')
    constants.update(selectedColors=np.array([i in channels for i in range(3)], dtype=bool),
                     survive=np.arange(4,9), born=np.arange(4,9))
    layers = state.derived_layers
    derived = dict(BW_2=layers.bw_2, wire=layers.wire,
                   branchpoints=layers.branchpoints+1, endpoints=layers.endpoints+1)
    distance = ndi.distance_transform_edt(layers.bw_2) if np.any(~layers.bw_2) else np.full(layers.bw_2.shape, np.inf)
    # MATLAB bwdist is single precision; logical indexing traverses columns.
    diameters = distance.astype(np.float32).T[layers.wire.T]*np.float32(2)
    diameters = diameters[diameters > 0]
    metrics = dict(vesselLength=int(layers.wire.sum()), vesselArea=int(layers.bw_2.sum()),
        # Preserve MATLAB saveDataButton's max(size(coords)), even for 0/1 rows.
        numBranchPoints=max(layers.branchpoints.shape),
        meanVesselDiam=_matlab_single_mean(diameters))
    data = dict(derivedPic=derived, constants=constants, metrics=metrics,
        image_resolution=p.image_resolution, imageSize=np.array(layers.bw_2.shape),
        imageDirectory=dict(directory=str(state.path.parent), validFiles=np.array([state.path.name],dtype=object)),
        reaverPython=dict(formatVersion=1, sourceName=state.path.name,
                          sourcePath=str(state.path.resolve()), imageSha256=digest, userVerified=bool(state.verified)),
        reaverLayers={f.name: getattr(layers,f.name) for f in fields(layers)
                      if f.name not in ('bw_2','wire','branchpoints','endpoints')})
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.'+path.name+'.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            if path.suffix.lower() == '.reaver':
                _write_native(stream.file, data)
            else:
                savemat(stream.file, data, do_compression=True, oned_as='row')
            stream.flush()
            os.fsync(stream.fileno())
        # Validate a complete temporary file before replacing a previous save.
        load_analysis(temporary, state.path)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    state.analysis_path = path
    state.save_path = path if path.suffix.lower() == '.reaver' else None
    state.metrics = metrics
    state.dirty = False
    return path


def _matlab_single_mean(values):
    """R2024a single-precision accumulation, in linear indexing order.

    Short vectors use a serial sum; longer vectors use four accumulators.
    Saved MATLAB references cover every length through 300 and larger cases.
    """
    values = np.asarray(values, dtype=np.float32).reshape(-1)
    if not values.size:
        return np.float32(np.nan)
    if values.size < 44:
        return np.cumsum(values, dtype=np.float32)[-1]/np.float32(values.size)
    rows = np.pad(values, (0, (-values.size) % 4)).reshape(-1, 4)
    totals = np.cumsum(rows, axis=0, dtype=np.float32)[-1]
    return np.sum(totals, dtype=np.float32)/np.float32(values.size)


def read_verification(image_path):
    """Read MATLAB's table without rewriting it; match whole image names."""
    image_path = Path(image_path)
    table_path = image_path.parent/'User Verified Table.mat'
    if not table_path.exists():
        return False
    table = loadmat(table_path,mat_dtype=True).get('userVerified')
    if table is None or table.ndim != 2 or table.shape[1] != 2:
        raise ValueError('Invalid User Verified Table.mat')
    for name,value in table:
        name = str(np.asarray(name).item())
        if name in (image_path.name, image_path.stem):
            value = np.asarray(value)
            if value.size != 1 or value.item() not in (0,1):
                raise ValueError('Invalid verification flag')
            return bool(value.item())
    return False


def _write_native(stream, data):
    """Portable ZIP: JSON metadata plus lossless numeric NPY arrays; no pickle."""
    constants = {k: (v.tolist() if isinstance(v, np.ndarray) else v)
                 for k, v in data['constants'].items()}
    if np.isinf(constants['thinIterations']):
        constants['thinIterations'] = 'Inf'
    manifest = dict(format='REAVER', version=1, algorithm='matlab-parity-replicate-r1',
        reaverPython=data['reaverPython'], constants=constants,
        image_resolution=data['image_resolution'], imageSize=data['imageSize'].tolist())
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', json.dumps(manifest, allow_nan=False))
        for name, value in data['derivedPic'].items():
            buffer = io.BytesIO()
            np.save(buffer, value, allow_pickle=False)
            archive.writestr(name+'.npy', buffer.getvalue())


def _manifest(path):
    with zipfile.ZipFile(path) as archive:
        value = json.loads(archive.read('manifest.json'))
    if value.get('format') != 'REAVER' or value.get('version') != 1:
        raise ValueError('Unsupported REAVER analysis version')
    if type(value.get('reaverPython', {}).get('userVerified')) is not bool:
        raise ValueError('Invalid verification flag')
    return value


def _read_native(path):
    try:
        data = _manifest(path)
        if data['constants']['thinIterations'] == 'Inf':
            data['constants']['thinIterations'] = np.inf
        colors = data['constants']['selectedColors']
        if not isinstance(colors, list) or len(colors) != 3 or any(type(c) is not bool for c in colors):
            raise ValueError('Invalid selectedColors mask')
        data['constants']['selectedColors'] = np.asarray(colors, dtype=bool)
        with zipfile.ZipFile(path) as archive:
            data['derivedPic'] = {name: np.load(io.BytesIO(archive.read(name+'.npy')), allow_pickle=False)
                for name in ('BW_2', 'wire', 'branchpoints', 'endpoints')}
        return data
    except (KeyError, zipfile.BadZipFile, UnicodeError, TypeError) as exc:
        raise ValueError(f'Invalid REAVER archive: {exc}') from exc


def analysis_verified(path, image_path):
    """Read status without loading source pixels or regenerating display layers."""
    path = Path(path)
    if zipfile.is_zipfile(path):
        meta = _manifest(path)['reaverPython']
    else:
        meta = loadmat(path, simplify_cells=True, variable_names=['reaverPython']).get('reaverPython', {})
    return bool(meta['userVerified']) if 'userVerified' in meta else read_verification(image_path)


def deletion_marker(image_path):
    path = Path(image_path)
    return path.with_name(path.name+'.reaver.deleted')


def remove_saved_analysis(state):
    """Recoverable removal. Legacy MAT originals remain untouched and undiscovered."""
    path = state.analysis_path or find_analysis(state.path)
    if path is None:
        raise ValueError('No saved analysis to remove')
    path = Path(path).resolve()
    # Validate ownership before moving any file, including an explicitly opened save.
    load_analysis(path, state.path)
    marker = deletion_marker(state.path)
    native_paths = {p for p in (path, default_analysis_path(state.path).resolve())
                    if p.suffix.lower() == '.reaver' and p.exists()}
    for native in native_paths:
        load_analysis(native, state.path)
    previous = marker.read_bytes() if marker.exists() else None
    moved = []
    try:
        marker.write_text('Legacy analyses hidden after removal in REAVER. Delete this marker to rediscover them.\n', encoding='utf-8')
        for native in native_paths:
            folder = native.parent/'.reaver-trash'
            folder.mkdir(exist_ok=True)
            destination = folder/(uuid4().hex+'.'+native.name)
            native.rename(destination)
            moved.append((native, destination))
    except Exception:
        for original, archived in reversed(moved):
            archived.rename(original)
        if previous is None:
            marker.unlink(missing_ok=True)
        else:
            marker.write_bytes(previous)
        raise
    return [archived for _, archived in moved]
