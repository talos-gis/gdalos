from enum import Enum, auto
from numbers import Real
from typing import TypeVar, Union, Sequence

from osgeo import gdal

from gdalos import gdalos_util

T = TypeVar("T")
MaybeSequence = Union[T, Sequence[T]]
warp_srs_base = Union[str, int, Real]


class OvrType(Enum):
    # existing_reuse or create_external_auto (by existance of src overviews)
    auto_select = auto()
    # do not create overviews
    no_overviews = auto()
    # work with existing overviews
    existing_reuse = auto()
    # create_external_single or create_external_multi (by size)
    create_external_auto = auto()
    # create a single .ovr file with all the overviews
    create_external_single = auto()
    # create one ovr file per overview: .ovr, .ovr.ovr, .ovr.ovr.orv ....
    create_external_multi = auto()
    # create overviews inside the main dataset file
    create_internal = auto()


# these are the common resamplers for translate, warp, addo, buildvrt.
# there are some specific resamplers for warp and addo
class GdalResamplingAlg(Enum):
    # nearest applies a nearest neighbour (simple sampling) resampler. for warp it's called 'near'
    nearest = auto()
    # average computes the average of all non-NODATA contributing pixels.
    # Starting with GDAL 3.1, this is a weighted average taking into account properly
    # the weight of source pixels not contributing fully to the target pixel.
    average = auto()
    # bilinear applies a bilinear convolution kernel.
    bilinear = auto()
    # cubic applies a cubic convolution kernel.
    cubic = auto()
    # cubicspline applies a B-Spline convolution kernel.
    cubicspline = auto()
    # lanczos applies a Lanczos windowed sinc convolution kernel.
    lanczos = auto()
    # mode selects the value which appears most often of all the sampled points.
    mode = auto()


class GdalOutputFormat(Enum):
    gtiff = auto()
    cog = auto()
    gpkg = auto()
    mem = auto()


class RasterKind(Enum):
    unknown = auto()
    photo = auto()
    pal = auto()
    dtm = auto()

    @classmethod
    def guess(cls, band_types_or_filename_or_ds):
        if isinstance(band_types_or_filename_or_ds, (list, tuple)):
            band_types = tuple(gdalos_util.get_data_type(band) for band in band_types_or_filename_or_ds)
        else:
            band_types = gdalos_util.get_band_types(band_types_or_filename_or_ds)
        if len(band_types) == 0:
            raise Exception("no bands in raster")

        if band_types[0] == gdal.GDT_Byte:
            if band_types in ((gdal.GDT_Byte, gdal.GDT_Byte, gdal.GDT_Byte),
                              (gdal.GDT_Byte, gdal.GDT_Byte, gdal.GDT_Byte, gdal.GDT_Byte)):
                return cls.photo
            elif len(band_types) == 1:
                return cls.pal
        elif len(band_types) == 1:
            return cls.dtm
        return cls.unknown

    def resampling_alg_by_kind(self, expand_rgb=False, fast_mode=False) -> GdalResamplingAlg:
        if self == RasterKind.pal and not expand_rgb:
            if fast_mode:
                return GdalResamplingAlg.nearest
            else:
                return GdalResamplingAlg.mode
        else:
            if fast_mode:
                return GdalResamplingAlg.average
            else:
                return GdalResamplingAlg.cubic
