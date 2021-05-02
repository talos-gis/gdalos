import math
from typing import Tuple

from osgeo import osr, gdal

from osgeo_utils.auxiliary.extent_util import GeoTransform
from osgeo_utils.auxiliary.rectangle import GeoRectangle


def calc_dx_dy_from_extent_and_count(extent: GeoRectangle, sample_count: int) -> Tuple[float, float]:
    (min_x, max_x, min_y, max_y) = extent.min_max
    w = max_x - min_x
    h = max_y - min_y
    pix_area = w * h / sample_count
    if pix_area <= 0 or w <= 0 or h <= 0:
        return 0, 0
    pix_len = math.sqrt(pix_area)
    return pix_len, pix_len


def transform_extent(extent: GeoRectangle,
                     transform: osr.CoordinateTransformation, sample_count: int = 1000) -> GeoRectangle:
    """ returns a transformed extent by transforming sample_count points along a given extent """
    if transform is None:
        return extent
    maxf = float("inf")
    (out_min_x, out_max_x, out_min_y, out_max_y) = (maxf, -maxf, maxf, -maxf)

    dx, dy = calc_dx_dy_from_extent_and_count(extent, sample_count)
    if dx == 0:
        return GeoRectangle.empty()

    y = float(extent.min_y)
    while y <= extent.max_y + dy:
        x = float(extent.min_x)
        while x <= extent.max_x + dx:
            tx, ty, tz = transform.TransformPoint(x, y)
            x += dx
            if not math.isfinite(tz):
                continue
            out_min_x = min(out_min_x, tx)
            out_max_x = max(out_max_x, tx)
            out_min_y = min(out_min_y, ty)
            out_max_y = max(out_max_y, ty)
        y += dy

    return GeoRectangle.from_min_max(out_min_x, out_max_x, out_min_y, out_max_y)


def get_geotransform_and_size(ds: gdal.Dataset) -> Tuple[GeoTransform, Tuple[int, int]]:
    return ds.GetGeoTransform(), (ds.RasterXSize, ds.RasterYSize)
