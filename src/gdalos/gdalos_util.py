import glob
import os
from pathlib import Path
from typing import Iterator, Sequence, Union

import gdal
import ogr
import osr

from gdalos import gdalos_types


def open_ds(filename_or_ds, *args, **kwargs):
    ods = OpenDS(filename_or_ds, *args, **kwargs)
    return ods.__enter__()


def get_ovr_idx(filename_or_ds, ovr_idx):
    if ovr_idx in [..., None]:
        ovr_idx = 0
    if ovr_idx < 0:
        # -1 is the last overview; -2 is the one before the last
        overview_count = get_ovr_count(open_ds(filename_or_ds))
        ovr_idx = max(0, overview_count + ovr_idx + 1)
    return ovr_idx


class OpenDS:
    def __init__(self, filename_or_ds, *args, **kwargs):
        if isinstance(filename_or_ds, (str, Path)):
            self.filename = str(filename_or_ds)
            self.ds = None
        else:
            self.filename = None
            self.ds = filename_or_ds
        self.args = args
        self.kwargs = kwargs
        self.own = None

    def __enter__(self) -> gdal.Dataset:
        if self.ds is None:
            self.ds = self._open_ds(self.filename, *self.args, **self.kwargs)
            if self.ds is None:
                raise IOError('could not open file "{}"'.format(self.filename))
            self.own = True
        return self.ds

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.own:
            self.ds = None

    @staticmethod
    def _open_ds(
            filename,
            access_mode=gdal.GA_ReadOnly,
            ovr_idx: int = None,
            open_options: dict = None,
            logger=None,
    ):
        open_options = dict(open_options or dict())
        ovr_idx = get_ovr_idx(filename, ovr_idx)
        if ovr_idx > 0:
            open_options["OVERVIEW_LEVEL"] = ovr_idx - 1  # gdal overview 0 is the first overview (after the base layer)
        if logger is not None:
            s = 'openning file: "{}"'.format(filename)
            if open_options:
                s = s + " with options: {}".format(str(open_options))
            logger.debug(s)
        if open_options:
            open_options = ["{}={}".format(k, v) for k, v in open_options.items()]

        if open_options:
            return gdal.OpenEx(str(filename), open_options=open_options)
        else:
            return gdal.Open(str(filename), access_mode)


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


def get_data_type(bandtype: Union[str, int]):
    if bandtype in [None, ...]:
        return None
    if isinstance(bandtype, str):
        return gdal.GetDataTypeName(bandtype)
    else:
        return bandtype


def get_raster_band(filename_or_ds, bnd_index=1, ovr_index=None):
    with OpenDS(filename_or_ds) as ds:
        bnd = ds.GetRasterBand(bnd_index)
        if ovr_index is not None:
            bnd = bnd.GetOverview(ovr_index)
        return bnd


def get_ovr_count(filename_or_ds):
    with OpenDS(filename_or_ds) as ds:
        bnd = ds.GetRasterBand(1)
        return bnd.GetOverviewCount()


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


def get_raster_min_max(filename_or_ds):
    with OpenDS(filename_or_ds) as ds:
        bnd = ds.GetRasterBand(1)
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


def check_expand_glob(val, filenames_expand):
    return (filenames_expand is True) or ((filenames_expand is ...) and ('*' in str(val) or '?' in str(val)))


def flatten_and_expand_file_list(l, do_expand_txt=True, do_expand_glob: Union[type(...), bool] = ...):
    if is_path_like(l):
        item = str(l).strip()
        if check_expand_glob(item, do_expand_glob):
            item1 = glob.glob(item)
            if len(item1) == 1:
                item = item1[0]
            elif len(item1) > 1:
                return flatten_and_expand_file_list(item1, do_expand_txt, do_expand_glob)

        if (
                do_expand_txt
                and os.path.isfile(item)
                and not os.path.isdir(item)
                and Path(item).suffix.lower() == ".txt"
        ):
            return flatten_and_expand_file_list(expand_txt(item), do_expand_txt, do_expand_glob)
        else:
            return item.strip()

    if not is_list_like(l):
        return l
    flat_list = []
    for item in l:
        item1 = flatten_and_expand_file_list(item, do_expand_txt, do_expand_glob)
        if is_list_like(item1):
            flat_list.extend(item1)
        else:
            flat_list.append(item1)
    return flat_list


def is_path_like(s):
    return isinstance(s, (str, Path))


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


def get_ext_by_of(of: str):
    ext = gdalos_types.enum_to_str(of).lower()
    if ext in ['gtiff', 'cog', 'mem']:
        ext = 'tif'
    return '.' + ext


def get_creation_options(creation_options=None,
                         of: str = 'gtiff',
                         sparse_ok: bool = True,
                         tiled: bool = True,
                         block_size: int = ...,
                         big_tiff: str = ...,
                         comp="DEFLATE"):
    creation_options = dict(creation_options or dict())
    no_yes = ("NO", "YES")
    creation_options["SPARSE_OK"] = no_yes[bool(sparse_ok)]

    of = of.lower()
    if of in ['gtiff', 'cog']:
        if not big_tiff:
            big_tiff = False
        elif big_tiff is ...:
            big_tiff = "IF_SAFER"
        elif not isinstance(big_tiff, str):
            big_tiff = no_yes[bool(big_tiff)]

        creation_options["BIGTIFF"] = big_tiff
        creation_options["COMPRESS"] = comp

    tiled = tiled.upper() != no_yes[False] if isinstance(tiled, str) else bool(tiled)
    creation_options["TILED"] = no_yes[tiled]
    if tiled and block_size is not ...:
        if of == 'gtiff':
            creation_options["BLOCKXSIZE"] = block_size
            creation_options["BLOCKYSIZE"] = block_size
        elif of == 'cog':
            creation_options["BLOCKSIZE"] = block_size

    creation_options_list = []
    for k, v in creation_options.items():
        creation_options_list.append("{}={}".format(k, v))

    return creation_options_list
