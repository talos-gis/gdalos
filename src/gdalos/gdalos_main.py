import datetime
import logging
import os
import tempfile
import time
from numbers import Real
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, TypeVar, Union

from osgeo import gdal
import gdalos
from gdalos import gdalos_util, gdalos_logger, gdalos_extent, projdef, __version__
from gdalos.__util__ import with_param_dict
from gdalos.calc import scale_raster
from gdalos.gdalos_base import enum_to_str, version_tuple
from gdalos.gdalos_types import GdalOutputFormat, OvrType, RasterKind, GdalResamplingAlg
from gdalos.gdalos_util import no_yes
from gdalos.partitions import Partition, make_partitions
from gdalos.rectangle import GeoRectangle

gdalos_version = version_tuple(gdalos.__version__)
gdal_version = version_tuple(gdal.__version__)
support_of_cog = gdal_version >= (3, 1)
multi_thread_support_available = gdal_version >= (3, 2)
workaround_warp_scale_bug = gdal_version < (3, 3)  # workaround https://github.com/OSGeo/gdal/issues/3232


def get_cuttent_time_string():
    return "Current time: {}".format(datetime.datetime.now())


def print_time_now(logger):
    logger.info(get_cuttent_time_string())


def options_dict_to_list(options: dict):
    options_list = []
    for k, v in options.items():
        options_list.append("{}={}".format(k, v))
    return options_list


def multi_thread_to_str(multi_thread: Union[bool, int, str]) -> str:
    if isinstance(multi_thread, bool):
        multi_thread = 'ALL_CPUS'
    elif isinstance(multi_thread, int):
        multi_thread = str(multi_thread)
    elif isinstance(multi_thread, str):
        pass
    else:
        raise Exception(f'unknown value multi_threa={multi_thread}')
    return multi_thread


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


T = TypeVar("T")
MaybeSequence = Union[T, Sequence[T]]
warp_srs_base = Union[str, int, Real]
default_multi_byte_nodata_value = -32768


# overviews numbers explained:
# overview_count=n means that the raster has n+1 rasters inside it. the base raster + n overviews.
# gdal numbers the overviews as 0..n-1, first overview as 0 meaning the base raster has no overview number
# I wanted to give the base raster also a number, which by this logic makes source it would be -1
# I find it a bit confusing to number the rasters as -1..n-1.
# so I define src_ovr=0 to be the base raster and 0..n to be the overviews
# I also define negative overview numbers as follows: ovr_idx<0 == overview_count+ovr_idx+1
# So for raster that has overview_count=3 holds 4 rasters which are numberd 0..3. (-1)->3; (-2)->2, (-3)->1, (-4)->0


