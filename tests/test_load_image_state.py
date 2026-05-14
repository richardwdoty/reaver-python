# tests/test_load_image_state.py

from pathlib import Path

import numpy as np
import pytest

from reaver.io.images import load_image_state


TEST_IMAGE_DIR = Path(__file__).resolve().parents[1] / "data" / "test_images"


@pytest.mark.parametrize(
    "filename",
    [
        "example_rgb.tif",
    ],
)
def test_load_image_state_loads_image(filename):
    image_path = TEST_IMAGE_DIR / filename

    image_state = load_image_state(image_path)

    assert image_state.path == image_path
    assert image_state.image_id == image_path.stem
    assert image_state.image_loaded is True

    assert image_state.base_image is not None
    assert image_state.base_image.path == image_path
    assert image_state.base_image.data is not None

    image_data = image_state.base_image.data

    assert isinstance(image_data, np.ndarray)
    assert image_data.ndim == 3
    assert image_data.dtype == np.uint8

    assert image_state.base_image.y_size == image_data.shape[0]
    assert image_state.base_image.x_size == image_data.shape[1]
    assert image_state.base_image.n_channels == image_data.shape[2]


def test_load_image_state_rejects_missing_file():
    missing_path = TEST_IMAGE_DIR / "does_not_exist.tif"

    with pytest.raises(FileNotFoundError):
        load_image_state(missing_path)