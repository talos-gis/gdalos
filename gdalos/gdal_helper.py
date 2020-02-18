import glob
import os
from pathlib import Path
from typing import Iterator
from typing import Sequence

import gdal


def open_ds(filename, access_mode=gdal.GA_ReadOnly, src_ovr:int=None, open_options:dict=None, logger=None):
    open_options = dict(open_options or dict())
    if src_ovr is not None and src_ovr >= 0:
        open_options['OVERVIEW_LEVEL'] = src_ovr
    if logger is not None:
        s = 'openning file: "{}"'.format(filename)
        if open_options:
            s = s + ' with options: {}'.format(str(open_options))
        logger.debug(s)
    if open_options:
        open_options = ['{}={}'.format(k, v) for k, v in open_options.items()]

    if open_options:
        return gdal.OpenEx(str(filename), open_options=open_options)
    else:
        return gdal.Open(str(filename), access_mode)


class OpenDS:
    def __init__(self, filename_or_ds, **kwargs):
        if isinstance(filename_or_ds, (str, Path)):
            self.filename = str(filename_or_ds)
            self.ds = None
        else:
            self.filename = None
            self.ds = filename_or_ds
        self.kwargs = kwargs
        self.own = None

    def __enter__(self)->gdal.Dataset:
        if self.ds is None:
            self.ds = open_ds(self.filename, **self.kwargs)
            if self.ds is None:
                raise IOError('could not open file "{}"'.format(self.filename))
            self.own = True
        return self.ds

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.own:
            self.ds = None


def _get_bands(ds: gdal.Dataset) -> Iterator[gdal.Band]:
    return (
        ds.GetRasterBand(i + 1) for i in range(ds.RasterCount)
    )


def _band_getmin(band):
    ret = band.GetMinimum()
    if ret is None:
        band.ComputeStatistics(0)
    return band.GetMinimum()


def get_band_types(filename_or_ds):
    with OpenDS(filename_or_ds) as ds:
        return [gdal.GetDataTypeName(band.DataType) for band in _get_bands(ds)]


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


def get_image_structure_metadata(filename_or_ds, key: str, default=None):
    key = key.strip()
    if not key.endswith('='):
        key = key + '='
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


def flatten_and_expand_file_list(l, do_expand_txt=True, do_expand_glob=True):
    if is_path_like(l):
        item = str(l).strip()
        if do_expand_glob:
            item1 = glob.glob(str(item).strip())
            if len(item1) == 1:
                item = item1[0]
            elif len(item1) > 1:
                return flatten_and_expand_file_list(item1)

        if do_expand_txt and \
                os.path.isfile(item) and not os.path.isdir(item) and \
                Path(item).suffix.lower() == '.txt':
            return flatten_and_expand_file_list(expand_txt(item))
        else:
            return item.strip()

    if not is_list_like(l):
        return l
    flat_list = []
    for item in l:
        item1 = flatten_and_expand_file_list(item)
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
    return Path(''.join([str(p) for p in argv]))


