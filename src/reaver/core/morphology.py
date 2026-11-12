"""MATLAB-compatible morphology adapted from Richard Doty's prototype."""
from functools import lru_cache
from scipy.linalg import svd
import numpy as np
from scipy import ndimage as ndi
from .morph_luts import (LUT_BRIDGE, LUT_THIN1, LUT_THIN2, LUT_BRANCHPOINTS, LUT_BACKCOUNT4, LUT_DILATE, LUT_SPUR, LUT_CLEAN, LUT_ENDPOINTS)

_LUT_WEIGHTS = np.array(
    [[1,   8,   64],
     [2,   16,  128],
     [4,   32,  256]],
    dtype=np.uint16
)

def make_lut(func):
    lut = np.zeros(512, dtype=bool)

    for idx in range(512):
        bits = ((idx >> np.arange(9)) & 1).astype(bool)

        # MATLAB column-major neighborhood ordering
        nhood = bits.reshape((3, 3), order="F")

        lut[idx] = func(nhood)

    return lut

# def branchpoint_fcn(nhood):
#     if nhood[1, 1]:
#         count = np.sum(nhood) - 1
#         return count > 2
#     return False


# LUT_BRANCHPOINTS = make_lut(branchpoint_fcn)

#%% Functions

def rgb2grey(img, selected_colors=[0,1,2]):
    coefficients = [0.298936021293775, 0.587043074451121, 0.114020904255103]
    grey = np.zeros(img.shape[0:-1])
    for channel in selected_colors:
        grey += (coefficients[channel] * img[:,:,channel])
    return np.round(grey)

@lru_cache(maxsize=16)
def _box_factors(k):
    # MATLAB imfilter separates rank-one kernels via SVD. Preserve that
    # numerical path: mathematically equivalent integral/running sums can
    # flip strict threshold comparisons at floating-point ties.
    u, singular, vh = svd(np.ones((k, k)) / (k * k), lapack_driver="gesvd")
    scale = np.sqrt(singular[0])
    return u[:, 0] * scale, vh[0] * scale


def box_filter_matlab_symmetric(x, k):
    """MATLAB-style separable symmetric box filter, including even alignment."""
    col, row = _box_factors(k)
    origin = -1 if k % 2 == 0 else 0
    result = ndi.correlate1d(np.asarray(x, dtype=float), col[::-1], axis=0,
                             mode="reflect", origin=origin)
    return ndi.correlate1d(result, row[::-1], axis=1, mode="reflect", origin=origin)


def bwareafilt_range(BW, area_range, connectivity=8):
    BW = np.asarray(BW, dtype=bool)
    min_area, max_area = area_range

    if connectivity == 8:
        structure = np.ones((3, 3), dtype=bool)
    elif connectivity == 4:
        structure = ndi.generate_binary_structure(2, 1)
    else:
        raise ValueError("connectivity must be 4 or 8")

    labels, n = ndi.label(BW, structure=structure)

    areas = np.bincount(labels.ravel())
    keep = (areas >= min_area) & (areas <= max_area)
    keep[0] = False  # background

    return keep[labels]

def bwmorph_fill(bw, iterations=1):
    """Fill background pixels whose four cardinal neighbors are foreground."""
    bw = np.asarray(bw, dtype=bool)
    kernel = np.array([[0, 1, 0], [1, 0, 1], [0, 1, 0]], dtype=np.uint8)
    for _ in range(iterations):
        count = ndi.correlate(bw.astype(np.uint8), kernel, mode="constant", cval=0)
        bw = bw | (count == 4)
    return bw


def bwmorph_majority(bw, iterations=1):
    bw = np.asarray(bw, dtype=bool)

    for _ in range(iterations):
        nbrs_3x3 = ndi.convolve(
            bw.astype(np.uint8),
            np.ones((3, 3), dtype=np.uint8),
            mode="constant",
            cval=0
        )

        # includes center pixel
        bw = nbrs_3x3 >= 5

    return bw


def bwmorph_bridge(bw, iterations=1):
    bw = np.asarray(bw, dtype=bool)

    if LUT_BRIDGE.size != 512:
        raise ValueError("Bridge LUT must have 512 entries.")

    # MATLAB neighborhood ordering is column-major:
    #
    # 1 4 7
    # 2 5 8
    # 3 6 9
    #
    weights = np.array(
        [[1,   8,   64],
         [2,   16,  128],
         [4,   32,  256]],
        dtype=np.uint16
    )

    for _ in range(iterations):
        idx = ndi.correlate(
            bw.astype(np.uint16),
            weights,
            mode="constant",
            cval=0
        )

        bw = LUT_BRIDGE[idx]

    return bw

