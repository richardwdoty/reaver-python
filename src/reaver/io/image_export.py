"""Lossless TIFF exports of saved masks and full-resolution display pixels."""
from datetime import datetime
from pathlib import Path
import os
import tempfile
import numpy as np
import tifffile
from .results import _read, _array


def write_new_tiff(path, pixels):
    """Validate a complete TIFF before publishing; never overwrite any file."""
    path = Path(path)
    pixels = np.asarray(pixels)
    if pixels.dtype not in (np.dtype(bool), np.dtype('uint8')) or pixels.ndim not in (2,3):
        raise ValueError('Expected binary or uint8 display pixels')
    if pixels.ndim == 3 and pixels.shape[-1] != 3:
        raise ValueError('Expected RGB pixels')
    if not pixels.size:
        raise ValueError('No image pixels to export')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,suffix='.tmp',delete=False) as stream:
            temporary = Path(stream.name)
            tifffile.imwrite(stream, pixels, photometric='rgb' if pixels.ndim==3 else 'minisblack', metadata=None)
            stream.flush();os.fsync(stream.fileno())
        if not np.array_equal(tifffile.imread(temporary), pixels):
            raise ValueError('TIFF verification failed')
        # Hard-link publication is atomic and refuses an existing destination.
        os.link(temporary,path)
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
    return path


def unique_tiff(folder, stem, pixels):
    folder=Path(folder)
    for index in range(100000):
        path=folder/(stem+('' if index==0 else f' ({index+1})')+'.tif')
        try:
            return write_new_tiff(path,pixels)
        except FileExistsError:
            continue
    raise ValueError('Could not choose an unused export filename')


def export_displayed_image(source, pixels):
    source=Path(source)
    return unique_tiff(source.parent,source.stem+' - '+datetime.now().strftime('%Y-%m-%d %H-%M-%S'),pixels)


def export_saved_masks(items, directory, progress=lambda *args:None):
    """Export saved BW_2 only, including unverified analyses; no recalculation."""
    folder=Path(directory)/'bw'
    folder.mkdir(exist_ok=True)
    report=dict(saved=[],failed=[])
    for index,(analysis,source) in enumerate(items):
        progress(index,len(items),Path(source).name)
        try:
            data=_read(analysis)
            shape=tuple(int(v) for v in np.asarray(data['imageSize']).reshape(-1))
            if len(shape)!=2 or min(shape)<1:raise ValueError('Invalid image dimensions')
            mask=_array(data['derivedPic']['BW_2'],shape,'BW_2',True)
            report['saved'].append(str(unique_tiff(folder,Path(source).stem,mask)))
        except Exception as exc:
            report['failed'].append(f'{Path(source).name}: {exc}')
    return report
