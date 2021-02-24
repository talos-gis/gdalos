from warnings import warn

from osgeo_utils.auxiliary.rectangle import *  # noqa

# warn('please use `osgeo_utils.auxiliary.rectangle` instead of `gdalos.rectangle`', DeprecationWarning)


def rect_contains(this: GeoRectangle, other: GeoRectangle):
    return \
        this.min_x <= other.min_x and \
        this.max_x >= other.max_x and \
        this.min_y <= other.min_y and \
        this.max_y >= other.max_y