def bwmorph_branchpoints_matlab(bw: np.ndarray) -> np.ndarray:
    bw = np.asarray(bw, dtype=bool)

    # Initial branch point candidates
    C = bwlookup_matlab(bw, LUT_BRANCHPOINTS)

    # Background 4-connected object count
    B = bwlookup_matlab(bw, LUT_BACKCOUNT4)

    # End points: Vp = 1
    E = B == 1

    # Final branch point candidates
    FC = C & ~E

    # Vp = 2 mask
    Vp = (B == 2) & ~E

    # Vq > 2 mask
    Vq = (B > 2) & ~E

    # Dilate Vq
    D = bwlookup_matlab(Vq, LUT_DILATE)

    # Remove candidates where Vp = 2 and adjacent to Vq > 2
    M = (FC & Vp) & D

    # Final branch points
    return FC & ~M

def bwlookup_matlab(bw, lut):
    bw = np.asarray(bw, dtype=bool)
    lut = np.asarray(lut)   # do NOT cast to bool

    if lut.size != 512:
        raise ValueError("Expected a 512-entry LUT.")

    idx = ndi.correlate(
        bw.astype(np.uint16),
        _LUT_WEIGHTS,
        mode="constant",
        cval=0
    )

    return lut[idx]


def bwmorph_thin_matlab(bw, iterations=np.inf):
    bw = np.asarray(bw, dtype=bool)
    if not np.isinf(iterations) and int(iterations) <= 0:
        return bw
    # Both MATLAB thinning tables only delete foreground pixels. Track those
    # pixels instead of evaluating known-false background on every full-image
    # pass. Each subiteration still reads its complete input before any deletion.
    padded = np.pad(bw, 1)
    flat = padded.ravel()
    active = np.flatnonzero(flat)
    stride = padded.shape[1]
    offsets = (-stride-1, -1, stride-1, -stride, 0, stride,
               -stride+1, 1, stride+1)
    count = 0
    while np.isinf(iterations) or count < int(iterations):
        previous_count = active.size
        for lut in (LUT_THIN1, LUT_THIN2):
            # Dense images are cheaper to scan than to gather by coordinates.
            if active.size > flat.size // 4:
                flat[:] = bwlookup_matlab(padded, lut).ravel()
                active = np.flatnonzero(flat)
                continue
            indices = np.zeros(active.size, dtype=np.uint16)
            for bit, offset in enumerate(offsets):
                indices += flat[active + offset] * np.uint16(1 << bit)
            keep = lut[indices]
            flat[active[~keep]] = False
            active = active[keep]
        count += 1
        if active.size == previous_count:
            break
    return padded[1:-1, 1:-1].copy()


def bwmorph_spur_matlab(bw: np.ndarray, iterations: int = 1) -> np.ndarray:
    """
    MATLAB-like bwmorph(..., 'spur') implementation.

    Removes spurs shorter than the specified number of iterations.
    """
    bw = np.asarray(bw, dtype=bool)

    for _ in range(iterations):

        # MATLAB complements first so border handling behaves
        # as if surrounded by foreground.
        bwc = ~bw

        end_points = bwlookup_matlab(bwc, LUT_SPUR)

        # Field 1
        bwc[0::2, 0::2] ^= end_points[0::2, 0::2]

        # Field 2
        new_end_points = end_points & bwlookup_matlab(bwc, LUT_SPUR)
        bwc[0::2, 1::2] ^= new_end_points[0::2, 1::2]

        # Field 3
        new_end_points = end_points & bwlookup_matlab(bwc, LUT_SPUR)
        bwc[1::2, 0::2] ^= new_end_points[1::2, 0::2]

        # Field 4
        new_end_points = end_points & bwlookup_matlab(bwc, LUT_SPUR)
        bwc[1::2, 1::2] ^= new_end_points[1::2, 1::2]

        bw = ~bwc

    return bw


def bwmorph_clean_matlab(bw: np.ndarray, iterations: int = 1) -> np.ndarray:
    bw = np.asarray(bw, dtype=bool)

    for _ in range(iterations):
        bw = bwlookup_matlab(bw, LUT_CLEAN)

    return bw
