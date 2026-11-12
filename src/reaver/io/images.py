from pathlib import Path

import numpy as np
import tifffile
from PIL import Image

from reaver.app.image_state import (
    BaseImage,
    ReaverImageState,
)


def load_image_state(path: str | Path) -> ReaverImageState:
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Image file does not exist: {path}")

    image_data = _read_image(path)

    if image_data.ndim == 2:
        image_data = image_data[:, :, np.newaxis]

    if image_data.shape[2] == 2:
        image_data = np.concatenate([image_data, np.zeros_like(image_data[:, :, :1])], axis=2)

    base_image = BaseImage(
        path=path,
        data=image_data,
        y_size=image_data.shape[0],
        x_size=image_data.shape[1],
        n_channels=image_data.shape[2],
    )

    image_state = ReaverImageState(
        image_id=path.stem,
        path=path,
        base_image=base_image,
        image_loaded=True,
    )

    return image_state


def _read_image(path: Path) -> np.ndarray:
    suffix = path.suffix.lower()

    if suffix in [".tif", ".tiff"]:
        # MATLAB reads each TIFF directory and concatenates its channels.
        with tifffile.TiffFile(path) as tif:
            pages = []
            for page in tif.pages:
                data = page.asarray()
                if page.axes == "SYX":
                    data = np.moveaxis(data, 0, -1)
                if data.ndim == 2:
                    data = data[:, :, np.newaxis]
                pages.append(to_uint8(data))
            image = np.concatenate(pages, axis=2)
    else:
        image = np.array(Image.open(path))

    image = _normalize_image_shape(image)

    return to_uint8(image)


def _normalize_image_shape(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image[:, :, np.newaxis]
    if image.ndim != 3 or image.shape[-1] not in (1, 2, 3):
        raise ValueError(f"Unsupported image shape: {image.shape}")
    return image


def to_uint8(image: np.ndarray) -> np.ndarray:
    """MATLAB im2uint8 conversion; no image-dependent contrast stretching."""
    if image.dtype == np.uint8:
        return image.copy()
    if image.dtype == np.bool_:
        return image.astype(np.uint8) * 255
    if image.dtype == np.uint16:
        values = image.astype(np.float64) / 257
    elif image.dtype == np.int16:
        values = (image.astype(np.float64) + 32768) / 257
    elif np.issubdtype(image.dtype, np.floating):
        values = np.clip(np.nan_to_num(image, nan=0), 0, 1) * 255
    else:
        raise ValueError(f"Unsupported image dtype: {image.dtype}")
    return np.floor(values + 0.5).astype(np.uint8)
