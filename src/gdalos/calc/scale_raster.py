import math
import numpy as np
from functools import partial
import gdal
from gdalos.calc import gdal_calc, gdal_numpy
from gdalos import gdalos_util
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
    if out_ndv in [None, ...]:
        out_ndv = 0
    ret = np.full_like(arr, out_ndv, dtype=dtype)
    np.multiply(arr, factor, out=ret, casting='unsafe')
    if in_ndv not in [None, ...]:
        ret[arr == in_ndv] = out_ndv

    return ret


def scale_raster(filename_or_ds, d_path, gdal_dt=gdal.GDT_Int16,
                 hide_nodata=False, in_ndv=..., out_ndv=..., scale=0, creation_options_list=None, **kwargs):
    ds = gdalos_util.open_ds(filename_or_ds)
    if in_ndv is ...:
        in_ndv = gdalos_util.get_nodatavalue(ds)
    if out_ndv is ... and in_ndv is not None:
        # out_ndv = None if in_ndv is None else gdal_calc.DefaultNDVLookup[gdal_dt]
        out_ndv = gdal_calc.DefaultNDVLookup[gdal_dt]
    np_dtype = gdal_numpy.gdal_dt_to_np_dt[gdal_dt]
    if not scale or scale is ...:
        scale = autoscale(ds.GetRasterBand(1), np_dtype)
    f = partial(scale_np_array, factor=1 / scale, in_ndv=in_ndv, out_ndv=out_ndv, dtype=np_dtype)
    calc_expr = 'f(x)'
    calc_kwargs = dict(x=ds)
    user_namespace = dict(f=f)
    creation_options_list = creation_options_list or gdalos_util.get_creation_options()

    ds = gdal_calc.Calc(
        calc_expr, outfile=str(d_path), hideNodata=hide_nodata, NoDataValue=out_ndv, return_ds=True, type=gdal_dt,
        user_namespace=user_namespace, creation_options=creation_options_list, **kwargs, **calc_kwargs)

    for i in range(ds.RasterCount):
        ds.GetRasterBand(i + 1).SetScale(scale)

    return ds
