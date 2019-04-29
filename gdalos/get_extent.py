import sys
import math
from osgeo import gdal, osr, ogr
from math import isfinite

from gdalos.rectangle import GeoRectangle


def get_points_extent(gt, cols, rows):
    """Return list of corner coordinates from a geotransform"""

    def transform_point(px, py):
        x = gt[0] + (px * gt[1]) + (py * gt[2])
        y = gt[3] + (px * gt[4]) + (py * gt[5])
        return x, y

    return [
        transform_point(0, 0),
        transform_point(0, rows),
        transform_point(cols, rows),
        transform_point(cols, 0)
    ]


def _srs(srs):
    if isinstance(srs, str):
        srs_ = osr.SpatialReference()
        if srs_.ImportFromProj4(srs) != ogr.OGRERR_NONE:
            raise Exception("ogr error when parsing srs")
        srs = srs_
    return srs


def reproject_coordinates(coords, src_srs, tgt_srs):
    src_srs = _srs(src_srs)
    tgt_srs = _srs(tgt_srs)

    transform = osr.CoordinateTransformation(src_srs, tgt_srs)
    return [
        transform.TransformPoint(src_x, src_y)[:2] for src_x, src_y in coords
    ]


def get_transform(src_srs, tgt_srs):
    src_srs = _srs(src_srs)
    tgt_srs = _srs(tgt_srs)
    if src_srs.IsSame(tgt_srs):
        return None
    else:
        return osr.CoordinateTransformation(src_srs, tgt_srs)


def translate_extent(extent: GeoRectangle, transform, sample_count=1000):
    if transform is None:
        return extent
    maxf = float('inf')
    (out_x_min, out_x_max, out_y_min, out_y_max) = (maxf, -maxf, maxf, -maxf)

    (x_min, x_max, y_min, y_max) = extent.lrdu

    d = ((x_max - x_min) + (y_max - y_min)) / sample_count
    if d <= 0:
        return GeoRectangle.empty()
    dx = (x_max - x_min) / math.ceil((x_max - x_min) / d)
    dy = (y_max - y_min) / math.ceil((y_max - y_min) / d)

    y = float(y_min)
    while y <= y_max:
        x = float(x_min)
        while x < x_max:
            tx, ty, tz = transform.TransformPoint(x, y)
            x += dx
            if not isfinite(tz):
                continue
            out_x_min = min(out_x_min, tx)
            out_x_max = max(out_x_max, tx)
            out_y_min = min(out_y_min, ty)
            out_y_max = max(out_y_max, ty)
        y += dy

    return GeoRectangle.from_min_max(out_x_min, out_x_max, out_y_min, out_y_max)


# todo so does gtrans open the dataset like fifty times or something?
def get_points_extent_from_file(raster_filename):
    ds = gdal.Open(raster_filename)

    geo_transform = ds.GetGeoTransform()
    cols = ds.RasterXSize
    rows = ds.RasterYSize
    points_extent = get_points_extent(geo_transform, cols, rows)

    src_srs = osr.SpatialReference()
    src_srs.ImportFromWkt(ds.GetProjection())
    src_srs_pj4 = src_srs.ExportToProj4()

    return points_extent, src_srs_pj4, geo_transform


def dist(p1x, p1y, p2x, p2y):
    return math.sqrt((p2y - p1y) ** 2 + (p2x - p1x) ** 2)


def transform_resolution_p(transform, dy, px, py):
    p1x, p1y, *_ = transform.TransformPoint(px, py, 0)
    p2x, p2y, *_ = transform.TransformPoint(px, py + dy, 0)
    return dist(p1x, p1y, p2x, p2y)


def transform_resolution(transform, dy, xmin, xmax, ymin, ymax):
    result = min(
        transform_resolution_p(transform, dy, xmin, ymin),
        transform_resolution_p(transform, -dy, xmin, ymax),
        transform_resolution_p(transform, -dy, xmax, ymax),
        transform_resolution_p(transform, dy, xmax, ymin)
    )
    if (ymin > 0) and (ymax < 0):
        result = min(
            result,
            transform_resolution_p(transform, dy, xmin, 0),
            transform_resolution_p(transform, dy, xmax, 0)
        )
    return result


# todo we need to get rid of this
def round_to_sig(d, extra_digits=-5):
    if (d == 0) or math.isnan(d) or math.isinf(d):
        return 0
    if abs(d) > 1E-20:
        digits = int(math.floor(math.log10(abs(d) + 1E-20)))
    else:
        digits = int(math.floor(math.log10(abs(d))))
    digits = digits + extra_digits
    return round(d, -digits)
