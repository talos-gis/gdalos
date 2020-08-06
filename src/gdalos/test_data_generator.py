import gdal
import numpy as np
from gdalos import gdalos_color, gdalos_trans
from gdalos.gdalos_color import ColorPalette


def test_data_generator(filename, levels=10, of='GTiff', color_palette: ColorPalette=...):
    driver = gdal.GetDriverByName(of)
    gdal_dtype = gdal.GDT_Byte
    np_dtype = np.uint8

    if color_palette is ...:
        color_palette = ColorPalette.get_xkcd_palette()
    color_table = gdalos_color.get_color_table(color_palette)

    for i in range(levels):
        size = 1 << levels-1-i
        shape = (size, size)
        filename_i = filename + '.ovr' * i
        ds = driver.Create(filename_i, xsize=shape[0], ysize=shape[1], bands=1, eType=gdal_dtype)
        pixel_size = 1 << i
        gt = [0, pixel_size, 0, 0, 0, -pixel_size]
        ds.SetGeoTransform(gt)
        bnd = ds.GetRasterBand(1)
        bnd.SetRasterColorTable(color_table)
        bnd.SetRasterColorInterpretation(gdal.GCI_PaletteIndex)
        arr = np.full(shape, i, np_dtype)
        bnd.WriteArray(arr, 0, 0)
        ds.FlushCache()


if __name__ == '__main__':
    filename = r'd:\Maps.temp\test.tif'
    test_data_generator(filename=filename)
    gdalos_trans(filename, overwrite=True)
