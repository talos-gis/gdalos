import numpy as np
from gdalos.viewshed.viewshed_params import viewshed_thresh, viewshed_ndv, viewshed_comb_ndv, viewshed_comb_multi_val
from gdalos.calc.gdal_calc import AlphaList


def get_by_index(a, index=0):
    """
    this is mainly for testing
    """
    return a[index]


def vs_max(a):
    """
    max value of each pixel
    """
    concatenate = np.stack(a)
    ret = concatenate.max(axis=0)
    return ret


def vs_count(a, threshold=viewshed_thresh):
    """
    count non zero values
    """
    concatenate = np.stack(a)
    a_bools = concatenate > threshold
    ret = a_bools.sum(axis=0, dtype=np.uint8)
    # ret = np.count_nonzero(a_bools, axis=0)  # also works
    return ret


def vs_count_z(a, threshold=viewshed_thresh, in_ndv=viewshed_ndv, out_ndv=viewshed_comb_ndv):
    """
    count non zero values considering ndv values
    """
    concatenate = np.stack(a)
    a_bools = concatenate > threshold
    ret = a_bools.sum(axis=0, dtype=np.uint8)

    # finding all indices that all vales are ndv and set the output to ndv
    a_bools = concatenate != in_ndv
    non_ndv = a_bools.sum(axis=0, dtype=np.uint8)
    ret[non_ndv == 0] = out_ndv

    return ret


def vs_unique(a, threshold=viewshed_thresh, multiple_nz=viewshed_comb_multi_val, all_zero=viewshed_comb_ndv):
    """
    returns indices of rasters with unique values
    """
    nz_count = vs_count(a, threshold)

    ret = np.full_like(a[0], all_zero)
    ret[nz_count > 1] = multiple_nz
    singular = nz_count == 1
    for i, arr in enumerate(a):
        ret[(arr != 0) & singular] = i
    return ret


def unique_bool(a, multiple_nz=viewshed_comb_multi_val, all_zero=viewshed_comb_ndv):
    a = [np.array(x) for x in a]
    concatenate = np.stack(a)
    nz_count = np.count_nonzero(concatenate, axis=0)
    ret = np.full_like(a[0], all_zero)
    ret[nz_count > 1] = multiple_nz
    singular = nz_count == 1
    for i, arr in enumerate(a):
        ret[(arr != 0) & singular] = i
    return ret


def make_calc_with_operand(filenames, alpha_pattern, operand, **kwargs):
    calc = None
    for filename, alpha in zip(filenames, AlphaList):
        kwargs[alpha] = filename
        alpha1 = alpha_pattern.format(alpha)
        if calc is None:
            calc = alpha1
        else:
            calc = '{}{}{}'.format(calc, operand, alpha1)
    return calc, kwargs


def make_calc_with_func(filenames, alpha_pattern, func_name, **kwargs):
    all_vals = 'a'
    alpha1 = alpha_pattern.format('x')
    calc = '{}({} for x in a)'.format(func_name, alpha1)
    kwargs[all_vals] = filenames
    return calc, kwargs