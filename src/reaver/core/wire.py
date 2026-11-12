"""Wire computation and the edit/update state transition.

Replicated padding and radius r deliberately unify the two MATLAB paths.
"""
from dataclasses import replace
import numpy as np
from scipy import ndimage as ndi
from scipy.ndimage import uniform_filter
from skimage.morphology import dilation, disk
from skimage.measure import label, regionprops
from reaver.app.params import SegmentationParams
from reaver.app.image_state import DerivedLayers
from .morphology import (
    rgb2grey, box_filter_matlab_symmetric, bwareafilt_range,
    bwmorph_bridge, bwmorph_fill, bwmorph_majority, bwmorph_thin_matlab,
    bwmorph_branchpoints_matlab, bwmorph_spur_matlab, bwmorph_clean_matlab,
    bwlookup_matlab, LUT_ENDPOINTS,
)



def compute_wire(binary, params=None):
    """Pure calculation; the returned mask may shrink when dilation is enabled."""
    binary = np.asarray(binary)
    if binary.ndim != 2 or binary.size == 0 or binary.dtype != np.bool_:
        raise ValueError("Expected a nonempty 2-D boolean mask")
    seg_constants = params if params is not None else SegmentationParams()
    for name in ('averaging_filter_size', 'conway_iterations', 'bridge_iterations',
                 'fill_iterations', 'bridge_fill_iterations', 'majority_iterations',
                 'wire_dilation_threshold'):
        value = getattr(seg_constants, name)
        if not isinstance(value, (int, np.integer)) or value < (1 if name == 'averaging_filter_size' else 0):
            raise ValueError(f'{name} must be a nonnegative integer (filter size must be positive)')
    iterations = seg_constants.thin_iterations
    if iterations != np.inf and (not np.isfinite(iterations) or iterations < 0 or iterations != int(iterations)):
        raise ValueError('thin_iterations must be a nonnegative integer or infinity')
    for name in ('grey_to_bw_threshold', 'min_connected_component_area', 'vessel_thickness_threshold'):
        if not np.isfinite(getattr(seg_constants, name)) or getattr(seg_constants, name) < 0:
            raise ValueError(f'{name} must be finite and nonnegative')
    derivedPic = DerivedLayers(bw_2=binary.copy())
    derivedPic.wire = derivedPic.bw_2.copy()
    for _ in range(seg_constants.conway_iterations):
        temp = np.pad(derivedPic.wire, pad_width=1, mode='edge').astype(np.uint8)
        neighbors = temp[1:-1, :-2] + temp[1:-1, 2:] + temp[:-2, 1:-1] + temp[2:, 1:-1] + temp[:-2, :-2] + temp[:-2, 2:] + temp[2:, :-2] + temp[2:, 2:]
        # Survival and birth both accept 4..8; the eight-neighbor count fits
        # in uint8 and the same decision applies regardless of the center.
        derivedPic.wire = neighbors >= 4
    wire = derivedPic.wire.astype(bool)
    for _ in range(seg_constants.bridge_fill_iterations):
        wire = bwmorph_bridge(wire, iterations=seg_constants.bridge_iterations)
        wire = bwmorph_fill(wire, iterations=seg_constants.fill_iterations)
    wire = bwmorph_majority(wire, iterations=seg_constants.majority_iterations)
    wire = wire | bwareafilt_range(~wire, [0, 79])
    pad_size = 48
    basic = np.pad(wire, ((pad_size, pad_size), (pad_size, pad_size)), mode='edge')
    basic = bwmorph_thin_matlab(basic, iterations=seg_constants.thin_iterations)
    wire = basic[pad_size:-pad_size, pad_size:-pad_size]
    derivedPic.wire = wire
    branch_mask = bwmorph_branchpoints_matlab(derivedPic.wire)
    By, Bx = np.nonzero(branch_mask)
    row, col = derivedPic.wire.shape
    branchpoints = np.column_stack([Bx, By])
    offsets = np.array([[0, 0], [1, 1], [-1, -1], [0, 1], [0, -1], [1, 0], [-1, 0], [-1, 1], [1, -1]])
    padded_branchpoints = (branchpoints[:, None, :] + offsets[None, :, :]).reshape(-1, 2)
    in_bounds = (padded_branchpoints[:, 0] >= 0) & (padded_branchpoints[:, 0] < col) & (padded_branchpoints[:, 1] >= 0) & (padded_branchpoints[:, 1] < row)
    padded_branchpoints = padded_branchpoints[in_bounds]
    branchpoint_mask = np.zeros_like(derivedPic.wire, dtype=bool)
    branchpoint_mask[padded_branchpoints[:, 1], padded_branchpoints[:, 0]] = True
    distance = -ndi.distance_transform_edt(derivedPic.bw_2) if np.any(~derivedPic.bw_2) else np.full(derivedPic.bw_2.shape, -np.inf)
    distance[~derivedPic.bw_2] = -np.inf
    vessel_thickness = np.round(derivedPic.wire).astype(np.uint8)
    threshold = seg_constants.vessel_thickness_threshold
    vessel_thickness[derivedPic.wire & (distance > -threshold)] = 2
    vessel_conn_comp_props = derivedPic.wire.copy()
    vessel_conn_comp_props[branchpoint_mask] = False
    labels = label(vessel_conn_comp_props, connectivity=2)
    trimmed_wire = derivedPic.wire.copy()
    for prop in regionprops(labels):
        rr = prop.coords[:, 0]
        cc = prop.coords[:, 1]
        average = vessel_thickness[rr, cc].mean()
        if average > 1.5:
            trimmed_wire[rr, cc] = False
    wire = bwmorph_spur_matlab(trimmed_wire, iterations=1)
    wire = bwmorph_clean_matlab(wire, iterations=1)
    wire = bwmorph_thin_matlab(wire, iterations=seg_constants.thin_iterations)
    derivedPic.wire = wire
    if seg_constants.wire_dilation_threshold > 0:
        footprint = disk(seg_constants.wire_dilation_threshold)
        derivedPic.bw_2 = derivedPic.bw_2 & dilation(derivedPic.wire, footprint=footprint)
    border_size = 5
    row, col = derivedPic.wire.shape
    branch_mask = bwmorph_branchpoints_matlab(derivedPic.wire)
    endpoint_mask = bwlookup_matlab(derivedPic.wire, LUT_ENDPOINTS)
    By, Bx = np.nonzero(branch_mask)
    Ey, Ex = np.nonzero(endpoint_mask)
    keep_branch = (Bx >= border_size - 1) & (Bx <= col - border_size - 1) & (By >= border_size - 1) & (By <= row - border_size - 1)
    keep_end = (Ex >= border_size - 1) & (Ex <= col - border_size - 1) & (Ey >= border_size - 1) & (Ey <= row - border_size - 1)
    Bx = Bx[keep_branch]
    By = By[keep_branch]
    Ex = Ex[keep_end]
    Ey = Ey[keep_end]
    derivedPic.branchpoints = np.column_stack([Bx, By])
    derivedPic.endpoints = np.column_stack([Ex, Ey])
    for points in (derivedPic.branchpoints, derivedPic.endpoints):
        points[:] = points[np.lexsort((points[:, 1], points[:, 0]))]
    derivedPic.dilated_wire = dilation(derivedPic.wire, footprint=disk(1)).astype(np.uint8)
    derivedPic.dilated_wire_2 = dilation(derivedPic.wire, footprint=disk(2)).astype(np.uint8)
    return derivedPic


