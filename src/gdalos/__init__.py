from typing import Tuple

import osgeo


def version_tuple(version: str) -> Tuple[int]:
    return tuple(int(s) for s in str(version).split('.') if s.isdigit())[:3]


def set_traditional_gis_order():
    if gdal_version >= (3, 0):
        from osgeo.osr import OAMS_TRADITIONAL_GIS_ORDER
        from osgeo_utils.auxiliary.osr_util import set_default_axis_order
        set_default_axis_order(OAMS_TRADITIONAL_GIS_ORDER)


version = (0, 64, 0)

__package_name__ = "gdalos"
__version__ = '.'.join(str(v) for v in version)
__author__ = "Idan Miara, Ben Avrahami"
__author_email__ = "idan@miara.com"
__license__ = "MIT"
__url__ = r"https://github.com/talos-gis/gdalos"
__description__ = "a simple gdal translate/warp/addo python wrapper for raster batch processing"

gdalos_version = version
gdal_version = version_tuple(osgeo.__version__)

set_traditional_gis_order()