@with_param_dict("all_args")
def gdalos_trans(
        filename: MaybeSequence[str],
        reference_filename: MaybeSequence[str] = None,
        filenames_expand: Optional[bool] = None,
        out_filename: Optional[str] = None,
        out_path: Optional[str] = None,
        return_ds: Optional[bool] = None,
        out_path_with_src_folders: bool = True,
        overwrite=False,
        cog: Optional[bool] = None,
        prefer_2_step_cog: Optional[bool] = None,
        write_info: Optional[bool] = None,
        write_spec: Optional[bool] = None,
        multi_file_as_vrt: bool = False,
        of: Optional[MaybeSequence[Union[GdalOutputFormat, str]]] = None,
        outext: Optional[str] = None,
        ot: Optional[Union[str, int]] = None,
        value_scale: Optional[Real] = None,  # 0 for default
        kind: Optional[RasterKind] = None,
        tiled: bool = True,
        block_size: Optional[int] = None,
        big_tiff: Optional[str] = None,
        config_options: Optional[dict] = None,
        open_options: Optional[dict] = None,
        common_options: Optional[dict] = None,
        creation_options: Optional[dict] = None,
        translate_options: Optional[dict] = None,
        warp_options: Optional[dict] = None,
        warp_options_inner: Optional[dict] = None,
        extent: Union[Optional[GeoRectangle], List[GeoRectangle]] = None,
        extent_in_4326: bool = True,
        extent_crop_to_minimal: bool = True,
        extent_aligned: Optional[bool] = None,
        src_win: Optional[Sequence[int]] = None,
        cutline: Optional[Union[str, List[str]]] = None,
        out_res: Optional[Union[type(...), Real, Tuple[Real, Real]]] = None,  # None -> gdalos default; ... -> gdal default
        warp_srs: MaybeSequence[warp_srs_base] = None,
        warp_scale: Optional[Union[Real, Tuple[Real, Real]]] = 1,  # https://github.com/OSGeo/gdal/issues/2810
        warp_error_threshold: Optional[Real] = 0,  # [None|0]: [linear approximator|exact] coordinate reprojection
        ovr_type: Optional[OvrType] = OvrType.auto_select,
        ovr_idx: Optional[int] = 0,  # ovr_idx=0 is the base raster; 1 is the first overview; ovr_idx=None will select the default ovr
        keep_src_ovr_suffixes: bool = True,
        dst_ovr_count: Optional[int] = None,
        dst_nodatavalue: Optional[Union[type(...), Real]] = None,  # None -> don't change; ... -> change only for DTM
        src_nodatavalue: Optional[Union[type(...), Real]] = None,  # None -> use original; ... -> use minimum;
        hide_nodatavalue: bool = False,
        resampling_alg: Optional[Union[type(...), GdalResamplingAlg, str]] = None,  # None -> gdalos default; ... -> gdal default;
        multi_thread: Union[bool, int, str] = True,
        lossy: Optional[bool] = None,
        expand_rgb: bool = False,
        quality: Optional[Real] = None,
        keep_alpha: Optional[bool] = None,
        sparse_ok: bool = True,
        final_files: Optional[list] = None,
        ovr_files: Optional[list] = None,
        aux_files: Optional[list] = None,
        temp_files: Optional[list] = None,
        delete_temp_files: bool = True,
        partition: Optional[Union[MaybeSequence[Partition], int]] = None,
        print_progress=...,
        logger=...,
        console_logger_level=logging.INFO,
        *,
        all_args: dict = None,
):
    # backwards compatibility: accept ... as None for the following vars
    if filenames_expand is ...:
        filenames_expand = None
    if return_ds is ...:
        return_ds = None
    if cog is ...:
        cog = None
    if prefer_2_step_cog is ...:
        prefer_2_step_cog = None
    if write_info is ...:
        write_info = None
    if write_spec is ...:
        write_spec = None
    if of is ...:
        of = None
    if ot is ...:
        ot = None
    if outext is ...:
        outext = None
    if value_scale is ...:
        value_scale = None
    if block_size is ...:
        block_size = None
    if big_tiff is ...:
        big_tiff = None
    if quality is ...:
        quality = None
    if keep_alpha is ...:
        keep_alpha = None
    if ovr_idx is ...:
        ovr_idx = None
    if lossy is ...:
        lossy = None
    if ovr_type is ...:
        ovr_type = None

    print(all_args)

    if final_files is None:
        final_files = []
    if ovr_files is None:
        ovr_files = []
    if aux_files is None:
        aux_files = []
    if temp_files is None:
        temp_files = []

    if isinstance(kind, str):
        kind = RasterKind[kind]

    if ovr_type is None:
        ovr_type = OvrType.auto_select
    elif isinstance(ovr_type, str):
        ovr_type = OvrType[ovr_type]

    if isinstance(partition, int):
        partition = None if partition <= 1 else make_partitions(partition)
        all_args["partition"] = partition

    key_list_arguments = [
        "filename",
        "extent",
        "warp_srs",
        # "cutline"
        "of",
        "expand_rgb",
        "partition",
    ]
    for key in key_list_arguments:
        val = all_args[key]
        do_expand_glob = filenames_expand if (key == "filename") else False
        val = gdalos_util.flatten_and_expand_file_list(val, do_expand_glob=do_expand_glob)
        if key == "filename":
            if gdalos_util.is_list_like(val) and multi_file_as_vrt:
                vrt_path = gdalos_vrt(
                    val,
                    filenames_expand=False,
                    resampling_alg=resampling_alg,
                    kind=kind,
                    overwrite=overwrite,
                    logger=logger,
                )
                if vrt_path is None:
                    raise Exception(
                        "failed to create a vrt file: {}".format(vrt_path)
                    )  # failed?
                temp_files.append(vrt_path)
                val = vrt_path
            filename = val

        if gdalos_util.is_list_like(val):
            # input argument is a list, recurse over its values
            all_args_new = all_args.copy()
            ret_code = None
            for idx, v in enumerate(val):
                print("iterate over {} ({}/{}) - {}".format(key, idx + 1, len(val), v))
                all_args_new[key] = v
                all_args_new["temp_files"] = []
                all_args_new["final_files"] = []
                all_args_new["ovr_files"] = []
                all_args_new["aux_files"] = []
                ret_code = gdalos_trans(**all_args_new)
                temp_files.extend(all_args_new["temp_files"])
                final_files.extend(all_args_new["final_files"])
                ovr_files.extend(all_args_new["ovr_files"])
                aux_files.extend(all_args_new["aux_files"])
                # if ret_code is None:
                #     break  # failed?
            return ret_code
        else:
            all_args[key] = val  # adding the default parameters

    if not filename:
        return None
    start_time = time.time()
    ref_filename = reference_filename or filename

    # region console logger initialization
    logger_handlers = []
    if logger is ...:
        logger = logging.getLogger(__name__)
        logger_handlers.append(gdalos_logger.set_logger_console(logger, level=console_logger_level))
        logger.debug("console handler added")
    all_args["logger"] = logger
    verbose = logger is not None and logger is not ...
    if verbose:
        print_time_now(logger)
        logger.info(f'gdal version: {gdal.__version__}')
        logger.info(all_args)
    # endregion

    # creating a copy of the input dictionaries, as I don't want to change the input
    config_options = dict(config_options or dict())
    common_options = dict(common_options or dict())
    creation_options = dict(creation_options or dict())
    translate_options = dict(translate_options or dict())
    warp_options = dict(warp_options or dict())
    warp_options_inner = dict(warp_options_inner or dict())
    out_suffixes = []

    if multi_thread:
        multi_thread = multi_thread_to_str(multi_thread)
        creation_options['NUM_THREADS'] = multi_thread
        warp_options_inner['NUM_THREADS'] = multi_thread
        warp_options['multithread'] = True

    if ovr_idx is not None:
        ovr_idx = gdalos_util.get_ovr_idx(filename, ovr_idx)
    ds = gdalos_util.open_ds(filename, ovr_idx=ovr_idx, open_options=open_options, logger=logger)

    # region decide which overviews to make
    if ovr_idx is not None:
        warp_options['overviewLevel'] = 'None'  # force gdal to use the selected ovr_idx (added in GDAL >= 3.0)
        overview_count = gdalos_util.get_ovr_count(ds)
        src_ovr_last = ovr_idx + overview_count
        if dst_ovr_count is not None:
            if dst_ovr_count >= 0:
                src_ovr_last = ovr_idx + min(overview_count, dst_ovr_count)
            else:
                # in this case we'll reopen the ds with a new ovr_idx, because we want only the last overviews
                new_src_ovr = max(0, overview_count + dst_ovr_count + 1)
                if new_src_ovr != ovr_idx:
                    ovr_idx = new_src_ovr
                    del ds
                    ds = gdalos_util.open_ds(filename, ovr_idx=ovr_idx, open_options=open_options, logger=logger)
                    overview_count = gdalos_util.get_ovr_count(ds)
                    src_ovr_last = ovr_idx + overview_count
    # endregion

    # filename_is_ds = not isinstance(filename, (str, Path))
    filename_is_ds = ds == filename

    if verbose:
        logger.info(f'gdal version: {gdal_version}; cog driver support: {support_of_cog}')
    if cog is None:
        cog = not filename_is_ds
    if ovr_type is None:
        cog = False

    if isinstance(of, str):
        of = of.lower()
        try:
            of = GdalOutputFormat[of]
        except:
            pass
    if return_ds is None:
        return_ds = of == GdalOutputFormat.mem
    if of is None:
        of = GdalOutputFormat.mem if return_ds else GdalOutputFormat.cog if (
                cog and support_of_cog) else GdalOutputFormat.gtiff

    if of == GdalOutputFormat.cog:
        cog = True

    if write_info is None:
        write_info = not return_ds
    if write_spec is None:
        write_spec = not return_ds
    if filename_is_ds:
        input_ext = None
    else:
        filename = Path(filename.strip())
        if os.path.isdir(filename):
            raise Exception('input is a dir, not a file: "{}"'.format(filename))
        if not os.path.isfile(filename):
            raise OSError('file not found: "{}"'.format(filename))
        input_ext = os.path.splitext(filename)[1].lower()

    if extent is None:
        extent_in_4326 = True

    if sparse_ok is ...:
        sparse_ok = not filename_is_ds and str(Path(filename).suffix).lower() == '.vrt'
    creation_options["SPARSE_OK"] = no_yes[bool(sparse_ok)]

    extent_was_cropped = False
    input_is_vrt = input_ext == ".vrt"

    geo_transform = ds.GetGeoTransform()
    input_res = (geo_transform[1], geo_transform[5])
    ot = gdalos_util.get_data_type(ot)
    band_types = gdalos_util.get_band_types(ds)
    if kind in [None, ...]:
        kind = RasterKind.guess(band_types)
    if kind != RasterKind.dtm:
        value_scale = None

    # region warp CRS handling
    pjstr_src_srs = projdef.get_srs_pj_from_ds(ds)
    pjstr_tgt_srs = None
    tgt_zone = None
    if warp_srs is not None:
        pjstr_tgt_srs, tgt_zone1 = projdef.parse_proj_string_and_zone(warp_srs)
        tgt_datum, tgt_zone = projdef.get_datum_and_zone_from_projstring(pjstr_tgt_srs)
        if tgt_zone1:
            tgt_zone = tgt_zone1
        if projdef.proj_is_equivalent(pjstr_src_srs, pjstr_tgt_srs):
            warp_srs = None  # no warp is really needed here
    if warp_srs is not None:
        if extent_aligned is None:
            extent_aligned = False
        if tgt_zone is not None and extent_in_4326:
            if tgt_zone != 0:
                # cropping according to tgt_zone bounds
                zone_extent = GeoRectangle.from_points(projdef.get_utm_zone_extent_points(tgt_zone))
                if extent is None:
                    extent = zone_extent
                elif extent_crop_to_minimal:
                    extent = extent.intersect(zone_extent)
                extent_was_cropped = True
        out_suffixes.append(projdef.get_canonic_name(tgt_datum, tgt_zone))
        if kind == RasterKind.dtm and ot is None:
            ot = gdal.GDT_Float32
        warp_options["dstSRS"] = pjstr_tgt_srs
    # endregion

    if cutline:
        if isinstance(cutline, str):
            cutline_filename = cutline
        elif isinstance(cutline, Sequence):
            cutline_filename = tempfile.mktemp(suffix='.gpkg')
            temp_files.append(cutline_filename)
            gdalos_util.wkt_write_ogr(cutline_filename, cutline, of='GPKG')
        warp_options['cutlineDSName'] = cutline_filename

    do_warp = warp_srs is not None or cutline is not None

    # region compression
    resample_is_needed = warp_srs is not None or (out_res not in [..., None])
    org_comp = gdalos_util.get_image_structure_metadata(ds, "COMPRESSION")
    src_is_lossy = (org_comp is not None) and ("JPEG" in org_comp)
    if lossy is None:
        lossy = src_is_lossy or resample_is_needed
    if lossy and (kind != RasterKind.photo):
        lossy = False
    if not lossy:
        comp = "DEFLATE"
    else:
        comp = "JPEG"
        out_suffixes.append("jpg")
    jpeg_compression = (comp == "JPEG") and (len(band_types) in (3, 4))
    # endregion

    # region expand_rgb
    if kind == RasterKind.pal and expand_rgb:
        translate_options["rgbExpand"] = "rgb"
        out_suffixes.append("rgb")
    # endregion

    # region nodatavalue
    if dst_nodatavalue is ...:
        if kind == RasterKind.dtm:
            dst_nodatavalue = default_multi_byte_nodata_value
        else:
            dst_nodatavalue = None  # don't change no_data
    if dst_nodatavalue is not None:
        src_nodatavalue_org = gdalos_util.get_nodatavalue(ds)
        if src_nodatavalue is None:
            src_nodatavalue = src_nodatavalue_org
        elif src_nodatavalue is ...:
            # assume raster minimum is nodata if nodata isn't set
            logger.debug('finding raster minimum, this might take some time...')
            src_min_value = gdalos_util.get_raster_minimum(ds)
            # if abs(src_min_value - default_multi_byte_nodata_value) < 100:
            # assuming that the raster minimum is indeed a nodatavalue if it's very low
            if True:
                src_nodatavalue = src_min_value
        if src_nodatavalue is not None:
            if src_nodatavalue != dst_nodatavalue:
                do_warp = True
                warp_options["dstNodata"] = dst_nodatavalue

            if src_nodatavalue_org != src_nodatavalue:
                translate_options["noData"] = src_nodatavalue
                warp_options["srcNodata"] = src_nodatavalue
    # endregion

    # region extent
    org_extent_in_src_srs = gdalos_extent.get_extent(ds)
    if org_extent_in_src_srs.is_empty():
        raise Exception(f"no input extent: {filename} [{org_extent_in_src_srs}]")
    out_extent_in_src_srs = org_extent_in_src_srs
    if extent is not None or partition is not None:
        pjstr_4326 = projdef.get_proj_string("w")  # 'EPSG:4326'
        transform = projdef.get_transform(pjstr_src_srs, pjstr_4326)
        src_srs_is_4326 = transform is None
        if extent is None:
            extent = gdalos_extent.translate_extent(org_extent_in_src_srs, transform)
        if pjstr_tgt_srs is None:
            pjstr_tgt_srs = pjstr_src_srs
            transform = None
        else:
            transform = projdef.get_transform(pjstr_src_srs, pjstr_tgt_srs)

        org_extent_in_tgt_srs = gdalos_extent.translate_extent(org_extent_in_src_srs, transform)
        if org_extent_in_tgt_srs.is_empty():
            raise Exception(f"no input extent: {filename} [{org_extent_in_tgt_srs}]")

        if extent_in_4326:
            if extent_crop_to_minimal and src_srs_is_4326:
                # we better intersect in 4326 then in a projected srs
                # because the projected srs bounds might be wider then the 'valid' zone bounds
                extent = extent.intersect(org_extent_in_src_srs)
            transform = projdef.get_transform(pjstr_4326, pjstr_tgt_srs)
            out_extent_in_tgt_srs = gdalos_extent.translate_extent(extent, transform)
        else:
            out_extent_in_tgt_srs = extent
        if extent_crop_to_minimal:
            out_extent_in_tgt_srs = out_extent_in_tgt_srs.intersect(org_extent_in_tgt_srs)

        if out_extent_in_tgt_srs != org_extent_in_tgt_srs:
            extent_was_cropped = True
            transform = projdef.get_transform(pjstr_tgt_srs, pjstr_4326)
            extent = gdalos_extent.translate_extent(out_extent_in_tgt_srs, transform)

        if out_extent_in_tgt_srs.is_empty():
            raise Exception(f"no output extent: {filename} [{out_extent_in_tgt_srs}]")

        if partition:
            out_extent_in_tgt_srs_part = out_extent_in_tgt_srs.get_partition(partition)
        else:
            out_extent_in_tgt_srs_part = out_extent_in_tgt_srs

        if extent_aligned:
            out_extent_in_tgt_srs_part = out_extent_in_tgt_srs_part.align(geo_transform)

        # -projwin minx maxy maxx miny (ulx uly lrx lry)
        translate_options["projWin"] = out_extent_in_tgt_srs_part.lurd
        # -te minx miny maxx maxy
        warp_options["outputBounds"] = out_extent_in_tgt_srs_part.ldru

        transform = projdef.get_transform(pjstr_4326, pjstr_src_srs)
        out_extent_in_src_srs = gdalos_extent.translate_extent(extent, transform)
        if extent_crop_to_minimal:
            out_extent_in_src_srs = out_extent_in_src_srs.intersect(org_extent_in_src_srs)
        if out_extent_in_src_srs.is_empty():
            raise Exception
    elif src_win is not None:
        translate_options["srcWin"] = src_win
    # endregion

    if do_warp and warp_error_threshold is not None:
        warp_options['errorThreshold'] = warp_error_threshold
    if do_warp and warp_scale:
        if isinstance(warp_scale, str):
            warp_scale = float(warp_scale)
        if not isinstance(warp_scale, Sequence):
            warp_scale = [warp_scale, warp_scale]
        # warp_options["warpOptions"].extend(['XSCALE={}'.format(warp_scale[0]), 'YSCALE={}'.format(warp_scale[1])])
        warp_options_inner['XSCALE'] = str(warp_scale[0])
        warp_options_inner['YSCALE'] = str(warp_scale[1])

    # region out_res
    if out_res is not ...:
        if out_res is not None:
            if isinstance(out_res, str):
                out_res = float(out_res)
            if not isinstance(out_res, Sequence):
                out_res = [out_res, -out_res]
        elif warp_srs is not None:
            transform_src_tgt = projdef.get_transform(pjstr_src_srs, pjstr_tgt_srs)
            if transform_src_tgt is not None:
                #  out_res is None and warp
                out_res = gdalos_extent.transform_resolution(transform_src_tgt, input_res, out_extent_in_src_srs)
        if out_res is not None:
            common_options["xRes"], common_options["yRes"] = out_res
            warp_options["targetAlignedPixels"] = True
            base_out_res = [r / 2 ** ovr_idx for r in out_res]
            out_suffixes.append('r' + str(base_out_res if keep_src_ovr_suffixes else out_res))
        # elif ovr_idx is not ...:
        #     #  out_res is None and no warp
        #     out_res = input_res
    # endregion

    # region decide ovr_type
    trans_or_warp_is_needed = bool(
        do_warp
        or extent
        or src_win
        or resample_is_needed
        or (lossy != src_is_lossy)
        or translate_options
    )

    if ovr_type == OvrType.auto_select:
        if (ovr_idx is not None) and (overview_count > 0) or (of == GdalOutputFormat.cog):
            # if the raster has overviews then use them, otherwise create overviews
            ovr_type = OvrType.existing_reuse
        else:
            ovr_type = OvrType.create_external_auto
    if (ovr_type == OvrType.existing_reuse) and (ovr_idx is None):
        raise Exception(f'ovr_idx = {None} cannot be used with ovr_type == {OvrType.existing_reuse}')

    cog_2_steps = \
        cog and \
        (trans_or_warp_is_needed or value_scale or
         ovr_type in [OvrType.create_external_auto, OvrType.create_external_single,
                      OvrType.create_external_multi, OvrType.create_internal])

    if cog_2_steps:
        if of == GdalOutputFormat.cog:
            if prefer_2_step_cog is None:
                prefer_2_step_cog = trans_or_warp_is_needed and (ovr_type == OvrType.existing_reuse)
            if prefer_2_step_cog:
                of = GdalOutputFormat.gtiff
            else:
                cog_2_steps = False
    # endregion

    # region make out_filename
    if outext is None:
        outext = gdalos_util.get_ext_by_of(of)
    elif not outext.startswith('.'):
        outext = '.' + outext
    auto_out_filename = out_filename is None and of != GdalOutputFormat.mem
    if auto_out_filename:
        if filename_is_ds and reference_filename is None:
            raise Exception('input is ds and no output filename is given')
        if (
                cog_2_steps
                and ovr_type == OvrType.create_external_auto
                and not trans_or_warp_is_needed
                and not input_is_vrt
        ):
            # create overviews for the input file then create a cog
            out_filename = ref_filename
        else:
            out_extent_in_4326 = extent
            if extent_was_cropped and (out_extent_in_src_srs is not None):
                transform = projdef.get_transform(pjstr_src_srs, pjstr_4326)
                out_extent_in_4326 = gdalos_extent.translate_extent(
                    out_extent_in_src_srs, transform
                )
            if out_extent_in_4326 is not None:
                out_suffixes.append(
                    "x[{},{}]_y[{},{}]".format(
                        *(round(x, 2) for x in out_extent_in_4326.lrdu)
                    )
                )
            elif src_win is not None:
                out_suffixes.append("off[{},{}]_size[{},{}]".format(*src_win))
            if partition is not None:
                partition_str = "part_"
                if partition.w > 1:
                    partition_str += "x[{},{}]".format(partition.x, partition.w)
                if partition.h > 1:
                    partition_str += "y[{},{}]".format(partition.y, partition.h)
                out_suffixes.append(partition_str)
            if value_scale:
                out_suffixes.append("int")
            if not out_suffixes:
                if outext.lower() == input_ext:
                    out_suffixes.append("new")
            if out_suffixes:
                out_suffixes = "." + ".".join(out_suffixes)
            else:
                out_suffixes = ""
            out_filename = gdalos_util.concat_paths(
                ref_filename, out_suffixes + outext
            )
            if keep_src_ovr_suffixes and ovr_idx is not None:
                out_filename = gdalos_util.concat_paths(
                    out_filename, ".ovr" * ovr_idx
                )
    elif out_filename:
        out_filename = Path(out_filename)
    else:
        out_filename = ''

    if out_path is not None:
        if out_path_with_src_folders:
            out_src_path = out_filename.parts[1:]
        else:
            out_src_path = [out_filename.parts[-1]]
        out_filename = Path(out_path).joinpath(*out_src_path)

    if out_filename and not os.path.exists(os.path.dirname(out_filename)):
        os.makedirs(os.path.dirname(out_filename), exist_ok=True)

    if cog:
        if auto_out_filename:
            final_filename = out_filename.with_suffix(".cog" + outext)
            if not cog_2_steps:
                out_filename = final_filename
        else:
            final_filename = out_filename
            if cog_2_steps:
                out_filename = out_filename.with_suffix(".temp" + outext)
    else:
        final_filename = out_filename
    trans_filename = out_filename.with_suffix(".float" + outext) if value_scale else out_filename
    # endregion

    if cog_2_steps:
        final_files_for_step_1 = temp_files
        ovr_files_for_step_1 = temp_files
    else:
        final_files_for_step_1 = final_files
        ovr_files_for_step_1 = ovr_files

    final_output_exists = do_skip_if_exists(final_filename, overwrite, logger)

    # for OvrType.existing_reuse we'll create the files in backwards order in the overview creation step
    skipped = (final_output_exists or
               ((not filename_is_ds) and
                ((ovr_type == OvrType.existing_reuse and (not cog or cog_2_steps)) or
                 ((filename == out_filename) and (not trans_or_warp_is_needed)))))

    if final_output_exists:
        final_files.append(final_filename)
    elif write_spec:
        spec_filename = gdalos_util.concat_paths(out_filename, ".spec")
        logger_handlers.append(gdalos_logger.set_file_logger(logger, spec_filename))
        logger.debug('spec file handler added: "{}"'.format(spec_filename))
        logger.debug("gdalos versoin: {}".format(__version__))
        aux_files.append(spec_filename)
        # logger.debug('debug')
        # logger.info('info')
        # logger.warning('warning')
        # logger.error('error')
        # logger.critical('critical')

    # region create base raster
    ret_code = None
    out_ds = None
    if not skipped:
        # region jpeg
        if jpeg_compression:
            if of == GdalOutputFormat.gpkg:
                creation_options["TILE_FORMAT"] = "JPEG"
            elif of != GdalOutputFormat.cog:
                creation_options["PHOTOMETRIC"] = "YCBCR"
            if quality:
                creation_options["JPEG_QUALITY" if of == GdalOutputFormat.gtiff else 'QUALITY'] = str(quality)

            # alpha channel is not supported with PHOTOMETRIC=YCBCR, thus we drop it or keep it as a mask band
            if len(band_types) == 4:
                if do_warp:
                    raise Exception(
                        "this mode is not supported: warp RGBA raster with JPEG output. "
                        "You could do it in two steps: "
                        "1. warp with lossless output, "
                        "2. save as jpeg"
                    )
                else:
                    translate_options["bandList"] = [1, 2, 3]
                    if keep_alpha is None:
                        keep_alpha = filename_is_ds or input_ext != '.gpkg'
                    if keep_alpha:
                        translate_options["maskBand"] = 4  # keep the alpha band as mask
        # endregion

        common_options["format"] = enum_to_str(of)
        if of in [GdalOutputFormat.gtiff, GdalOutputFormat.cog]:
            creation_options["BIGTIFF"] = gdalos_util.get_big_tiff(big_tiff)
            creation_options["COMPRESS"] = comp

        tiled = gdalos_util.get_tiled(tiled)
        if of == GdalOutputFormat.gtiff:
            creation_options["TILED"] = no_yes[tiled]
        if tiled and block_size is not None:
            # if block_size is ...:
            #     block_size = 256  # default gdal block_size
            # assert(width / BlockXSize * height / BlockYSize * (big_tiff ? 8: 4) <= 0x80000000)
            # File too large regarding tile size. This would result
            # in a file with tile arrays larger than 2GB
            if of == GdalOutputFormat.gtiff:
                creation_options["BLOCKXSIZE"] = block_size
                creation_options["BLOCKYSIZE"] = block_size
            elif of == GdalOutputFormat.cog:
                creation_options["BLOCKSIZE"] = block_size
        if cog and not cog_2_steps and of != GdalOutputFormat.cog:
            creation_options["COPY_SRC_OVERVIEWS"] = "YES"

        creation_options_list = options_dict_to_list(creation_options)
        if creation_options:
            common_options["creationOptions"] = creation_options_list

        if print_progress:
            common_options["callback"] = print_progress_callback(print_progress)

        if resample_is_needed:
            if resampling_alg is None:
                resampling_alg = kind.resampling_alg_by_kind(expand_rgb)
            if resampling_alg is not ...:
                common_options["resampleAlg"] = enum_to_str(resampling_alg)

        if ot is not None:
            common_options["outputType"] = ot

        if verbose:
            logger.info('filename: "' + str(trans_filename) + '" ...')
            if common_options:
                logger.info("common options: " + str(common_options))

        if input_ext == ".xml":
            config_options = {"GDAL_HTTP_UNSAFESSL": "YES"}  # for gdal-wms xml files

        try:
            if config_options:
                if verbose:
                    logger.info("config options: " + str(config_options))
                for k, v in config_options.items():
                    gdal.SetConfigOption(k, v)

            if do_warp:
                if warp_options_inner:
                    warp_options["warpOptions"] = options_dict_to_list(warp_options_inner)
                if verbose and warp_options:
                    logger.info("warp options: " + str(warp_options))
                out_ds = gdal.Warp(str(trans_filename), ds, **common_options, **warp_options)

                if value_scale is None and workaround_warp_scale_bug:
                    scale_raster.assign_same_scale_and_offset_values(out_ds, ds)
            else:
                if verbose and translate_options:
                    logger.info("translate options: " + str(translate_options))
                out_ds = gdal.Translate(str(trans_filename), ds, **common_options, **translate_options)
            if value_scale is not None:
                temp_files.append(trans_filename)
                if verbose:
                    logger.info(f'scaling {out_filename}..."')
                out_ds = scale_raster.scale_raster(
                    out_ds, out_filename,
                    scale=value_scale, format=enum_to_str(of),
                    hide_nodata=hide_nodatavalue,
                    creation_options_list=creation_options_list, overwrite=overwrite)
            ret_code = out_ds is not None
            if not return_ds:
                out_ds = None  # close output ds
            if ret_code:
                final_files_for_step_1.append(out_filename)
        except Exception as e:
            if verbose:
                logger.error(str(e))
        finally:
            for key, val in config_options.items():
                gdal.SetConfigOption(key, None)

        if verbose:
            seconds = round(time.time() - start_time)
            time_string = str(datetime.timedelta(seconds=seconds))
            logger.info(
                'time: {} for creating file: "{}"'.format(time_string, out_filename)
            )

    if verbose:
        logger.debug(get_cuttent_time_string() + ' closing ds for file: "{}"'.format(filename))
    ds = None  # close input ds if filename was input
    if verbose:
        logger.debug(get_cuttent_time_string() + ' ds is now closed for file: "{}"'.format(filename))
    # end region

    # region create overviews, cog, info
    cog_ready = cog and final_output_exists
    if not cog_ready and (ret_code or skipped):
        if not skipped and hide_nodatavalue:
            gdalos_util.unset_nodatavalue(out_ds or str(out_filename))

        if not cog or cog_2_steps:
            # create overview file(s)
            if ovr_type == OvrType.existing_reuse:
                # overviews are numbered as follows (i.e. for dst_ovr_count=3, meaning create base+3 ovrs=4 files):
                # -1: base dataset, 0: first ovr, 1: second ovr, 2: third ovr

                all_args_new = all_args.copy()
                all_args_new["ovr_type"] = None
                all_args_new["dst_ovr_count"] = None
                all_args_new["out_path"] = None
                all_args_new["write_spec"] = False
                all_args_new["cog"] = False
                all_args_new["logger"] = logger
                # iterate backwards on the overviews
                if verbose:
                    logger.debug(
                        "iterate on overviews creation, from {} to {}".format(
                            src_ovr_last, ovr_idx
                        )
                    )
                for cur_ovr_idx in range(src_ovr_last, ovr_idx - 1, -1):
                    all_args_new["final_files"] = []
                    all_args_new["ovr_files"] = []  # there shouldn't be any
                    all_args_new["aux_files"] = []
                    all_args_new["temp_files"] = []  # there shouldn't be any
                    all_args_new["out_filename"] = gdalos_util.concat_paths(
                        out_filename, ".ovr" * (cur_ovr_idx - ovr_idx)
                    )
                    all_args_new["ovr_idx"] = cur_ovr_idx
                    if out_res not in [None, ...]:
                        res_factor = 2 ** (cur_ovr_idx - ovr_idx)
                        all_args_new["out_res"] = [r * res_factor for r in out_res]
                    all_args_new["write_info"] = (
                            write_info and (cur_ovr_idx == ovr_idx) and not cog
                    )
                    ret_code = gdalos_trans(**all_args_new)
                    if not ret_code:
                        logger.warning(
                            "return code was None for creating {}".format(
                                all_args_new["out_filename"]
                            )
                        )
                    if cur_ovr_idx == ovr_idx:
                        final_files_for_step_1.extend(all_args_new["final_files"])
                    else:
                        ovr_files_for_step_1.extend(all_args_new["final_files"])
                    if verbose:
                        for f in ["ovr_files", "temp_files"]:
                            if all_args_new[f]:
                                logger.error(
                                    "there shound not be any {} here, but there are! {}".format(
                                        f, all_args_new[f]
                                    )
                                )
                        if len(all_args_new["final_files"]) != 1:
                            logger.error(
                                "ovr creating should have made exactly 1 file! {}".format(
                                    all_args_new["final_files"]
                                )
                            )
                    aux_files.extend(all_args_new["aux_files"])
                write_info = write_info and cog
            elif not filename_is_ds and ovr_type not in [None, OvrType.existing_reuse]:
                # create overviews from dataset (internal or external)
                ret_code = gdalos_ovr(
                    out_filename,
                    overwrite=overwrite,
                    ovr_type=ovr_type,
                    dst_ovr_count=dst_ovr_count,
                    kind=kind,
                    multi_thread=multi_thread,
                    resampling_alg=resampling_alg,
                    print_progress=print_progress,
                    logger=logger,
                    ovr_files=ovr_files_for_step_1,
                )

        if cog_2_steps:
            if verbose:
                logger.debug("running cog 2nd step...")
            cog_final_files = []  # there should be exactly one!
            cog_temp_files = []  # there shouldn't be any!
            cog_ovr_files = []  # there shouldn't be any!
            cog_aux_files = []
            ret_code = gdalos_trans(
                out_filename,
                out_filename=final_filename,
                cog=True,
                ovr_type=OvrType.existing_reuse,
                of=of,
                outext=outext,
                tiled=tiled,
                big_tiff=big_tiff,
                print_progress=print_progress,
                final_files=cog_final_files,
                ovr_files=cog_ovr_files,
                aux_files=cog_aux_files,
                temp_files=cog_temp_files,
                delete_temp_files=False,
                logger=logger,
                overwrite=overwrite,
                write_info=write_info,
                write_spec=False,
            )
            if ret_code and verbose:
                if cog_temp_files:
                    logger.error(
                        "cog 2nd step should not have any temp files, but it has! {}".format(
                            cog_temp_files
                        )
                    )
                if len(cog_final_files) != 1:
                    logger.error(
                        "cog 2nd step should have made exactly 1 file! {}".format(
                            cog_final_files
                        )
                    )
            final_files.extend(cog_final_files)
            aux_files.extend(cog_aux_files)
            write_info = (
                False  # we don't need an info for the temp file from first step
            )
        if write_info:
            info = gdalos_info(
                out_filename, overwrite=overwrite, logger=logger
            )
            if info is not None:
                aux_files.append(info)
    # endregion

    missing_final_files = list(f for f in final_files if (f != '') and not os.path.exists(f))
    if missing_final_files:
        logger.error("output files are missing: {}".format(missing_final_files))
    do_delete_temp_files = delete_temp_files and not missing_final_files
    # region log file lists
    if verbose:
        if final_files:
            logger.info("final_files: {}".format(final_files))
        if aux_files:
            logger.info("aux_files: {}".format(aux_files))
        if temp_files:
            logger.info(f'temp_files (will {"" if do_delete_temp_files else "not "}be deleted): {temp_files}')
    # endregion

    # region delete temp files
    if do_delete_temp_files and temp_files:
        for f in temp_files:
            if f == filename:
                if verbose:
                    logger.error(f'somehow the input file was set as a temp file for deletion: "{f}")')
            elif os.path.isfile(f):
                try:
                    os.remove(f)
                except Exception as e:
                    logger.warning('could not delete file: "{}" ({})'.format(f, str(e)))
            else:
                logger.warning('file for deletion not found: "{}"'.format(f))
        temp_files.clear()
    # endregion

    if verbose:
        logger.info("*** done! ***\n")

    # region remove loggers
    if logger_handlers:
        logger.debug("removing {} logging handlers".format(len(logger_handlers)))
        for handler in logger_handlers:
            handler.close()
            logger.removeHandler(handler)
        logger.debug("logging handlers removed")  # this shouldn't log anything
    # end region
    return out_ds or ret_code


