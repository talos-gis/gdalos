import os


from gdalos import gdalos_trans
from gdalos import GeoRectangle, OvrType

my_extent = GeoRectangle.from_min_max(5, 85, 30, 40)

bases = ('world.tiff', 'middle_east.tiff', 'zion.tiff', 'israel.tiff')

trans_osm = [
    *(os.path.join(r'D:\Maps\OSM.tif\wms_eox', b) for b in bases),
    *(os.path.join(r'D:\Maps\OSM.tif\mecr_tiles', b) for b in bases)
]
extent_me = GeoRectangle.from_min_max(20, 80, 20, 40)

[gdalos_trans(path, lossy=True, skip_if_exist=True, ovr_type=OvrType.existing, extent=extent_me, warp_CRS=warp_CRS)
 for path in trans_osm for warp_CRS in [None, 36]]
