"""Faithful port of public_REAVER/Network Quantification (R2024a behavior).

Unusual legacy definitions are intentional. See docs/matlab_parity.md.
"""
from dataclasses import dataclass
import numpy as np
from scipy import ndimage as ndi
from .morphology import bwlookup_matlab, LUT_ENDPOINTS, bwareafilt_range

METRIC_LABELS = {
    'fov_um': 'Field of view (µm)', 'umppix': 'Resolution (µm/pixel)',
    'vessel_area_fraction': 'Vessel area fraction', 'vessel_length_um': 'Vessel length (µm)',
    'vessel_length_density_mmpmm2': 'Vessel length density (mm/mm²)',
    'branchpoint_count': 'Branchpoint count', 'segment_count': 'Segment count',
    'mean_segment_length_um': 'Mean segment length (µm)', 'mean_tortuosity': 'Tortuosity',
    'mean_valency': 'Valency', 'mean_segment_diam_um': 'Mean segment diameter (µm)',
    'max_diffusion_dist_um': 'Mean maximum diffusion distance (µm)',
}


class MeasurementError(ValueError):
    pass


@dataclass
class NetworkMeasurements:
    metrics: dict
    segments: list  # zero-based row/column coordinates, including repeat visits
    tortuosity: np.ndarray
    radii: np.ndarray
    endpoint_segments: np.ndarray


def trace_boundary(wire):
    """bwtraceboundary(wire, first column-major pixel, 'W'), 8-connected CW."""
    wire = np.asarray(wire, dtype=bool)
    locations = np.flatnonzero(wire.T)
    if not locations.size:
        return np.empty((0, 2), dtype=np.int64)
    col, row = divmod(int(locations[0]), wire.shape[0])
    start = (row+1, col+1)
    padded = np.pad(wire, 1)
    offsets = ((-1,0),(-1,1),(0,1),(1,1),(1,0),(1,-1),(0,-1),(-1,-1))
    current, search, first_next = start, 6, None
    trace = [start]
    # A boundary can visit a pixel multiple times, but has only 8 directed edges.
    for _ in range(8*locations.size+1):
        found = False
        for advance in range(8):
            direction = (search+advance)%8
            dr,dc = offsets[direction]
            neighbor = (current[0]+dr,current[1]+dc)
            if padded[neighbor]:
                found = True
                break
        if not found:
            break
        if first_next is None:
            first_next = neighbor
        elif current == start and neighbor == first_next:
            break
        trace.append(neighbor)
        current = neighbor
        search = (direction + (6 if direction%2 == 0 else 5))%8
    else:
        raise MeasurementError('Boundary tracing did not close')
    return np.asarray(trace,dtype=np.int64)-1


def skeleton_segments(wire, branchpoints, endpoints):
    """Port skel_2_linesegs; point inputs use zero-based (x,y)."""
    wire = np.asarray(wire,dtype=bool)
    branchpoints = np.asarray(branchpoints,dtype=np.int64).reshape(-1,2)
    endpoints = np.asarray(endpoints,dtype=np.int64).reshape(-1,2)
    if not len(branchpoints):
        # MATLAB's zero-pass loop creates a numeric [] then fails in cellfun.
        raise MeasurementError('MATLAB network measurements are undefined for an analysis with no branchpoints (legacy segment-tracing error).')
    border = np.zeros(wire.shape,bool)
    border[0,:] = border[-1,:] = border[:,0] = border[:,-1] = True
    points_mask = bwlookup_matlab(wire,LUT_ENDPOINTS) & border
    for points in (branchpoints,endpoints):
        points_mask[points[:,1],points[:,0]] = True
    remaining = wire.copy()
    segments = []
    # R2024a evaluates 1:size(rc_bp.^2) using the first size entry (BP count).
    for _ in range(len(branchpoints)):
        if not remaining.any():
            break
        trace = trace_boundary(remaining)
        indices = np.flatnonzero(points_mask[trace[:,0],trace[:,1]])
        for first,last in zip(indices[:-1],indices[1:]):
            if last-first+1 > 5:
                segments.append(trace[first:last+1].copy())
        remaining[trace[:,0],trace[:,1]] = False
        remaining = bwareafilt_range(remaining | points_mask, [2,np.inf])
    return segments


