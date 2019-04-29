import os

from gdalos import gdalos_trans
from gdalos import GeoRectangle, OvrType

my_extent = GeoRectangle.from_min_max(5, 85, 30, 40)

bases = ('world.tiff', 'middle_east.tiff', 'zion.tiff', 'israel.tiff')

def test_srtm():
    srtm_path = r'd:\maps\srtm.tif'
    [gdalos_trans(path=srtm_path, extent=my_extent, warp_CRS=warp_CRS, dst_nodatavalue=0, hide_nodatavalue=True) for warp_CRS in [None, 32, 34]]
trans_osm = [
    *(os.path.join(r'D:\Maps\OSM.tif\wms_eox', b) for b in bases),
    *(os.path.join(r'D:\Maps\OSM.tif\mecr_tiles', b) for b in bases)
]
extent_me = GeoRectangle.from_min_max(20, 80, 20, 40)

[gdalos_trans(path, lossy=True, skip_if_exists=True, ovr_type=OvrType.translate_existing, extent=extent_me, warp_CRS=36)
 for path in trans_osm]