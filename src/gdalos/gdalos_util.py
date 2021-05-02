import glob
from pathlib import Path

from gdalos.backports.ogr_utils import ogr_create_geometries_from_wkt
from osgeo_utils.auxiliary.progress import get_progress_callback
from osgeo_utils.auxiliary.util import *  # noqa
from osgeo_utils.auxiliary.raster_creation import *  # noqa

# backwards compatibility
from osgeo_utils.auxiliary.raster_creation import get_creation_options  # noqa

print_progress_callback = get_progress_callback
wkt_write_ogr = ogr_create_geometries_from_wkt
get_big_tiff = get_bigtiff_creation_option_value
get_tiled = is_true


def is_list_like(lst: Sequence) -> bool:
    return isinstance(lst, Sequence) and not isinstance(lst, str)


def concat_paths(*argv) -> str:
    return Path("".join([str(p) for p in argv]))


def expand_txt(filename):
    # input argument is a txt file, replace it with a list of its lines
    filename = Path(filename.strip())
    with open(filename) as f:
        return f.read().splitlines()


def check_expand_glob(val, filenames_expand: Optional[bool]):
    return (filenames_expand is True) or ((filenames_expand is None) and ('*' in str(val) or '?' in str(val)))


def flatten_and_expand_file_list(lst, do_expand_txt=True, do_expand_glob: Optional[bool] = None, always_return_list=False):
    if isinstance(lst, PathLikeOrStr.__args__):
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


def do_skip_if_exists(out_filename, overwrite, logger=None):
    verbose = logger not in [None,  ...]
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
