import numpy as np
import pytest
import tifffile

from reaver.io.images import load_image_state, to_uint8


def test_uint16_matlab_scaling():
    # Verified directly with MATLAB R2024a im2uint8.
    image = np.array([0, 255, 256, 257, 32768, 65535], dtype=np.uint16)
    np.testing.assert_array_equal(to_uint8(image), [0, 1, 1, 1, 128, 255])


def test_float_clipping_and_rounding():
    np.testing.assert_array_equal(to_uint8(np.array([-1., 0., .5, 1., 2.])), [0, 0, 128, 255, 255])


def test_small_rgb_is_not_mistaken_for_planar_channels(tmp_path):
    image = np.arange(3*8*3, dtype=np.uint8).reshape(3, 8, 3)
    path = tmp_path / 'small.tif'
    tifffile.imwrite(path, image, photometric='rgb')
    np.testing.assert_array_equal(load_image_state(path).base_image.data, image)


def test_grayscale_retains_identity(tmp_path):
    path = tmp_path / 'gray.tif'
    tifffile.imwrite(path, np.full((8, 9), 32768, np.uint16))
    state = load_image_state(path)
    assert state.base_image.n_channels == 1
    assert np.all(state.base_image.data == 128)


def test_two_tiff_pages_are_channels_with_zero_blue(tmp_path):
    path = tmp_path / 'pages.tif'
    with tifffile.TiffWriter(path) as tif:
        tif.write(np.full((8, 9), 20, np.uint8))
        tif.write(np.full((8, 9), 80, np.uint8))
    image = load_image_state(path).base_image.data
    assert image.shape == (8, 9, 3)
    np.testing.assert_array_equal(image[0, 0], [20, 80, 0])
