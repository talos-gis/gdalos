import tempfile
import math

from osgeo import ogr, osr
import gdal

from gdalos.rectangle import GeoRectangle, get_points_extent

# Geotransform:
# 0 = x-coordinate of the upper-left corner of the upper-left pixel
# 1 = pixel width,
# 2 = row rotation (typically zero)
# 3 = y-coordinate of the of the upper-left corner of the upper-left pixel
# 4 = column rotation (typically zero)
# 5 = pixel height (typically negative)
# Xgeo = gt(0) + Xpixel * gt(1) + Yline * gt(2)
# Ygeo = gt(3) + Xpixel * gt(4) + Yline * gt(5)

# In case of north up images,
# (GT(2), GT(4)) coefficients are zero,
# (GT(1), GT(5)) is pixel size
# (GT(0), GT(3)) position is the top left corner of the top left pixel of the raster.
# Note that the pixel/line coordinates in the above are from (0.0,0.0) at the top left corner of the top left pixel
# to (width_in_pixels,height_in_pixels) at the bottom right corner of the bottom right pixel.
# The pixel/line location of the center of the top left pixel would therefore be (0.5,0.5).


def calc_dx_dy(extent: GeoRectangle, sample_count: int):
    (min_x, max_x, min_y, max_y) = extent.min_max
    w = max_x - min_x
    h = max_y - min_y
    pix_area = w * h / sample_count
    if pix_area <= 0 or w <= 0 or h <= 0:
        return 0, 0
    pix_len = math.sqrt(pix_area)
    return pix_len, pix_len


def translate_extent(extent: GeoRectangle, transform, sample_count=1000):
    if transform is None:
        return extent
    maxf = float("inf")
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
            if not math.isfinite(tz):
                continue
            out_min_x = min(out_min_x, tx)
            out_max_x = max(out_max_x, tx)
            out_min_y = min(out_min_y, ty)
            out_max_y = max(out_max_y, ty)
        y += dy

    return GeoRectangle.from_min_max(out_min_x, out_max_x, out_min_y, out_max_y)


def get_geotransform_and_size(ds):
    return ds.GetGeoTransform(), (ds.RasterXSize, ds.RasterYSize)


def get_points_extent_from_ds(ds):
    geo_transform, size = get_geotransform_and_size(ds)
    points_extent = get_points_extent(geo_transform, *size)
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
        transform_resolution_p(transform, 0, dy, xmax, ymin),
    )
    if (ymin > 0) and (ymax < 0):
        out_res_x = min(
            out_res_x,
            transform_resolution_p(transform, 0, dy, xmin, 0),
            transform_resolution_p(transform, 0, dy, xmax, 0),
        )
    out_res_x = round_to_sig(out_res_x, -1)
    out_res = (out_res_x, -out_res_x)
    return out_res


def transform_resolution(
    transform, input_res, extent: GeoRectangle, equal_res=..., sample_count=1000):
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
    if abs(d) > 1e-20:
        digits = int(math.floor(math.log10(abs(d) + 1e-20)))
    else:
        digits = int(math.floor(math.log10(abs(d))))
    digits = digits + extra_digits
    return round(d, -digits)


def get_extent(ds):
    gt, size = get_geotransform_and_size(ds)
    return GeoRectangle.from_geotransform_and_size(gt, size)


def calc_geo_offsets(src_gt, src_size, dst_gt, dst_size):
    src = GeoRectangle.from_geotransform_and_size_to_pix(src_gt, src_size)
    dst = GeoRectangle.from_geotransform_and_size_to_pix(dst_gt, dst_size)
    offset = (dst.x - src.x, dst.y - src.y)
    src_offset = (max(0, offset[0]), max(0, offset[1]))
    dst_offset = (max(0, -offset[0]), max(0, -offset[1]))
    return src_offset, dst_offset


