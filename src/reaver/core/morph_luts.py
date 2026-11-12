"""
Utilities for generating MATLAB-style 3x3 morphology LUTs.

The LUT indexing follows MATLAB bwlookup/makelut neighborhood order:

    1 4 7
    2 5 8
    3 6 9

which corresponds to Fortran/column-major ordering.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage as ndi


def make_lut_3x3(rule, *, dtype=bool) -> np.ndarray:
    """
    Generate a 512-entry LUT from a 3x3 binary-neighborhood rule.

    Parameters
    ----------
    rule
        Callable accepting a 3x3 boolean ndarray and returning one output value.
    dtype
        Output LUT dtype.

    Returns
    -------
    np.ndarray
        Flat 512-entry LUT compatible with MATLAB-style bwlookup indexing.
    """
    lut = np.empty(512, dtype=dtype)

    for idx in range(512):
        bits = ((idx >> np.arange(9)) & 1).astype(bool)
        nhood = bits.reshape((3, 3), order="F")
        lut[idx] = rule(nhood)

    return lut


def count_components_8(binary_image: np.ndarray) -> int:
    """Count 8-connected foreground components."""
    _, n_components = ndi.label(
        np.asarray(binary_image, dtype=bool),
        structure=np.ones((3, 3), dtype=bool),
    )
    return n_components


def bridge_rule(nhood: np.ndarray) -> bool:
    """
    Rule for MATLAB-like bwmorph(..., 'bridge').

    A center 0-pixel is turned on when doing so connects disconnected
    8-connected foreground components, except for the four two-pixel
    outer-edge pair cases that MATLAB does not bridge.
    """
    nhood = np.asarray(nhood, dtype=bool)

    if nhood[1, 1]:
        return True

    if nhood.sum() == 2:
        excluded_outer_edge_pair = (
            (nhood[0, 0] and nhood[2, 0]) or  # left column
            (nhood[0, 2] and nhood[2, 2]) or  # right column
            (nhood[0, 0] and nhood[0, 2]) or  # top row
            (nhood[2, 0] and nhood[2, 2])     # bottom row
        )

        if excluded_outer_edge_pair:
            return False

    before = nhood.copy()
    before[1, 1] = False

    after = nhood.copy()
    after[1, 1] = True

    return count_components_8(after) < count_components_8(before)


def make_bridge_lut() -> np.ndarray:
    """Generate the MATLAB-like bridge LUT."""
    return make_lut_3x3(bridge_rule, dtype=bool)


def _thin_neighbors_x(nhood: np.ndarray) -> np.ndarray:
    """
    Return neighbors starting at east and moving counter-clockwise:

        x0 = E
        x1 = NE
        x2 = N
        x3 = NW
        x4 = W
        x5 = SW
        x6 = S
        x7 = SE
    """
    return np.array([
        nhood[1, 2],
        nhood[0, 2],
        nhood[0, 1],
        nhood[0, 0],
        nhood[1, 0],
        nhood[2, 0],
        nhood[2, 1],
        nhood[2, 2],
    ], dtype=bool)


def _compute_g1(x: np.ndarray) -> bool:
    two_i = np.array([1, 3, 5, 7])      # MATLAB x(2), x(4), x(6), x(8)
    two_i_minus_1 = np.array([0, 2, 4, 6])
    two_i_plus_1 = np.array([2, 4, 6, 0])  # MATLAB mod(twoi + 1, 8), with 0 -> 8

    b = ~x[two_i_minus_1] & (x[two_i] | x[two_i_plus_1])
    return np.sum(b) == 1


def _compute_g2(x: np.ndarray) -> bool:
    two_i = np.array([1, 3, 5, 7])
    two_i_minus_1 = np.array([0, 2, 4, 6])
    two_i_plus_1 = np.array([2, 4, 6, 0])

    n1 = np.sum(x[two_i_minus_1] | x[two_i])
    n2 = np.sum(x[two_i] | x[two_i_plus_1])

    return min(n1, n2) in (2, 3)


def _compute_g3(x: np.ndarray) -> bool:
    return not ((x[1] or x[2] or (not x[7])) and x[0])


def _compute_g3_prime(x: np.ndarray) -> bool:
    return not ((x[5] or x[6] or (not x[3])) and x[4])


def thin_iter1_rule(nhood: np.ndarray) -> bool:
    nhood = np.asarray(nhood, dtype=bool)
    x = _thin_neighbors_x(nhood)

    remove_pixel = (
        _compute_g1(x) and
        _compute_g2(x) and
        _compute_g3(x)
    )

    return bool(nhood[1, 1] and not remove_pixel)


def thin_iter2_rule(nhood: np.ndarray) -> bool:
    nhood = np.asarray(nhood, dtype=bool)
    x = _thin_neighbors_x(nhood)

    remove_pixel = (
        _compute_g1(x) and
        _compute_g2(x) and
        _compute_g3_prime(x)
    )

    return bool(nhood[1, 1] and not remove_pixel)


def make_thin_luts() -> tuple[np.ndarray, np.ndarray]:
    """Generate MATLAB-like bwmorph(..., 'thin') iteration LUTs."""
    return (
        make_lut_3x3(thin_iter1_rule, dtype=bool),
        make_lut_3x3(thin_iter2_rule, dtype=bool),
    )


def branchpoints_rule(nhood: np.ndarray) -> bool:
    """
    Initial MATLAB branchpoint-candidate rule.

    Equivalent to the rule used to generate images.internal.lutbranchpoints().
    """
    nhood = np.asarray(nhood, dtype=bool)

    if not nhood[1, 1]:
        return False

    return (np.sum(nhood) - 1) > 2


def make_branchpoints_lut() -> np.ndarray:
    """Generate the initial branchpoint-candidate LUT."""
    return make_lut_3x3(branchpoints_rule, dtype=bool)


def backcount4_rule(nhood: np.ndarray) -> np.uint8:
    """
    MATLAB lutbackcount4 rule.

    If the center pixel is foreground, count the number of 4-connected
    background components in the 3x3 neighborhood. Otherwise return 0.
    """
    nhood = np.asarray(nhood, dtype=bool)

    if not nhood[1, 1]:
        return np.uint8(0)

    background = ~nhood

    _, count = ndi.label(
        background,
        structure=ndi.generate_binary_structure(2, 1),  # 4-connectivity
    )

    return np.uint8(count)


def make_backcount4_lut() -> np.ndarray:
    """Generate the MATLAB-style 4-connected background-count LUT."""
    return make_lut_3x3(backcount4_rule, dtype=np.uint8)


def dilate_rule(nhood: np.ndarray) -> bool:
    return np.any(nhood)


def make_dilate_lut() -> np.ndarray:
    return make_lut_3x3(dilate_rule, dtype=bool)

def spur_rule(nhood: np.ndarray) -> bool:
    """
    MATLAB lutspur rule.

    Detects endpoints in the complemented image, where 0-valued pixels
    are treated as foreground.
    """
    x = np.asarray(nhood, dtype=bool)

    is_east_endpoint = (
        (not x[1, 0]) and (not x[1, 1]) and
        x[0, 1] and x[0, 2] and x[1, 2] and x[2, 1] and x[2, 2]
    )

    is_south_endpoint = (
        (not x[0, 1]) and (not x[1, 1]) and
        x[1, 0] and x[1, 2] and x[2, 0] and x[2, 1] and x[2, 2]
    )

    is_west_endpoint = (
        (not x[1, 1]) and (not x[1, 2]) and
        x[0, 0] and x[0, 1] and x[1, 0] and x[2, 0] and x[2, 1]
    )

    is_north_endpoint = (
        (not x[1, 1]) and (not x[2, 1]) and
        x[0, 0] and x[0, 1] and x[0, 2] and x[1, 0] and x[1, 2]
    )

    is_southeast_endpoint = (
        (not x[1, 1]) and (not x[0, 0]) and (np.sum(x) == 7)
    )

    is_southwest_endpoint = (
        (not x[1, 1]) and (not x[0, 2]) and (np.sum(x) == 7)
    )

    is_northwest_endpoint = (
        (not x[1, 1]) and (not x[2, 2]) and (np.sum(x) == 7)
    )

    is_northeast_endpoint = (
        (not x[1, 1]) and (not x[2, 0]) and (np.sum(x) == 7)
    )

    return (
        is_east_endpoint or
        is_south_endpoint or
        is_west_endpoint or
        is_north_endpoint or
        is_southeast_endpoint or
        is_southwest_endpoint or
        is_northwest_endpoint or
        is_northeast_endpoint
    )


def make_spur_lut() -> np.ndarray:
    """Generate the MATLAB-style spur endpoint LUT."""
    return make_lut_3x3(spur_rule, dtype=bool)


def clean_rule(nhood: np.ndarray) -> bool:
    """
    MATLAB-like bwmorph(..., 'clean') rule.

    Keeps a foreground center pixel only if it has at least one
    foreground neighbor.
    """
    nhood = np.asarray(nhood, dtype=bool)

    if not nhood[1, 1]:
        return False

    return np.count_nonzero(nhood) > 1


def make_clean_lut() -> np.ndarray:
    """Generate the MATLAB-style clean LUT."""
    return make_lut_3x3(clean_rule, dtype=bool)


def endpoints_rule(nhood: np.ndarray) -> bool:
    """
    MATLAB endpoint LUT rule.
    """
    nhood = np.asarray(nhood, dtype=bool)

    if not nhood[1, 1]:
        return False

    background = ~nhood

    _, count = ndi.label(
        background,
        structure=ndi.generate_binary_structure(2, 1),  # 4-connectivity
    )

    return count == 1


def make_endpoints_lut() -> np.ndarray:
    return make_lut_3x3(endpoints_rule, dtype=bool)


LUT_THIN1, LUT_THIN2 = make_thin_luts()
LUT_BRIDGE = make_bridge_lut()
LUT_BRANCHPOINTS = make_branchpoints_lut()
LUT_ENDPOINTS = make_endpoints_lut()
LUT_BACKCOUNT4 = make_backcount4_lut()
LUT_DILATE = make_dilate_lut()
LUT_SPUR = make_spur_lut()
LUT_CLEAN = make_clean_lut()
