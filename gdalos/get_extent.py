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


def calc_dx_dy(extent: GeoRectangle, sample_count: int):
    (min_x, max_x, min_y, max_y) = extent.min_max
    w = max_x - min_x
    h = max_y - min_y
    pix_area = w*h / sample_count
    if pix_area <= 0 or w <= 0 or h <= 0:
        return 0, 0
    pix_len = math.sqrt(pix_area)
    return pix_len, pix_len


def translate_extent(extent: GeoRectangle, transform, sample_count=1000):
    if transform is None:
        return extent
    maxf = float('inf')
    (out_min_x, out_max_x, out_min_y, out_max_y) = (maxf, -maxf, maxf, -maxf)

    dx, dy = calc_dx_dy(extent, sample_count)
    if dx == 0:
        return GeoRectangle.empty()

    y = float(extent.min_y)
    while y <= extent.max_y:
        x = float(extent.min_x)
        while x < extent.max_x:
            tx, ty, tz = transform.TransformPoint(x, y)
            x += dx
            if not isfinite(tz):
                continue
            out_min_x = min(out_min_x, tx)
            out_max_x = max(out_max_x, tx)
            out_min_y = min(out_min_y, ty)
            out_max_y = max(out_max_y, ty)
        y += dy

    return GeoRectangle.from_min_max(out_min_x, out_max_x, out_min_y, out_max_y)


def get_points_extent_from_ds(ds):
    geo_transform = ds.GetGeoTransform()
    cols = ds.RasterXSize
    rows = ds.RasterYSize
    points_extent = get_points_extent(geo_transform, cols, rows)
    return points_extent, geo_transform


def dist(p1x, p1y, p2x, p2y):
    return math.sqrt((p2y - p1y) ** 2 + (p2x - p1x) ** 2)


def transform_resolution_p(transform, dx, dy, px, py):
    p1x, p1y, *_ = transform.TransformPoint(px, py + dx, 0)
    p2x, p2y, *_ = transform.TransformPoint(px, py + dy, 0)
    return dist(p1x, p1y, p2x, p2y)


def transform_resolution_old(transform, input_res, extent: GeoRectangle):
    (xmin, xmax, ymin, ymax) = extent.min_max
    [dx, dy] = input_res
    out_res_x = min(
        transform_resolution_p(transform, 0, dy, xmin, ymin),
        transform_resolution_p(transform, 0, -dy, xmin, ymax),
        transform_resolution_p(transform, 0, -dy, xmax, ymax),
        transform_resolution_p(transform, 0, dy, xmax, ymin)
    )
    if (ymin > 0) and (ymax < 0):
        out_res_x = min(
            out_res_x,
            transform_resolution_p(transform, 0, dy, xmin, 0),
            transform_resolution_p(transform, 0, dy, xmax, 0)
        )
    out_res_x = round_to_sig(out_res_x, -1)
    out_res = (out_res_x, -out_res_x)
    return out_res


def transform_resolution(transform, input_res, extent: GeoRectangle, equal_res = ..., sample_count=1000):
    dx, dy = calc_dx_dy(extent, sample_count)

    calc_only_res_y = equal_res is ...
    out_x = []
    out_y = []
    y = float(extent.min_y)
    while y <= extent.max_y:
        x = float(extent.min_x)
        while x < extent.max_x:
            out_y.append(transform_resolution_p(transform, 0, input_res[1], x, y))
            if not calc_only_res_y:
                out_x.append(transform_resolution_p(transform, input_res[0], 0, x, y))
            x += dx
        y += dy

    if calc_only_res_y:
        out_y.sort()
        out_x = out_y
    if equal_res:
        out_y.extend(out_x)
        out_y.sort()
        out_x = out_y
    else:
        out_x.sort()
        out_y.sort()
    out_r = [out_x, out_y]

    # choose the median resolution
    out_res = [round_to_sig(r[round(len(r) / 2)], -1) for r in out_r]
    out_res[1] = -out_res[1]
    return out_res


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
