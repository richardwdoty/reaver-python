"""Display conversions only; processing arrays retain their original values."""
import math
import numpy as np
from scipy.ndimage import binary_erosion, binary_dilation
from skimage.morphology import disk
from reaver.app.display_settings import DisplaySettings


def imadjust_uint8(image):
    """MATLAB imadjust default: per-channel 1%/99% stretch, gamma 1."""
    result = np.empty_like(image)
    planes = image.reshape((*image.shape[:2], -1))
    output = result.reshape(planes.shape)
    for c in range(planes.shape[-1]):
        cdf = np.cumsum(np.bincount(planes[...,c].ravel(), minlength=256))/planes[...,c].size
        low = np.searchsorted(cdf, .01, side='right')
        high = np.searchsorted(cdf, .99, side='left')
        if low == high: low, high = 0, 255
        # Use normalized MATLAB arithmetic before uint8 half-up conversion.
        table = np.clip((np.arange(256)/255 - low/255)/(high/255-low/255),0,1)
        output[...,c] = np.floor(table[planes[...,c]]*255+.5).astype(np.uint8)
    return result


def _overlay_region(state, display_channels, settings, cache, bounds):
    """Render output bounds using a two-pixel input halo for erosion+dilation."""
    image = state.base_image.data
    layers = state.derived_layers
    height, width = layers.bw_2.shape
    y0, y1, x0, x1 = bounds
    sy0, sy1 = max(0, y0-2), min(height, y1+2)
    sx0, sx1 = max(0, x0-2), min(width, x1+2)
    crop = np.s_[y0-sy0:y1-sy0, x0-sx0:x1-sx0]
    base = image
    if settings.gamma_adjust:
        cached = None if cache is None else cache.get('contrast')
        if cached is None or cached[0] is not image:
            cached = (image, imadjust_uint8(image))
            if cache is not None:
                cache['contrast'] = cached
        base = cached[1]
    base = base[y0:y1, x0:x1]
    if image.ndim == 2 or image.shape[-1] == 1:
        base = np.repeat(base.reshape((*base.shape[:2], 1)), 3, axis=2)
        selected = (True, False, False)
    else:
        selected = display_channels
    outside = ~layers.bw_2[sy0:sy1, sx0:sx1]
    boundary = outside & ~binary_erosion(outside, border_value=0)
    # Suppress only the real image border, never the artificial crop border.
    if sy0 == 0:
        boundary[0, :] = False
    if sy1 == height:
        boundary[-1, :] = False
    if sx0 == 0:
        boundary[:, 0] = False
    if sx1 == width:
        boundary[:, -1] = False
    edge = binary_dilation(boundary, structure=disk(1))[crop]
    cached = None if cache is None else cache.get('wire')
    if cached is None or cached[0] is not layers.wire:
        cached = (layers.wire, binary_dilation(layers.wire, structure=disk(1)))
        if cache is not None:
            cache['wire'] = cached
    wire = cached[1][y0:y1, x0:x1]
    out = np.zeros((y1-y0, x1-x0, 3), dtype=np.uint8)
    for c in range(3):
        paint = settings.edge_line_color[c]*(edge & ~wire).astype(np.uint16) + settings.center_line_color[c]*wire.astype(np.uint16)
        # Preserve MATLAB's per-channel zero-color background rule exactly.
        out[..., c] = (paint + bool(selected[c])*(paint==0)*base[..., c]*(~wire)).astype(np.uint8)
    return out


def update_brush_view(state, mode, output, start, end, size,
                      display_channels=(True, True, True), settings=None, cache=None):
    """Update a displayed buffer after the unchanged brush rasterizer runs.

    The endpoint box conservatively encloses every rounded interpolation point.
    Add the brush radius and two pixels for the changed boundary's influence.
    Non-brush changes must instead use a full render_view refresh.
    """
    if mode not in ('overlay', 'segmented'):
        raise ValueError('Regional brush rendering requires an editable view')
    height, width = state.derived_layers.bw_2.shape
    margin = size + 2  # radius=size-1, rounding allowance=1, edge influence=2
    x0 = max(0, min(width, math.floor(min(start[0], end[0]))-margin))
    x1 = max(0, min(width, math.ceil(max(start[0], end[0]))+margin+1))
    y0 = max(0, min(height, math.floor(min(start[1], end[1]))-margin))
    y1 = max(0, min(height, math.ceil(max(start[1], end[1]))+margin+1))
    if x0 >= x1 or y0 >= y1:
        return
    if mode == 'overlay':
        patch = _overlay_region(state, display_channels, settings or DisplaySettings(), cache, (y0,y1,x0,x1))
    else:
        patch = state.derived_layers.bw_2[y0:y1, x0:x1].astype(np.uint8)*255
    output[y0:y1, x0:x1] = patch


def render_view(state, mode, display_channels=(True, True, True), input_channels=(0,), settings=None, cache=None):
    """Render exact pixels; optional cache requires immutable image/wire inputs.

    Hold source references rather than ids to avoid reuse after replacement.
    The GUI clears this bounded cache on every non-brush display refresh.
    """
    image = state.base_image.data
    gray = image.ndim == 2 or image.shape[-1] == 1
    layers = state.derived_layers
    if mode == 'displayed_channels':
        if gray:
            return image.reshape(image.shape[:2]).copy()
        background = image.copy()
        background[..., ~np.asarray(display_channels, dtype=bool)] = 0
        return background
    if mode == 'input_channel':
        if gray:
            return image.reshape(image.shape[:2]).copy()
        selected = image.copy()
        selected[..., [i for i in range(3) if i not in input_channels]] = 0
        return selected
    fields = dict(grey='gray', grey_neighbors='gray_neighbors',
                  first_binary='bw_1', first_binary_neighbors='bw_1_neighbors',
                  segmented='bw_2', wire_frame='wire')
    if mode == 'overlay':
        if layers.bw_2 is None or layers.wire is None:
            return None
        height, width = layers.bw_2.shape
        return _overlay_region(state, display_channels, settings or DisplaySettings(), cache, (0,height,0,width))
    data = getattr(layers, fields[mode])
    if data is None:
        return None
    if mode == 'wire_frame':
        return binary_dilation(data,structure=disk(2)).astype(np.uint8)*255
    if mode in ('first_binary', 'first_binary_neighbors', 'segmented', 'wire_frame'):
        return data.astype(np.uint8) * 255
    if mode == 'grey_neighbors':
        data = data * 255
    return np.clip(np.floor(data + .5), 0, 255).astype(np.uint8)
