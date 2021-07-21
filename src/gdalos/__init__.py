from osgeo.osr import OAMS_TRADITIONAL_GIS_ORDER
from osgeo_utils.auxiliary.osr_util import set_default_axis_order
set_default_axis_order(OAMS_TRADITIONAL_GIS_ORDER)

version = (0, 60, 2)

__package_name__ = "gdalos"
__version__ = '.'.join(str(v) for v in version)
__author__ = "Idan Miara, Ben Avrahami"
__author_email__ = "idan@miara.com"
__license__ = "MIT"
__url__ = r"https://github.com/talos-gis/gdalos"
__description__ = "a simple gdal translate/warp/addo python wrapper for raster batch processing"
