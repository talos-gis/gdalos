import math
import numpy as np
from functools import partial
import gdal
from pathlib import Path
from gdalos.calc import gdal_calc, gdal_numpy
from gdalos import gdalos_util, gdalos_trans, GeoRectangle
from numbers import Real


def autoscale(bnd, np_dtype, possible_scale_values=(0.1, 0.15, 0.2, 0.25, 0.3)):
    bnd.ComputeStatistics(0)
    max_band_val = bnd.GetMaximum()
    max_dt_value = np.iinfo(np_dtype).max
    scale = max_band_val / max_dt_value
    if possible_scale_values is None:
        scale = math.ceil(scale*100)/100
    else:
        for v in possible_scale_values:
            if scale <= v:
                scale = v
                break
    return scale


def scale_np_array(arr, factor: Real, in_ndv, out_ndv, dtype):
    """
        input: arr: numpy array, factor
        returns a numpy array = arr*factor with a given dtype.
    """

    # ret = np.full_like(arr, out_ndv, dtype=dtype)
    # ret[arr != in_ndv] = dtype(arr * scale)

    ret = np.full_like(arr, out_ndv, dtype=dtype)
    np.multiply(arr, factor, out=ret, casting='unsafe')
    ret[arr == in_ndv] = out_ndv

    return ret


def scale_raster(filename_or_ds, d_path, gdal_dt=gdal.GDT_Int16,
                 hide_nodata = True, in_ndv=..., out_ndv=..., scale=0, **kwargs):
    ds = gdalos_util.open_ds(filename_or_ds)
    if in_ndv is ...:
        in_ndv = gdalos_util.get_nodatavalue(ds)
    if out_ndv is ...:
        out_ndv = gdal_calc.DefaultNDVLookup[gdal_dt]
    np_dtype = gdal_numpy.gdal_dt_to_np_dt[gdal_dt]
    if not scale:
        scale = autoscale(ds.GetRasterBand(1), np_dtype)
    f = partial(scale_np_array, factor=1 / scale, in_ndv=in_ndv, out_ndv=out_ndv, dtype=np_dtype)
    calc_expr = 'f(x)'
    calc_kwargs = dict(x=ds)
    user_namespace = dict(f=f)
    creation_options = gdalos_util.get_creation_options()

    ds = gdal_calc.Calc(
        calc_expr, outfile=str(d_path), hideNodata=hide_nodata, NoDataValue=out_ndv,
        overwrite=True, return_ds=True,
        user_namespace=user_namespace, creation_options=creation_options, **kwargs, **calc_kwargs)

    for i in range(ds.RasterCount):
        ds.GetRasterBand(i + 1).SetScale(scale)

    return ds


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