def add_ovr(
        filename,
        options,
        access_mode,
        overwrite=True,
        logger=None,
        ovr_files: list = None,
):
    verbose = logger is not None and logger is not ...
    filename = Path(filename)
    out_filename = gdalos_util.concat_paths(filename, ".ovr")
    if not do_skip_if_exists(out_filename, overwrite, logger):
        if verbose:
            logger.info(
                'adding ovr for: "{}" options: {} access_mode: {}'.format(
                    out_filename, options, access_mode
                )
            )
        with gdalos_util.OpenDS(filename, access_mode=access_mode, logger=logger) as ds:
            ret_code = ds.BuildOverviews(**options) == 0
            if ret_code and ovr_files is not None:
                ovr_files.append(out_filename)
            return ret_code
    else:
        return None


default_dst_ovr_count = 10


def gdalos_ovr(
        filename,
        comp=None,
        overwrite=True,
        ovr_type=...,
        dst_ovr_count=default_dst_ovr_count,
        kind=None,
        resampling_alg=None,
        config_options: dict = None,
        ovr_options: dict = None,
        ovr_files: list = None,
        multi_thread: Union[bool, int, str] = True,
        print_progress=...,
        logger=None,
):
    verbose = logger is not None and logger is not ...
    filename = Path(filename)
    if os.path.isdir(filename):
        raise Exception('input is a dir, not a file: "{}"'.format(filename))

    if not os.path.isfile(filename):
        raise Exception('file not found: "{}"'.format(filename))

    if dst_ovr_count is None or dst_ovr_count <= 0:
        dst_ovr_count = default_dst_ovr_count

    if ovr_files is None:
        ovr_files = []

    if isinstance(ovr_type, str):
        ovr_type = OvrType[ovr_type]
    elif ovr_type is ...:
        ovr_type = OvrType.auto_select
    if ovr_type in [OvrType.auto_select, OvrType.create_external_auto]:
        file_size = os.path.getsize(filename)
        max_ovr_gb = 1
        if file_size > max_ovr_gb * 1024 ** 3:
            ovr_type = OvrType.create_external_multi
        else:
            ovr_type = OvrType.create_external_single
    elif ovr_type not in [
        OvrType.create_internal,
        OvrType.create_external_single,
        OvrType.create_external_multi,
    ]:
        return None

    if ovr_options is None:
        ovr_options = dict()
    if config_options is None:
        config_options = dict()

    if multi_thread and multi_thread_support_available:
        multi_thread = multi_thread_to_str(multi_thread)
        config_options['GDAL_NUM_THREADS'] = multi_thread

    if resampling_alg is None:
        if kind in [None, ...]:
            kind = RasterKind.guess(filename)
        resampling_alg = kind.resampling_alg_by_kind()
    if resampling_alg is not ...:
        ovr_options["resampling"] = enum_to_str(resampling_alg)
    if print_progress:
        ovr_options["callback"] = print_progress_callback(print_progress)

    if comp is None:
        comp = gdalos_util.get_image_structure_metadata(filename, "COMPRESSION")
    if comp == "YCbCr JPEG":
        config_options["COMPRESS_OVERVIEW"] = "JPEG"
        config_options["PHOTOMETRIC_OVERVIEW"] = "YCBCR"
        config_options["INTERLEAVE_OVERVIEW"] = "PIXEL"
    else:
        config_options["COMPRESS_OVERVIEW"] = comp

    try:
        if config_options:
            if verbose:
                logger.info("config options: " + str(config_options))
            for k, v in config_options.items():
                gdal.SetConfigOption(k, v)

        out_filename = filename
        access_mode = gdal.GA_ReadOnly
        if ovr_type in (OvrType.create_internal, OvrType.create_external_single):
            if ovr_type == OvrType.create_internal:
                access_mode = gdal.GA_Update
            ovr_levels = []
            for i in range(dst_ovr_count):
                ovr_levels.append(
                    2 ** (i + 1)
                )  # ovr_levels = '2 4 8 16 32 64 128 256 512 1024'
            ovr_options["overviewlist"] = ovr_levels
            ret_code = add_ovr(
                out_filename,
                ovr_options,
                access_mode,
                overwrite,
                logger,
                ovr_files,
            )
        elif ovr_type == OvrType.create_external_multi:
            ovr_options["overviewlist"] = [2]
            ret_code = None
            for i in range(dst_ovr_count):
                ret_code = add_ovr(
                    filename,
                    ovr_options,
                    access_mode,
                    overwrite,
                    logger,
                    ovr_files,
                )
                if not ret_code:
                    break
                filename = gdalos_util.concat_paths(filename, ".ovr")
        else:
            raise Exception("invalid ovr type")
    finally:
        for key, val in config_options.items():
            gdal.SetConfigOption(key, None)
    return ret_code


