from typing import Iterator

import gdal


class OpenDS:
    def __init__(self, ds, *options):
        self.ds = ds
        self.options = options
        self.own = None

    def __enter__(self)->gdal.Dataset:
        if isinstance(self.ds, str):
            self.ds = gdal.Open(self.ds, *self.options)
            if self.ds is None:
                raise IOError("could not open file")
            self.own = True
        return self.ds

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.own:
            self.ds = None


def _get_bands(ds: gdal.Dataset) -> Iterator[gdal.Band]:
    return (
        ds.GetRasterBand(i + 1) for i in range(ds.RasterCount)
    )


def get_band_types(ds):
    with OpenDS(ds) as ds:
        return [
            gdal.GetDataTypeName(band.DataType)
            for band in _get_bands(ds)
        ]


def get_nodatavalue(ds):
    with OpenDS(ds) as ds:
        band = next(_get_bands(ds))
        return band.GetNoDataValue()


def unset_nodatavalue(ds):
    with OpenDS(ds, gdal.GA_Update) as ds:
        for b in _get_bands(ds):
            b.DeleteNoDataValue()


def get_raster_minimum(ds):
    with OpenDS(ds) as ds:
        return min(b.GetMinimum() for b in _get_bands(ds))


def get_image_structure_metadata(ds, key: str, default=None):
    key = key.strip()
    if not key.endswith('='):
        key = key + '='
    with OpenDS(ds) as ds:
        metadata = ds.GetMetadata_List("IMAGE_STRUCTURE")
        if metadata is None:
            return default
        for metadata in metadata:
            if metadata.startswith(key):
                return metadata[len(key):]
        return default
