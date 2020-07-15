import gdal
from gdalos.gdalos_color import ColorPalette
from gdalos.calc import gdal_calc
from enum import Enum
from functools import partial
import numpy as np
import copy
from gdalos.gdalos_util import open_ds
from pathlib import Path


class DiscreteMode(Enum):
    up = 1
    down = 2


def cont2discrete_array(arr, values, mode: DiscreteMode, dtype=np.uint8):
    """
    input: continues np array [float | int]
    output: uint8 np array with discrete values
    """
    enumerated_values = list(enumerate(sorted(values)))
    if mode == DiscreteMode.up:
        # 0 - equal or below first value
        # 1 - above first
        # 2 - above second
        # n - above n
        ret = np.full_like(arr, len(values)-1, dtype=dtype)
        # iterate values from high to low
        for i, val in reversed(enumerated_values[:-1]):
            ret[(arr <= val)] = i
    else:
        # 0 - below first value
        # 1 - below second
        # 2 - below third
        # n - above n-1
        ret = np.full_like(arr, 0, dtype=dtype)
        # iterate values from low to high
        for i, val in list(enumerated_values[1:]):
            ret[(arr >= val)] = i
    return ret


def cont2discrete(filename_or_ds: gdal.Dataset, pal: ColorPalette, outfile=None, mode: DiscreteMode=DiscreteMode.down) -> gdal.Dataset:
    values = list(pal.pal.keys())
    try:
        values.remove('np')
    except:
        pass
    f = partial(cont2discrete_array, values=values,  mode=mode)
    calc_expr = 'f(x)'

    filename_or_ds = open_ds(filename_or_ds)
    calc_kwargs = dict(x=filename_or_ds)
    user_namespace = dict(f=f)
    serial_pal = copy.deepcopy(pal)
    serial_pal.to_serial_values()
    color_table = serial_pal.get_color_table()
    ds = gdal_calc.Calc(
        calc_expr, type=gdal.GDT_Byte, outfile=str(outfile), color_table=color_table, return_ds=True, overwrite=True,
        user_namespace=user_namespace, **calc_kwargs)

    return ds


def test_main(path, pal):
    for mode in DiscreteMode:
        outfile = path.with_suffix('.{}.tif'.format(mode))
        cont2discrete(path, pal, outfile=outfile, mode=mode)


def test_dtm():
    path = Path(r'd:\dev\gis\talos_wps\data\sample\maps\srtm1_x35_y32.tif')
    color_file = r'sample\color_files\gradient\rainbow.txt'
    pal = ColorPalette()
    pal.read_color_file(color_file)
    test_main(path, pal)


def test_f1():
    path = Path(r'd:\dev\gis\talos_wps\data\sample\maps\f1.tif')
    talos_pal = r'100;4;0;0;500;0;1;1;0;|;$CC000080;0;3;2|;$CC00FFFF;0;3;2|;$CC00FF00;0;3;2|;$CCFFFF00;0;3;2'
    pal = ColorPalette()
    pal.read_talos_palette(talos_pal)
    test_main(path, pal)


if __name__ == '__main__':
    # test_dtm()
    test_f1()
