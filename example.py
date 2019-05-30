from gdalos import gdalos_trans
from gdalos import GeoRectangle, OvrType


def test_srtm():
    my_extent = GeoRectangle.from_min_max(5, 85, 30, 40)
    srtm_path = r'd:\maps\srtm.tif'
    warp_CRS = [None, 32, 34]:
    gdalos_trans(filename=srtm_path, extent=my_extent, warp_CRS=warp_CRS, dst_nodatavalue=0,
                 hide_nodatavalue=True, ovr_type=OvrType.create_external_auto)


if __name__ == "__main__":
    test_srtm()
