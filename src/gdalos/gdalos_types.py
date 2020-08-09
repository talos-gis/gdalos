from enum import Enum, auto


def enum_to_str(enum_or_str):
    return enum_or_str.name if isinstance(enum_or_str, Enum) else str(enum_or_str)


class OvrType(Enum):
    # existing_reuse or create_external_auto (by existance of src overviews)
    auto_select = auto()
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
