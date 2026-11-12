"""MATLAB square brush and single backup per edit/update cycle."""
from copy import deepcopy
import numpy as np
from .wire import apply_binary_edit


def paint_segment(state, start, end, size, add):
    if not state.image_segmented:
        raise ValueError('Segment before editing')
    if not 1 <= size <= 16:
        raise ValueError('MATLAB brush setting must be 1..16')
    # MATLAB displays radius+1, while the square footprint is 2*radius+1.
    radius = size - 1
    a, b = np.asarray(start), np.asarray(end)
    if np.array_equal(a, b):
        points = a[None, :]
    else:
        points = np.linspace(a, b, 50)
    # Coordinates refer to zero-based pixel centers. MATLAB rounds half away
    # from zero in one-based coordinates, including just outside the image.
    one_based = points + 1
    points = (np.sign(one_based) * np.floor(np.abs(one_based) + .5) - 1).astype(int)
    old = state.derived_layers
    mask = old.bw_2.copy()
    height, width = mask.shape
    for x, y in points:
        if 0 <= x < width and 0 <= y < height:
            mask[max(0,y-radius):min(height,y+radius+1),
                 max(0,x-radius):min(width,x+radius+1)] = add
    if np.array_equal(mask, old.bw_2):
        return False
    if not state.edit_backup_locked:
        state.undo_layers = deepcopy(old)
        state.edit_backup_locked = True
    apply_binary_edit(state, mask)
    # MATLAB keeps the previous skeleton visible in the overlay until Update
    # Wire, but disables the dedicated wire view while it is stale.
    for name in ('wire','branchpoints','endpoints','dilated_wire','dilated_wire_2'):
        setattr(state.derived_layers, name, getattr(old, name))
    state.undo_available = True
    return True


def undo_edit(state):
    if not state.undo_available or state.undo_layers is None:
        return False
    state.derived_layers = deepcopy(state.undo_layers)
    state.wire_update_pending = False
    state.undo_available = False
    state.dirty = True
    state.verified = False
    state.metrics.clear()
    state.measurements.clear()
    return True
