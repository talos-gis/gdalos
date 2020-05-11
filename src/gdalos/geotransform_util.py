from gdalos import GeoRectangle
import math


def get_offsets(src_gt, src_size, dst_gt, dst_size):
    src = GeoRectangle.from_geotransform_and_size(src_gt, src_size)
    dst = GeoRectangle.from_geotransform_and_size(dst_gt, dst_size)
    offset = (dst.x - src.x, dst.y - src.y)
    src_offset = (max(0, offset[0]), max(0, offset[1]))
    dst_offset = (max(0, -offset[0]), max(0, -offset[1]))
    return src_offset, dst_offset

# 0 = x-coordinate of the upper-left corner of the upper-left pixel
# 1 = width of a pixel
# 2 = row rotation (typically zero)
# 3 = y-coordinate of the of the upper-left corner of the upper-left pixel
# 4 = column rotation (typically zero)
# 5 = height of a pixel (typically negative)


def get_extent(GeoTransforms, Dimensions, isUnion: bool):
    # corners = [GetExtent(gt, *dimensions) for gt, dimensions in zip(GeoTransforms, Dimensions)]

    # extents differ, but pixel size and rotation are the same.
    # we'll make a union or an intersection
    if GeoTransforms is None or len(GeoTransforms) != len (Dimensions):
        return None
    out_rect:GeoRectangle = None
    for gt, size in zip(GeoTransforms, Dimensions):
        # Xgeo = gt(0) + Xpixel * gt(1) + Yline * gt(2)
        # Ygeo = gt(3) + Xpixel * gt(4) + Yline * gt(5)
        rect = GeoRectangle.from_geotransform_and_size(gt, size)
        if out_rect:
            if isUnion:
                out_rect = out_rect.union(rect)
            else:
                out_rect = out_rect.crop(rect)
        else:
            out_rect = rect

    if out_rect is None or out_rect.is_empty():
        return None
    else:
        pixel_size = (gt[1], gt[5])
        gt = (  out_rect.x * pixel_size[0],
                gt[1], gt[2],
                out_rect.y * pixel_size[1],
                gt[4], gt[5])
    return gt, (math.ceil(out_rect.w), math.ceil(out_rect.h))


# def GetExtent(gt,cols,rows):
#     ''' Return list of corner coordinates from a geotransform
#
#         @type gt:   C{tuple/list}
#         @param gt: geotransform
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