"""Automatic segmentation matching the MATLAB GUI's segmentImage.m path.

Inputs are uint8 grayscale or channel-last RGB; coordinates are zero-based
(x, y). Display settings never affect the chosen segmentation channels.
"""
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


def initial_layers(image, params=None, channels=(0,)) -> DerivedLayers:
    """Reconstruct only the display layers MATLAB rebuilds when reopening."""
    basePic = np.asarray(image)
    if basePic.dtype != np.uint8:
        raise ValueError("segment_image expects uint8 data; use load_image_state for files")
    if basePic.ndim == 3 and basePic.shape[2] == 1:
        basePic = basePic[:, :, 0]
    if basePic.ndim not in (2, 3) or (basePic.ndim == 3 and basePic.shape[2] != 3):
        raise ValueError("Expected a grayscale or channel-last RGB image")
    if not basePic.size:
        raise ValueError("Image must not be empty")
    channels = tuple(channels)
    if any(c not in (0, 1, 2) for c in channels) or len(set(channels)) != len(channels):
        raise ValueError("channels must contain unique indices from 0, 1, 2")
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
    selected = basePic.copy()
    if selected.ndim == 3:
        selected[:, :, [c for c in range(3) if c not in channels]] = 0
    grey = basePic.astype(float) if basePic.ndim == 2 else rgb2grey(basePic, selected_colors=channels)
    g = np.pad(grey, pad_width=1, mode='edge')
    greynbrs = (g[1:-1, :-2] + g[1:-1, 2:] + g[:-2, 1:-1] + g[2:, 1:-1] + g[:-2, :-2] + g[:-2, 2:] + g[2:, :-2] + g[2:, 2:]) / (255 * 8)
    derivedPic = DerivedLayers(selected_channels=selected, gray=grey)
    derivedPic.gray_neighbors = greynbrs
    derivedPic.local_mean = 0.4 * box_filter_matlab_symmetric(derivedPic.gray_neighbors, seg_constants.averaging_filter_size)
    derivedPic.bw_1 = (derivedPic.gray_neighbors - derivedPic.local_mean > seg_constants.grey_to_bw_threshold).astype(int)
    g = np.pad(derivedPic.bw_1, pad_width=1, mode='edge')
    derivedPic.bw_1_neighbors = g[1:-1, :-2] + g[1:-1, 2:] + g[:-2, 1:-1] + g[2:, 1:-1] + g[:-2, :-2] + g[:-2, 2:] + g[2:, :-2] + g[2:, 2:] > 3
    return derivedPic


def segment_image(image, params=None, channels=(0,)) -> DerivedLayers:
    """Return derived layers without modifying the image or parameter object."""
    seg_constants = params if params is not None else SegmentationParams()
    derivedPic = initial_layers(image, seg_constants, channels)
    derivedPic.bw_2 = bwareafilt_range(derivedPic.bw_1_neighbors, [seg_constants.min_connected_component_area, np.inf])
    bw_2inv_base = ~derivedPic.bw_2.copy()
    bw_2inv = np.pad(bw_2inv_base, (50, 50), mode='edge')
    blurryImage = uniform_filter(bw_2inv.astype(np.float32), size=11, mode='constant')
    bw_2inv = blurryImage > 0.5
    bw_2inv = bw_2inv[50:-50, 50:-50]
    temp = ~bw_2inv
    bw_2inv = ~temp.copy()
    bw_2inv = np.pad(bw_2inv, (50, 50), mode='edge')
    bw_2inv = bw_2inv & bwareafilt_range(bw_2inv, [0, 800])
    bw_2inv = bw_2inv[50:-50, 50:-50]
    derivedPic.bw_2 = temp | bw_2inv
    bw_2 = np.pad(derivedPic.bw_2, (50, 50), mode='edge')
    bw_2 = bwmorph_thin_matlab(bw_2, iterations=2)
    derivedPic.bw_2 = bw_2[50:-50, 50:-50]
    derivedPic.bw_2 = bwareafilt_range(derivedPic.bw_2, [seg_constants.min_connected_component_area, np.inf])
    from .wire import compute_wire, WIRE_FIELDS
    result = compute_wire(derivedPic.bw_2, seg_constants)
    for name in WIRE_FIELDS:
        setattr(derivedPic, name, getattr(result, name))
    return derivedPic
