from gdalos.__data__ import (
    __name__,
    __author__,
    __author_email__,
    __license__,
    __url__,
    __version__,
)

from gdalos.gdalos_main import OvrType, RasterKind, gdalos_trans
from gdalos.rectangle import GeoRectangle

__all__ = ['GeoRectangle', 'OvrType', 'RasterKind', 'gdalos_trans', '__version__']
