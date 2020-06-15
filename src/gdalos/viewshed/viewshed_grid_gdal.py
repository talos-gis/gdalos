from gdalos import gdalos_trans
from gdalos import GeoRectangle
from pathlib import Path
from copy import copy
from gdalos.viewshed.viewshed_grid_params import ViewshedGridParams


def calc_extent(oxy, grid_range, interval, md, frame):
    # i is for x-y;
    # j is for min and max values of the grid
    # k is for the sign (to subtract or to add) the max_range
    minmax = [oxy[i] + grid_range[j] * interval + k * (md + frame) for i in (0, 1) for j, k in zip((0, -1), (-1, 1))]
    full_extent = GeoRectangle.from_min_max(*minmax)
    return full_extent


def viewshed_run(vp: ViewshedGridParams, output_path, input_filename):
    import gdal
    from gdalos import gdalos_util

    ds = gdalos_util.open_ds(input_filename)
    band: gdal.Band = ds.GetRasterBand(1)

    if band is None:
        raise Exception('band number out of range')

    arr = vp.get_array()
    for vp1 in arr:
        filename = output_path / (vp1.name + '.tif')

        vals = vp1.get_as_gdal_params()
        dest = gdal.ViewshedGenerate(band, 'GTiff', str(filename), None, **vals)

        if dest is None:
            raise Exception('error occurred')

        del dest


if __name__ == "__main__":
    dir_path = Path('/home/idan/maps')
    input_filename = dir_path / Path('srtm1_x35_y32.tif')
    output_path = dir_path / Path('comb')
    srtm_filename = Path(output_path) / Path('srtm1_36_sample.tif')

    vp = ViewshedGridParams()

    make_map = True
    if make_map:
        frame = 500
        full_extent = calc_extent(vp.oxy, vp.grid_range, vp.interval, vp.max_r, frame)
        gdalos_trans(input_filename, extent=full_extent, warp_CRS=36, extent_in_4326=False, out_filename=srtm_filename)

    viewshed_run(vp, output_path, srtm_filename)
