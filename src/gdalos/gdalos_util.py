import glob
import os
from pathlib import Path
from typing import Iterator, Sequence

from gdalos.rectangle import GeoRectangle
from osgeo import ogr, osr

from gdalos.gdalos_base import enum_to_str
from osgeo_utils.auxiliary.util import *

no_yes = ("NO", "YES")


def _get_bands(ds: gdal.Dataset) -> Iterator[gdal.Band]:
    return (ds.GetRasterBand(i + 1) for i in range(ds.RasterCount))


def _band_getmin(band):
    ret = band.GetMinimum()
    if ret is None:
        band.ComputeStatistics(0)
    return band.GetMinimum()


def get_band_types(filename_or_ds):
    with OpenDS(filename_or_ds) as ds:
        return [band.DataType for band in _get_bands(ds)]


def get_data_type(bandtype: Optional[Union[str, int]]):
    if bandtype is None:
        return None
    if isinstance(bandtype, str):
        return gdal.GetDataTypeByName(bandtype)
    else:
        return bandtype


def get_raster_band(filename_or_ds, bnd_index=1, ovr_index=None):
    with OpenDS(filename_or_ds) as ds:
        bnd = ds.GetRasterBand(bnd_index)
        if ovr_index is not None:
            bnd = bnd.GetOverview(ovr_index)
        return bnd


def get_nodatavalue(filename_or_ds):
    with OpenDS(filename_or_ds) as ds:
        band = next(_get_bands(ds))
        return band.GetNoDataValue()


def unset_nodatavalue(filename_or_ds):
    with OpenDS(filename_or_ds, access_mode=gdal.GA_Update) as ds:
        for b in _get_bands(ds):
            b.DeleteNoDataValue()


def get_raster_minimum(filename_or_ds):
    with OpenDS(filename_or_ds) as ds:
        return min(_band_getmin(b) for b in _get_bands(ds))


def get_raster_min_max(filename_or_ds, bnd_index=1):
    with OpenDS(filename_or_ds) as ds:
        bnd = ds.GetRasterBand(bnd_index)
        bnd.ComputeStatistics(0)
        min_val = bnd.GetMinimum()
        max_val = bnd.GetMaximum()
        return min_val, max_val


def get_image_structure_metadata(filename_or_ds, key: str, default=None):
    key = key.strip()
    if not key.endswith("="):
        key = key + "="
    with OpenDS(filename_or_ds) as ds:
        metadata = ds.GetMetadata_List("IMAGE_STRUCTURE")
        if metadata is None:
            return default
        for metadata in metadata:
            if metadata.startswith(key):
                return metadata[len(key):]
        return default


def expand_txt(filename):
    # input argument is a txt file, replace it with a list of its lines
    filename = Path(filename.strip())
    with open(filename) as f:
        return f.read().splitlines()


def check_expand_glob(val, filenames_expand: Optional[bool]):
    return (filenames_expand is True) or ((filenames_expand is None) and ('*' in str(val) or '?' in str(val)))


def flatten_and_expand_file_list(lst, do_expand_txt=True, do_expand_glob: Optional[bool] = None, always_return_list=False):
    if isinstance(lst, PathLike.__args__):
        item = str(lst).strip()
        if check_expand_glob(item, do_expand_glob):
            item1 = glob.glob(item)
            if len(item1) == 1:
                item = str(item1[0]).strip()
            elif len(item1) > 1:
                # return flatten_and_expand_file_list(item1, do_expand_txt, do_expand_glob)
                return item1
        if (
                do_expand_txt
                and os.path.isfile(item)
                and not os.path.isdir(item)
                and Path(item).suffix.lower() == ".txt"
        ):
            return flatten_and_expand_file_list(expand_txt(item), do_expand_txt, do_expand_glob)
        else:
            return [item] if always_return_list else item

    if not is_list_like(lst):
        return [lst] if always_return_list else lst
    flat_list = []
    for item in lst:
        item1 = flatten_and_expand_file_list(item, do_expand_txt, do_expand_glob)
        if is_list_like(item1):
            flat_list.extend(item1)
        else:
            flat_list.append(item1)
    return flat_list


def is_list_like(lst):
    return isinstance(lst, Sequence) and not isinstance(lst, str)


def concat_paths(*argv):
    return Path("".join([str(p) for p in argv]))


def wkt_write_ogr(path, wkt_list, of='ESRI Shapefile', epsg=4326):
    driver = ogr.GetDriverByName(of)
    ds = driver.CreateDataSource(path)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)

    layer = ds.CreateLayer('', srs, ogr.wkbUnknown)
    for wkt in wkt_list:
        feature = ogr.Feature(layer.GetLayerDefn())
        geom = ogr.CreateGeometryFromWkt(wkt)
        feature.SetGeometry(geom)  # Set the feature geometry
        layer.CreateFeature(feature)  # Create the feature in the layer
        feature.Destroy()  # Destroy the feature to free resources
    # Destroy the data source to free resources
    ds.Destroy()


def get_big_tiff(big_tiff):
    return "IF_SAFER" if big_tiff is None else big_tiff if isinstance(big_tiff, str) else no_yes[bool(big_tiff)]


def get_tiled(tiled):
    return tiled.upper() != no_yes[False] if isinstance(tiled, str) else bool(tiled)


def get_ext_by_of(of: str):
    ext = enum_to_str(of).lower()
    if ext in ['gtiff', 'cog', 'mem']:
        ext = 'tif'
    return '.' + ext


def get_creation_options(creation_options=None,
                         of: str = 'gtiff',
                         sparse_ok: bool = True,
                         tiled: bool = True,
                         block_size: Optional[int] = None,
                         big_tiff: Optional[str] = None,
                         comp="DEFLATE"):
    creation_options = dict(creation_options or dict())
    creation_options["SPARSE_OK"] = no_yes[bool(sparse_ok)]

    of = of.lower()
    if of in ['gtiff', 'cog']:
        creation_options["BIGTIFF"] = get_big_tiff(big_tiff)
        creation_options["COMPRESS"] = comp

    tiled = get_tiled(tiled)
    creation_options["TILED"] = no_yes[tiled]
    if tiled and block_size is not None:
        if of == 'gtiff':
            creation_options["BLOCKXSIZE"] = block_size
            creation_options["BLOCKYSIZE"] = block_size
        elif of == 'cog':
            creation_options["BLOCKSIZE"] = block_size

    creation_options_list = []
    for k, v in creation_options.items():
        creation_options_list.append("{}={}".format(k, v))

    return creation_options_list


def do_skip_if_exists(out_filename, overwrite, logger=None):
    verbose = logger is not None and logger is not ...
    skip = False
    if os.path.isfile(out_filename):
        if not overwrite:
            skip = True
            if verbose:
                logger.warning('file "{}" exists, skip!'.format(out_filename))
        else:
            if verbose:
                logger.warning('file "{}" exists, deleting...!'.format(out_filename))
            os.remove(out_filename)
    return skip


def print_progress_from_to(r0, r1):
    # print(str(round(r1*100)) + '%', end=" ")
    i0 = 0 if (r0 is None) or (r0 > r1) else round(r0 * 100) + 1
    i1 = round(r1 * 100) + 1
    for i in range(i0, i1):
        print(str(i) if i % 5 == 0 else ".", end="", flush=True)
    if r1 >= 1:
        print("% done!")


def print_progress_callback(print_progress):
    if print_progress:
        if print_progress is ...:
            last = None

            def print_progress(prog, *_):
                nonlocal last

                r0 = last
                r1 = prog
                print_progress_from_to(r0, r1)
                last = prog

    return print_progress
