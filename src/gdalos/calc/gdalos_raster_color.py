import os
import tempfile
import gdal
from gdalos.gdalos_color import ColorPalette
from gdalos.calc import gdal_calc
from functools import partial
import numpy as np
import copy
from pathlib import Path
from gdalos.calc.discrete_mode import DiscreteMode
from gdalos import gdalos_util
from gdalos.calc import gdal_to_czml


def cont2discrete_array(arr, values, discrete_mode: DiscreteMode, dtype=np.uint8):
    """
    input: continues np array [float | int]
    output: uint8 np array with discrete values
    """
    enumerated_values = list(enumerate(sorted(values)))
    if discrete_mode == DiscreteMode.up:
        # 0 - equal or below first value
        # 1 - above first
        # 2 - above second
        # n - above n
        ret = np.full_like(arr, len(values)-1, dtype=dtype)
        # iterate values from high to low
        for i, val in reversed(enumerated_values[:-1]):
            ret[(arr <= val)] = i
    elif discrete_mode == DiscreteMode.down:
        # 0 - below first value
        # 1 - below second
        # 2 - below third
        # n - above n-1
        ret = np.full_like(arr, 0, dtype=dtype)
        # iterate values from low to high
        for i, val in list(enumerated_values[1:]):
            ret[(arr >= val)] = i
    else:
        raise Exception('unsupported mode {}'.format(discrete_mode))
    return ret


def gdalos_raster_color(filename_or_ds: gdal.Dataset,
                        color_palette: ColorPalette,
                        out_filename: str=None, output_format: str = None,
                        discrete_mode=DiscreteMode.interp) -> gdal.Dataset:
    ds = gdalos_util.open_ds(filename_or_ds)

    if color_palette is None:
        return ds
    if not output_format:
        output_format = 'GTiff' if out_filename else 'MEM'

    if not out_filename:
        out_filename = ''
        if output_format != 'MEM':
            raise Exception('output filename is None')
    if discrete_mode in [DiscreteMode.interp, DiscreteMode.near]:
        temp_color_filename = color_palette.write_color_file()
        dem_options = {
            'options': ['-nearest_color_entry'] if discrete_mode == DiscreteMode.near else [],
            'addAlpha': True,
            'format': output_format,
            'processing': 'color-relief',
            'colorFilename': str(temp_color_filename)}
        ds = gdal.DEMProcessing(str(out_filename), ds, **dem_options)
        os.remove(temp_color_filename)
    elif discrete_mode in [DiscreteMode.up, DiscreteMode.down]:
        color_palette_copy = copy.deepcopy(color_palette)
        if color_palette.has_percents:
            min_max = gdalos_util.get_raster_min_max(ds)
            color_palette_copy.apply_percent(*min_max)

        values = []
        for key in color_palette_copy.pal.keys():
            if not isinstance(key, str):
                values.append(key)
        if not values:
            raise Exception('no absolute values found in the palette')

        f = partial(cont2discrete_array, values=values, discrete_mode=discrete_mode)
        calc_expr = 'f(x)'

        calc_kwargs = dict(x=ds)
        user_namespace = dict(f=f)
        color_palette_copy.to_serial_values()
        color_table = color_palette_copy.get_color_table()

        meta = gdal_to_czml.make_czml_description(color_palette_copy)

        ds = gdal_calc.Calc(
            calc_expr, type=gdal.GDT_Byte, outfile=str(out_filename), format=output_format,
            color_table=color_table, return_ds=True, overwrite=True,
            user_namespace=user_namespace, **calc_kwargs)

        ds.SetMetadataItem(gdal_to_czml.czml_metadata_name, meta)
    if ds is None:
        raise Exception('fail to color')
    return ds


def test_main(path, color_palette):
    for mode in DiscreteMode:
        outfile = path.with_suffix('.{}.tif'.format(mode))
        gdalos_raster_color(path, color_palette, out_filename=outfile, discrete_mode=mode)


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


def test_dem_color():
    script_dir = os.path.dirname(os.path.realpath(__file__))
    root_data = os.path.join(script_dir, r'../../data/sample')
    color_palette_filename = os.path.join(root_data, r'color_files/percents.txt')
    raster_filename = os.path.join(root_data, r'maps/srtm1_x35_y32.tif')
    ds = gdalos_util.open_ds(raster_filename)
    out_filename = tempfile.mktemp(suffix='.tif')

    color_palette = ColorPalette()
    color_palette.read_color_file(color_palette_filename)

    ds = gdalos_raster_color(
        filename_or_ds=ds,
        out_filename=out_filename,
        color_palette=color_palette,
        discrete_mode=DiscreteMode.interp,
        output_format='GTiff')

    print(out_filename)
    print(color_palette)


if __name__ == '__main__':
    # test_dtm()
    test_f1()
