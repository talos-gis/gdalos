import sys
my_scripts_dir = r'd:\dev\Scripts'
sys.path.append(my_scripts_dir)

from gdalos import gdalos_trans, OvrType
from gdalos import GeoRectangle

my_extent = GeoRectangle.from_min_max(5, 85, 30, 40)


def test_srtm():
    srtm_path = r'd:\maps\srtm.tif'
    [gdalos_trans(path=srtm_path, extent=my_extent, warp_CRS=warp_CRS, dst_nodatavalue=0, hide_NDV=True) for warp_CRS in [None, 32, 34]]


def test_rgb():
    my_maps = [
        r'c:\Maps\ortho_map.tif',
        r'c:\Maps\osm_map.tif'
    ]
    [gdalos_trans(path, extent=None, lossy=True, skip_if_exist=False, resample_method='average', alpha=0) for path in my_maps]


if __name__ == '__main__':
    test_srtm()
    test_rgb()
    pass
