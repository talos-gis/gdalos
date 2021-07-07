import pytest
import tempfile
from typing import Optional, Tuple

import numpy as np
from numpy.testing import assert_almost_equal
from osgeo import gdal
from osgeo import gdal_array

from osgeo_utils.auxiliary.base import PathLikeOrStr, MaybeSequence
from osgeo_utils.auxiliary.util import GetOutputDriverFor


def write_array_to_file(dst_filename: PathLikeOrStr, a: MaybeSequence[np.ndarray], gdal_dtype=None) -> gdal.Dataset:
    driver_name = GetOutputDriverFor(dst_filename, is_raster=True)
    driver = gdal.GetDriverByName(driver_name)
    a_shape = a[0].shape
    if len(a_shape) == 1:
        # 2d array, singleband raster
        a = [a]
        bands_count = 1
    elif len(a_shape) == 2:
        # 3d array, multiband raster
        bands_count = a.shape[0]
    else:
        raise Exception('Array should have 2 or 3 dimensions')
    y_size, x_size = a[0].shape

    if gdal_dtype is None:
        np_dtype = a[0].dtype
        gdal_dtype = gdal_array.flip_code(np_dtype)
    ds = driver.Create(
        dst_filename, x_size, y_size, bands_count, gdal_dtype)
    if ds is None:
        raise Exception(f'failed to create: {dst_filename}')

    for bnd_num in range(bands_count):
        bnd = ds.GetRasterBand(bnd_num+1)
        if gdal_array.BandWriteArray(bnd, a[bnd_num], xoff=0, yoff=0) != 0:
            raise Exception('I/O error')

    return ds


@pytest.mark.parametrize("shape", [(10, 20), (2, 10, 20)])
def test_write_array_to_file(shape: Tuple[int], dst_filename: Optional[PathLikeOrStr] = None):
    np_dtype = np.float32
    a = np.random.rand(*shape)
    a = np.array(a, dtype=np_dtype)
    if dst_filename is None:
        dst_filename = tempfile.mktemp(suffix='.tif')
    ds = write_array_to_file(dst_filename, a)

    if len(shape) == 3:
        a0 = a[0]
        raster_count = shape[0]
        y_size, x_size = shape[1:]
    else:
        a0 = a
        raster_count = 1
        y_size, x_size = shape
    assert ds.RasterCount == raster_count
    assert ds.RasterXSize == x_size
    assert ds.RasterYSize == y_size
    bnd: gdal.Band = ds.GetRasterBand(1)
    assert bnd.DataType == gdal_array.flip_code(a.dtype)
    b = bnd.ReadAsArray()
    assert_almost_equal(a0, b)
    ds = None

    gdal.Unlink(dst_filename)