WIRE_FIELDS = ('bw_2', 'wire', 'branchpoints', 'endpoints', 'dilated_wire', 'dilated_wire_2')


def apply_binary_edit(state, binary):
    """Accept an edited mask and enable exactly one wire update.

    Caller supplies the completed edit; brush rasterization and undo UI are separate.
    A no-op edit does not unlock another update.
    """
    old = state.derived_layers.bw_2
    binary = np.asarray(binary)
    if not state.image_segmented or old is None:
        raise ValueError("Segment the image before editing")
    if binary.dtype != np.bool_ or binary.shape != old.shape:
        raise ValueError("Edited mask must be boolean and retain the image shape")
    if np.array_equal(old, binary):
        return False
    state.derived_layers = replace(state.derived_layers, bw_2=binary.copy(),
        wire=None, branchpoints=None, endpoints=None, dilated_wire=None, dilated_wire_2=None)
    state.wire_update_pending = True
    state.dirty = True
    state.verified = False
    state.metrics.clear()
    state.measurements.clear()
    return True


def update_wire(state, params=None):
    """Consume an edit's pending update only after successful calculation."""
    if not state.image_segmented or not state.wire_update_pending:
        raise ValueError("Update Wire requires a new binary edit")
    result = compute_wire(state.derived_layers.bw_2, params)
    state.derived_layers = replace(state.derived_layers,
        **{name: getattr(result, name) for name in WIRE_FIELDS})
    state.wire_update_pending = False
    state.edit_backup_locked = False
    state.dirty = True
    state.verified = False
    state.metrics.clear()
    state.measurements.clear()
    return state.derived_layers
