import os
import tempfile
from typing import Optional, Sequence, List, Union
from osgeo import gdal, ogr, osr
from gdalos.rectangle import GeoRectangle
from gdalos.calc import gdal_to_czml
from gdalos.gdalos_color import ColorPalette, get_file_from_strings
from gdalos import gdalos_util

# def get_named_temporary_filenme(suffix='', dir_name=''):
#     filename = next(tempfile._get_candidate_names())+suffix
#     if dir_name is None:
#         return filename
#     else:
#         if dir_name=='':
#             dir_name = tempfile._get_default_tempdir()
#         return os.path.join(dir_name, filename)


def gdal_crop(ds: gdal.Dataset, out_filename: str, output_format: str = 'MEM',
              extent: Optional[GeoRectangle] = None,
              cutline: Optional[Union[str, List[str]]] = None,
              common_options: dict = None):
    common_options = dict(common_options or dict())
    translate_options = {}
    warp_options = {}
    temp_filename = None

    if cutline is None:
        if extent is None:
            return ds
        # -projwin minx maxy maxx miny (ulx uly lrx lry)
        translate_options['projWin'] = extent.lurd
        # -te minx miny maxx maxy
    else:
        if extent is not None:
            warp_options['outputBounds'] = extent.ldru
        warp_options['cropToCutline'] = extent is None
        warp_options['dstNodata'] = -32768
        # warp_options['dstAlpha'] = True

        if isinstance(cutline, str):
            cutline_filename = cutline
        elif isinstance(cutline, Sequence):
            temp_filename = tempfile.mktemp(suffix='.gpkg')
            cutline_filename = temp_filename
            gdalos_util.wkt_write_ogr(cutline_filename, cutline, of='GPKG')
        warp_options['cutlineDSName'] = cutline_filename
    # else:
    #     raise Exception("extent is unknown {}".format(extent))

    common_options['format'] = output_format
    if warp_options:
        ds = gdal.Warp(str(out_filename), ds, **common_options, **warp_options)
    else:
        ds = gdal.Translate(str(out_filename), ds, **common_options, **translate_options)
    if temp_filename is not None:
        os.remove(temp_filename)
    return ds


def make_czml_description(pal:ColorPalette, process_palette):
    if pal:
        if process_palette >= 2:
            return ' '.join(['{}:{}'.format(
                ColorPalette.format_number(x),
                ColorPalette.format_color(c)) for x, c in pal.pal.items()])
        else:
            return ' '.join([ColorPalette.format_number(x) for x in pal.pal.keys()])
    else:
        return None


def czml_gdaldem_crop_and_color(ds: gdal.Dataset, process_palette, czml_output_filename: str, **kwargs):
    ds, pal = gdaldem_crop_and_color(ds=ds, process_palette=process_palette, **kwargs)
    if ds is None:
        raise Exception('fail to color')
    if czml_output_filename is not None:
        description = make_czml_description(pal, process_palette)
        gdal_to_czml.gdal_to_czml(ds, name=czml_output_filename, out_filename=czml_output_filename, description=description)
    return ds


def gdaldem_crop_and_color(ds: gdal.Dataset,
                           out_filename: str, output_format: str = 'GTiff',
                           extent: Optional[GeoRectangle] = None,
                           cutline: Optional[Union[str, List[str]]] = None,
                           color_palette: Optional[Union[str, Sequence[str]]] = None,
                           process_palette=2,
                           common_options: dict = None):
    do_color = color_palette is not None
    do_crop = (extent or cutline) is not None

    if out_filename is None:
        out_filename = ''
        if output_format != 'MEM':
            raise Exception('output filename is None')

    if do_crop:
        output_format_crop = 'MEM' if do_color else output_format
        ds = gdal_crop(ds, out_filename,
                       output_format=output_format_crop, extent=extent, cutline=cutline,
                       common_options=common_options)
        if ds is None:
            raise Exception('fail to crop')

    pal = None
    if process_palette:
        bnd = ds.GetRasterBand(1)
        bnd.ComputeStatistics(0)
        min_val = bnd.GetMinimum()
        max_val = bnd.GetMaximum()

    if do_color:
        color_filename, temp_color_filename = get_file_from_strings(color_palette)
        if not process_palette:
            pal = None
        else:
            pal = ColorPalette()
            pal.read(color_filename)
            pal.apply_percent(min_val, max_val)
            # color_palette_stats(color_filename, min_val, max_val, process_palette)
        dem_options = {
            'addAlpha': True,
            'format': output_format,
            'processing': 'color-relief',
            'colorFilename': color_filename}
        ds = gdal.DEMProcessing(out_filename, ds, **dem_options)
        if temp_color_filename is not None:
            os.remove(temp_color_filename)
        if ds is None:
            raise Exception('fail to color')
    # else:
    #     stats = [min_val, max_val]
    return ds, pal


def get_wkt_list(filename):
    ds = ogr.Open(filename, 0)
    layer = ds.GetLayer()
    wkt_list = []
    for feature in layer:
        geom = feature.GetGeometryRef()
        wkt_list.append(geom.ExportToWkt())
    return wkt_list


def read_list(filename):
    return [line.rstrip('\n') for line in open(filename)]


if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.realpath(__file__))
    root_data = os.path.join(script_dir, r'../../data/sample')
    shp_filename = os.path.join(root_data, r'shp/poly.shp')
    color_palette_filename = os.path.join(root_data, r'color_files/percents.txt')
    wkt_list = get_wkt_list(shp_filename)
    color_palette = read_list(color_palette_filename)
    raster_filename = os.path.join(root_data, r'maps/srtm1_x35_y32.tif')
    ds = gdalos_util.open_ds(raster_filename)
    out_filename = tempfile.mktemp(suffix='.tif')
    ds, pal = gdaldem_crop_and_color(
        ds=ds,
        out_filename=out_filename,
        cutline=wkt_list,
        color_palette=color_palette,
        output_format='GTiff')
    print(out_filename)
    print(pal)
