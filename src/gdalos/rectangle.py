import math
from osgeo_utils.auxiliary.rectangle import *  # noqa


def rect_contains(this: GeoRectangle, other: GeoRectangle):
    return \
        this.min_x <= other.min_x and \
        this.max_x >= other.max_x and \
        this.min_y <= other.min_y and \
        this.max_y >= other.max_y


def gt_and_size_from_rect(r: GeoRectangle, pixel_size):
    origin = (r.min_x, r.max_y)
    pix_r = r.to_pixels(pixel_size)
    size = tuple(math.ceil(x) for x in pix_r.size)
    return size, (origin[0], pixel_size[0], 0, origin[1], 0, pixel_size[1])


