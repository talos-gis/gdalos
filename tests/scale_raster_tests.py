from pathlib import Path

from gdalos.gdalos_trans import gdalos_trans, GeoRectangle
from gdalos.calc.scale_raster import scale_raster


def make_test_input():
    input_file = r'd:\Maps\w84u36\dtm\SRTM1_hgt.x[27.97,37.98]_y[27.43,37.59].cog.tif'
    extent = GeoRectangle.from_min_max(670000, 700000, 3600000, 3630000)
    gdalos_trans(input_file, extent=extent, extent_in_4326=False)


def make_test_input2():
    input_file = Path(r'd:\Maps\w84geo\dtm\SRTM1_hgt.tif.new.cog.tif')
    # input_file = r'd:\Maps\w84u36\dtm\SRTM1_hgt.x[27.97,37.98]_y[27.43,37.59].cog.tif'
    extent = GeoRectangle.from_min_max(34, 35, 32, 33)
    gdalos_trans(input_file, warp_srs=36, extent=extent, extent_in_4326=True, out_path=r'd:\Maps.temp', out_path_with_src_folders=False)


def test_scale_raster(input_file):
    scale = 0
    out_dst = Path(input_file).with_suffix('.scale_{}.tif'.format(scale))
    scale_raster(input_file, out_dst, scale=scale)
    gdalos_trans(out_dst)
    return out_dst


if __name__ == '__main__':
    # make_test_input2()
    input_file = Path(r'd:\Maps\w84u36\dtm\SRTM1_hgt.x[27.97,37.98]_y[27.43,37.59].cog.tif.x[34.8,35.16]_y[32.51,32.81].cog.tif')
    # input_file = Path(r'd:\Maps.temp\SRTM1_hgt.tif.new.cog.tif.w84u36.[31.0, -31.0].x[33.99,35.06]_y[31.99,33.05].cog.tif')
    # input_file = Path(r'd:\Maps\w84u36\dtm\SRTM1_hgt.x[27.97,37.98]_y[27.43,37.59].cog.tif')
    # input_file = r"d:\Maps.raw\osm\ready\w84u36\SRTM1_hgt_ndv0.cog.tif.new.cog.tif.w84u36.[31.0, -31.0].x[26.85,39.55]_y[19.92,40.4].cog.tif"
    test_scale_raster(input_file)
