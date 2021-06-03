import os
import tempfile
from typing import Optional, Sequence, List, Union
from osgeo import gdal, ogr, osr
from gdalos.rectangle import GeoRectangle
from gdalos.calc import gdal_to_czml
from gdalos.gdalos_color import ColorPalette, get_file_from_strings
from gdalos import gdalos_util
from gdalos.calc.gdalos_raster_color import DiscreteMode, gdalos_raster_color
from gdalos.backports.ogr_utils import ogr_create_geometries_from_wkt

import copy


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
            ogr_create_geometries_from_wkt(cutline_filename, cutline, of='GPKG', srs=4326)
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


def czml_gdaldem_crop_and_color(
        ds: gdal.Dataset,
        out_filename: str = None, output_format: str = None,
        czml_output_filename: str = None,
        extent: Optional[GeoRectangle] = None,
        cutline: Optional[Union[str, List[str]]] = None,
        color_palette: ColorPalette = None,
        discrete_mode=DiscreteMode.interp,
        process_palette=None,
        common_options: dict = None):

    do_color = color_palette is not None
    output_format_crop = 'MEM' if do_color else output_format
    out_filename_crop = '' if do_color else out_filename

    ds = gdalos_crop(
        ds, out_filename=out_filename_crop, output_format=output_format_crop,
        extent=extent, cutline=cutline,
        common_options=common_options)

    min_max = gdalos_util.get_raster_min_max(ds) if process_palette and color_palette.has_percents else None

    if do_color:
        ds = gdalos_raster_color(
            ds, color_palette=color_palette,
            out_filename=out_filename, output_format=output_format,
            discrete_mode=discrete_mode)

    if ds is None:
        raise Exception('fail to color')
    if czml_output_filename is not None:
        if min_max and None not in min_max:
            color_palette_copy = copy.deepcopy(color_palette)
            color_palette_copy.apply_percent(*min_max)
        else:
            color_palette_copy = color_palette
        meta = gdal_to_czml.make_czml_description(color_palette_copy, process_palette)
        ds.SetMetadataItem(gdal_to_czml.czml_metadata_name, meta)

        gdal_to_czml.gdal_to_czml(ds, name=czml_output_filename, out_filename=czml_output_filename)
    return ds


def gdalos_crop(ds: gdal.Dataset,
                out_filename: str = '', output_format: str = None,
                extent: Optional[GeoRectangle] = None,
                cutline: Optional[Union[str, List[str]]] = None,
                common_options: dict = None):
    if (extent or cutline) is None:
        return ds

    if not output_format:
        output_format = 'GTiff' if out_filename else 'MEM'

    if not out_filename:
        out_filename = ''
        if output_format != 'MEM':
            raise Exception('output filename is None')

    ds = gdal_crop(ds, out_filename,
                   output_format=output_format, extent=extent, cutline=cutline,
                   common_options=common_options)
    if ds is None:
        raise Exception('fail to crop')

    return ds


# def gdaldem_crop_and_color(ds: gdal.Dataset,
#                            out_filename: str = None, output_format: str = None,
#                            extent: Optional[GeoRectangle] = None,
#                            cutline: Optional[Union[str, List[str]]] = None,
#                            color_palette: ColorPalette = None,
#                            discrete_mode=DiscreteMode.interp,
#                            get_min_max=None,
#                            common_options: dict = None):
#     ds = gdalos_crop(
#         ds, out_filename=out_filename, output_format=output_format,
#         extent=extent, cutline=cutline,
#         common_options=common_options)
#
#     min_max = get_raster_min_max(ds) if get_min_max else None
#
#     ds = gdalos_raster_color(
#         ds, color_palette=color_palette,
#         out_filename=out_filename, output_format=output_format,
#         discrete_mode=discrete_mode)
#
#     return ds, min_max


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
    wkt_list = get_wkt_list(shp_filename)

    raster_filename = os.path.join(root_data, r'maps/srtm1_x35_y32.tif')
    ds = gdalos_util.open_ds(raster_filename)
    out_filename = tempfile.mktemp(suffix='.tif')

    ds = gdalos_crop(
        ds=ds,
        out_filename=out_filename,
        cutline=wkt_list,
        output_format='GTiff')

    print(out_filename)