def _mean(values):
    return float(np.mean(values)) if len(values) else float('nan')


def quantify_network(binary, wire, branchpoints, endpoints, resolution=1.0):
    """Compute all 12 MATLAB network fields without modifying any input."""
    binary,wire = np.asarray(binary),np.asarray(wire)
    if (binary.dtype != np.bool_ or wire.dtype != np.bool_ or binary.ndim != 2
            or not binary.size or binary.shape != wire.shape):
        raise MeasurementError('Measurements require matching nonempty 2-D binary and wire masks')
    if not np.isfinite(resolution) or resolution <= 0:
        raise MeasurementError('Image resolution must be positive and finite')
    points = []
    for value in (branchpoints,endpoints):
        value = np.asarray(value)
        if value.ndim != 2 or value.shape[1] != 2 or value.dtype.kind not in 'iu':
            raise MeasurementError('Expected integer (x,y) point arrays')
        if np.any(value < 0) or np.any(value >= (wire.shape[1],wire.shape[0])):
            raise MeasurementError('Point coordinates lie outside the image')
        points.append(value)
    branchpoints,endpoints = points
    segments = skeleton_segments(wire,branchpoints,endpoints)
    fov_um = resolution*binary.shape[0]
    fov_mm = fov_um/1000
    length = int(np.count_nonzero(wire))
    tortuosity = []
    for segment in segments:
        distance = np.sqrt(np.sum(np.abs(segment[0]-segment[-1]).astype(float)**2))
        if distance >= 5:
            tortuosity.append(segment.size/distance)  # MATLAB numel(N-by-2), not N.
    from reaver.io.results import _matlab_single_mean
    distance = (ndi.distance_transform_edt(binary).astype(np.float32)
                if np.any(~binary) else np.full(binary.shape,np.inf,dtype=np.float32))
    radii = np.array([float(_matlab_single_mean(distance[s[:,0],s[:,1]])) for s in segments])
    ep_set = set(map(tuple,endpoints[:,::-1]))
    endpoint_segments = np.array([tuple(s[0]) in ep_set or tuple(s[-1]) in ep_set for s in segments],bool)
    diffusion = (ndi.distance_transform_edt(~binary).astype(np.float32)
                 if binary.any() else np.full(binary.shape,np.inf,dtype=np.float32))
    labels,n = ndi.label(diffusion != 0,structure=np.ones((3,3),bool))
    maxima = ndi.maximum(diffusion,labels,np.arange(1,n+1)).astype(float) if n else np.array([])
    metrics = dict(fov_um=fov_um, umppix=resolution,
        vessel_area_fraction=float(binary.sum())/binary.size,
        vessel_length_um=length*(fov_um/binary.shape[0]),
        vessel_length_density_mmpmm2=length*(fov_mm/binary.shape[0])/(fov_mm**2),
        branchpoint_count=len(branchpoints),segment_count=len(segments),
        mean_segment_length_um=_mean([len(s) for s in segments])*resolution,
        mean_tortuosity=_mean(tortuosity),
        mean_valency=len(branchpoints)/len(segments) if segments else float('inf'),
        mean_segment_diam_um=_mean(2*radii+1)*(fov_um/binary.shape[0]),
        max_diffusion_dist_um=_mean(maxima)*resolution)
    return NetworkMeasurements(metrics,segments,np.asarray(tortuosity),radii,endpoint_segments)


def measure_state(state):
    if not state.image_segmented or state.wire_update_pending or state.params is None:
        raise MeasurementError('Segment the image and Update Wire before measuring or exporting')
    d = state.derived_layers
    return quantify_network(d.bw_2,d.wire,d.branchpoints,d.endpoints,state.params.image_resolution)
