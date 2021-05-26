import timeit
from typing import Tuple, Optional, Union

from osgeo import osr
from pyproj.geod import Geod, GeodIntermediateReturn
import numpy as np

from osgeo_utils.auxiliary.util import PathOrDS
from osgeo_utils.samples.gdallocationinfo import gdallocationinfo

g_wgs84 = Geod(ellps='WGS84')


def geod_profile(filename_or_ds: PathOrDS, band_nums=None, srs=4326, ovr_idx: Optional[Union[int, float]] = None,
                 g: Geod = None, only_geod: bool = False,
                 initial_idx: int = 0, terminus_idx: int = 0, **kwargs) -> \
        Tuple[GeodIntermediateReturn, Optional[np.ndarray]]:
    if g is None:
        g = g_wgs84
    geod_res = g.inv_intermediate(initial_idx=initial_idx, terminus_idx=terminus_idx, **kwargs)
    lons, lats = geod_res.lons, geod_res.lats
    if only_geod:
        raster_res = None
    else:
        pixels, lines, raster_res = gdallocationinfo(
            filename_or_ds, band_nums=band_nums, x=lons, y=lats, srs=srs,
            inline_xy_replacement=False, ovr_idx=ovr_idx,
            axis_order=osr.OAMS_TRADITIONAL_GIS_ORDER)
    return geod_res, raster_res


def test_profile(do_print=False, **kwargs):
    filename = r'd:\Maps\w84geo\dtm_SRTM1_hgt_ndv0.cog.tif.new.cog.tif'
    boston_lat = 42. + (15. / 60.)
    boston_lon = -71. - (7. / 60.)
    portland_lat = 45. + (31. / 60.)
    portland_lon = -123. - (41. / 60.)
    lon1 = boston_lon
    lat1 = boston_lat
    lon2 = portland_lon
    lat2 = portland_lat

    filename = r"d:\Maps\w84u36\dtm\dtm_SRTM1_hgt_ndv0.w84u36.[31.0, -31.0].x[26.84,40.05]_y[21.8,40.48].scale_0.1.cog.tif"
    lon1 = 35
    lat1 = 32
    lon2 = 35
    lat2 = 33

    g = Geod(ellps='WGS84')
    geod_res, alts = geod_profile(
        filename, g=g,
        lon1=lon1, lat1=lat1, lon2=lon2, lat2=lat2, **kwargs)
    lons, lats = geod_res.lons, geod_res.lats
    if do_print:
        for x, y, z in list(zip(lons, lats, alts[0])):
            print(f"{x:8.3f} {y:8.3f} {z:12.3f}")


if __name__ == '__main__':
    do_time = False
    bench_count = 1
    repeat_count = 10
    npts = 10
    ellps = 'WGS84'
    if do_time:
        t = timeit.timeit(
            'test_profile()',
            setup='from __main__ import test_profile',
            number=repeat_count)
        print(t)
    else:
        test_profile(npts=npts, do_print=True)
