from typing import Tuple

import osgeo
from gdalos import version as gdalos_version  # noqa


def version_tuple(version: str) -> Tuple[int]:
    return tuple(int(s) for s in str(version).split('.') if s.isdigit())[:3]


gdal_version = version_tuple(osgeo.__version__)
gdal_cog_support = gdal_version >= (3, 1)
gdal_multi_thread_support = gdal_version >= (3, 2)
gdal_workaround_warp_scale_bug = gdal_version < (3, 3)  # workaround https://github.com/OSGeo/gdal/issues/3232
