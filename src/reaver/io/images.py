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

    if image_data.shape[2] == 1:
        image_data = np.repeat(image_data, 3, axis=2)

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
        image = tifffile.imread(path)
    else:
        image = np.array(Image.open(path))

    image = _normalize_image_shape(image)

    return image.astype(np.uint8)


def _normalize_image_shape(image: np.ndarray) -> np.ndarray:
    # grayscale
    if image.ndim == 2:
        return image[:, :, np.newaxis]

    # channels-first TIFF
    if image.ndim == 3 and image.shape[0] in [2, 3, 4]:
        image = np.moveaxis(image, 0, -1)

    return image