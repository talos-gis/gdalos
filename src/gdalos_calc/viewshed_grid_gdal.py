from gdalos import gdalos_trans
from gdalos import GeoRectangle
from pathlib import Path
from gdalos_calc import viewshed_params


def calc_extent(center, grid_range, interval, md, frame):
    # i is for x-y;
    # j is for min and max values of the grid
    # k is for the sign (to subtract or to add) the max_range
    minmax = [center[i] + grid_range[j] * interval + k * (md + frame) for i in (0, 1) for j, k in zip((0, -1), (-1, 1))]
    full_extent = GeoRectangle.from_min_max(*minmax)
    return full_extent


def viewshed_run(md, interval, grid_range, center, oz, tz, output_path, input_filename):
    import gdal
    from gdalos import gdal_helper

    ds = gdal_helper.open_ds(input_filename)
    band: gdal.Band = ds.GetRasterBand(1)

    if band is None:
        raise Exception('band number out of range')

    st_seen     = 5
    st_seenbut  = 4
    st_hidbut   = 3
    st_hidden   = 2
    st_nodtm    = 1
    st_nodata   = 0
    
    vv = st_seen
    iv = st_hidden
    ndv = -1
    cc = 0
    ov = 0
    for i in grid_range:
        for j in grid_range:
            ox = center[0] + i * interval
            oy = center[1] + j * interval

            name = '{}_{}'.format(i, j)
            filename = output_path / (name + '.tif')

            dest = gdal.ViewshedGenerate(band, 'GTIFF', filename, None,
                                         ox, oy, oz, tz, vv, iv, ov, ndv, cc,
                                         mode=2,
                                         maxDistance=md)

            if dest is None:
                raise Exception('error occurred')

            del dest


if __name__ == "__main__":
    dir_path = Path('/home/idan/maps')
    input_filename = dir_path / Path('srtm1_x35_y32.tif')
    output_path = dir_path / Path('comb')
    srtm_filename = Path(output_path) / Path('srtm1_36_sample.tif')

    vp = viewshed_params.get_test_viewshed_params()

    make_map = True
    if make_map:
        frame = 500
        full_extent = calc_extent(vp.center, vp.grid_range, vp.interval, vp.md, frame)
        gdalos_trans(input_filename, extent=full_extent, warp_CRS=36, extent_in_4326=False, out_filename=srtm_filename)

    viewshed_run(vp.md, vp.interval, vp.grid_range, vp.center, vp.oz, vp.tz, output_path, srtm_filename)
