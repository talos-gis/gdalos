# backwards compatibility
import functools

from osgeo_utils.auxiliary.osr_util import *
from gdalos.backports.osr_util2 import *
from gdalos.backports.osr_utm_util import *
from gdalos.talos_osr import *
from osgeo_utils.auxiliary import osr_util

get_srs_from_ds = get_srs
get_proj4_string = get_proj_string
get_srs_pj_from_ds = get_srs_pj
get_srs_pj_from_epsg = get_srs_pj
proj_is_equivalent = are_srs_equivalent
get_zone_center = get_utm_zone_center
get_zone_by_lon = get_utm_zone_by_lon
get_datum_and_zone_from_projstring = get_datum_and_zone_from_srs


if __name__ == '__main__':
    from osgeo_utils.auxiliary import osr_util
    print(osr_util._default_axis_order)
    pj4326 = get_srs_pj(4326)