def gdalos_info(filename_or_ds, overwrite=True, logger=None):
    filename_or_ds = Path(filename_or_ds)
    if os.path.isdir(filename_or_ds):
        raise Exception(f"input is a dir, not a file: {filename_or_ds}")
    if not os.path.isfile(filename_or_ds):
        raise Exception("file not found: {}".format(filename_or_ds))
    out_filename = gdalos_util.concat_paths(filename_or_ds, ".info")
    if not do_skip_if_exists(out_filename, overwrite=overwrite):
        with gdalos_util.OpenDS(filename_or_ds, logger=logger) as ds:
            gdal_info = gdal.Info(ds)
        with open(out_filename, "w") as w:
            w.write(gdal_info)
        return out_filename
    else:
        return None


def gdalos_vrt(
        filenames: MaybeSequence,
        filenames_expand: Optional[bool] = None,
        vrt_path=None,
        kind=None,
        resampling_alg=None,
        overwrite=True,
        logger=None,
):
    if gdalos_util.is_list_like(filenames):
        flatten_filenames = gdalos_util.flatten_and_expand_file_list(filenames, do_expand_glob=filenames_expand)
    else:
        flatten_filenames = [filenames]
    flatten_filenames = [str(f) for f in flatten_filenames]
    if not flatten_filenames:
        return None
    first_filename = flatten_filenames[0]
    if vrt_path is None:
        vrt_path = first_filename + ".vrt"

    if os.path.isdir(vrt_path):
        vrt_path = os.path.join(vrt_path, os.path.basename(first_filename) + ".vrt")
    if do_skip_if_exists(vrt_path, overwrite, logger):
        return vrt_path
    if os.path.isfile(vrt_path):
        raise Exception("could not delete vrt file: {}".format(vrt_path))
    os.makedirs(os.path.dirname(vrt_path), exist_ok=True)
    vrt_options = dict()
    if resampling_alg is None:
        if kind in [None, ...]:
            kind = RasterKind.guess(first_filename)
        resampling_alg = kind.resampling_alg_by_kind(kind)
    if resampling_alg is not ...:
        vrt_options["resampleAlg"] = enum_to_str(resampling_alg)
    vrt_options = gdal.BuildVRTOptions(*vrt_options)
    out_ds = gdal.BuildVRT(vrt_path, flatten_filenames, options=vrt_options)
    if out_ds is None:
        return None
    del out_ds
    success = os.path.isfile(vrt_path)
    if success:
        return vrt_path
    else:
        return None