def calc_geotransform_and_dimensions(geotransforms, dimensions, input_extent: GeoRectangle = None):
    # extents differ, but pixel size and rotation are the same.
    # we'll make a union or an intersection
    if geotransforms is None or len(geotransforms) != len(dimensions):
        raise Exception('Error! GeoTransforms and Dimensions have different lengths!')
    if isinstance(input_extent, GeoRectangle):
        gt = geotransforms[0]
        out_extent = input_extent.align(gt)
    else:
        out_extent: GeoRectangle = None
        is_union = input_extent == 2
        for gt, size in zip(geotransforms, dimensions):
            extent = GeoRectangle.from_geotransform_and_size(gt, size)
            out_extent = extent if out_extent is None else \
                out_extent.union(extent) if is_union else out_extent.intersect(extent)

    if out_extent is None or out_extent.is_empty():
        return None, None, None
    else:
        pixel_size = (gt[1], gt[5])
        pix_extent = out_extent.to_pixels(pixel_size)
        gt = (out_extent.left,
              gt[1], gt[2],
              out_extent.up,
              gt[4], gt[5])
    return gt, (math.ceil(pix_extent.w), math.ceil(pix_extent.h)), out_extent


def make_temp_vrt(ds, extent: GeoRectangle):
    # ds = gdalos_util.open_ds(filename)
    # extent = gdalos_extent.get_extent(ds)
    options = gdal.BuildVRTOptions(outputBounds=(extent.min_x, extent.min_y, extent.max_x, extent.max_y))
    # hideNodata=True, separate=False)
    # vrt_filename = filename + ".vrt"
    vrt_filename = tempfile.mktemp(suffix='.vrt')
    vrt_ds = gdal.BuildVRT(vrt_filename, ds, options=options)
    if vrt_ds is None:
        raise Exception("Error! cannot create vrt. Cannot proceed")
    return vrt_filename, vrt_ds


def make_temp_vrt_old(filename, ds, data_type, projection, bands_count, gt, dimensions, ref_gt, ref_dimensions):
    drv = gdal.GetDriverByName("VRT")
    dt = gdal.GetDataTypeByName(data_type)

    # vrt_filename = filename + ".vrt"
    vrt_filename = tempfile.mktemp(suffix='.vrt')
    vrt_ds = drv.Create(vrt_filename, ref_dimensions[0], ref_dimensions[1], bands_count, dt)
    vrt_ds.SetGeoTransform(ref_gt)
    vrt_ds.SetProjection(projection)

    src_offset, dst_offset = calc_geo_offsets(gt, dimensions, ref_gt, ref_dimensions)
    if src_offset is None:
        raise Exception("Error! The requested extent is empty. Cannot proceed")

    source_size = dimensions

    for j in range(1, bands_count + 1):
        band = vrt_ds.GetRasterBand(j)
        inBand = ds.GetRasterBand(j)
        myBlockSize = inBand.GetBlockSize()

        myOutNDV = inBand.GetNoDataValue()
        if myOutNDV is not None:
            band.SetNoDataValue(myOutNDV)
        ndv_out = '' if myOutNDV is None else '<NODATA>%i</NODATA>' % myOutNDV

        source_xml = '<SourceFilename relativeToVRT="1">%s</SourceFilename>' % filename + \
                     '<SourceBand>%i</SourceBand>' % j + \
                     '<SourceProperties RasterXSize="%i" RasterYSize="%i" DataType=%s BlockXSize="%i" BlockYSize="%i"/>' % \
                     (*source_size, dt, *myBlockSize) + \
                     '<SrcRect xOff="%i" yOff="%i" xSize="%i" ySize="%i"/>' % \
                     (*src_offset, *source_size) + \
                     '<DstRect xOff="%i" yOff="%i" xSize="%i" ySize="%i"/>' % \
                     (*dst_offset, *source_size) + \
                     ndv_out
        source = '<ComplexSource>' + source_xml + '</ComplexSource>'
        band.SetMetadataItem("source_%i" % j, source, 'new_vrt_sources')
        band = None  # close band
    return vrt_filename, vrt_ds

# def GetExtent(gt,cols,rows):
#     ''' Return list of corner coordinates from a gt
#
#         @type gt:   C{tuple/list}
#         @param gt: gt
#         @type cols:   C{int}
#         @param cols: number of columns in the dataset
#         @type rows:   C{int}
#         @param rows: number of rows in the dataset
#         @rtype:    C{[float,...,float]}
#         @return:   coordinates of each corner
#     '''
#     ext=[]
#     xarr=[0, cols]
#     yarr=[0, rows]
#
#     for px in xarr:
#         for py in yarr:
#             x=gt[0]+(px*gt[1])+(py*gt[2])
#             y=gt[3]+(px*gt[4])+(py*gt[5])
#             ext.append([x, y])
#         yarr.reverse()
#     return ext

