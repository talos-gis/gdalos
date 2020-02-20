import datetime
import logging
import os
import time
from enum import Enum, auto
from numbers import Real
from pathlib import Path
from typing import Optional, Sequence, List, Union, Tuple, TypeVar

import gdal
from gdalos_data import __version__
from gdalos import gdal_helper
from gdalos import gdalos_logger
from gdalos import get_extent
from gdalos import projdef
from gdalos.__util__ import with_param_dict
from gdalos.gdal_helper import concat_paths
from gdalos.rectangle import GeoRectangle


def print_time_now():
    info('Current time: {}'.format(datetime.datetime.now()))


class OvrType(Enum):
    auto_select = auto()  # existing_auto or create_external_auto (by existance of src overviews)
    create_external_auto = auto()  # create_external_single or create_external_multi (by size)
    create_external_single = auto()  # create a single .ovr file with all the overviews
    create_external_multi = auto()  # create one ovr file per overview: .ovr, .ovr.ovr, .ovr.ovr.orv ....
    create_internal = auto()  # create overviews inside the main dataset file
    existing_auto = auto()  # existing_reuse or create cog
    existing_reuse = auto()  # work with existing overviews


class RasterKind(Enum):
    photo = auto()
    pal = auto()
    dtm = auto()

    @classmethod
    def guess(cls, band_types_or_filename_or_ds):
        if isinstance(band_types_or_filename_or_ds, list):
            band_types = band_types_or_filename_or_ds
        else:
            band_types = gdal_helper.get_band_types(band_types_or_filename_or_ds)
        if len(band_types) == 0:
            raise Exception('no bands in raster')

        if band_types[0] == 'Byte':
            if len(band_types) in (3, 4):
                return cls.photo
            elif len(band_types) == 1:
                return cls.pal
            else:
                raise Exception("invalid raster band count")
        elif len(band_types) == 1:
            return cls.dtm

        raise Exception('could not guess raster kind')


def resampling_alg_by_kind(kind, expand_rgb=False):
    if kind is None:
        return None
    elif kind == RasterKind.pal:
        if expand_rgb:
            return 'average'
        else:
            return 'near'
    elif kind == RasterKind.dtm:
        return 'average'
    else:
        return 'cubic'


def do_skip_if_exists(out_filename, skip_if_exists, logger=None):
    verbose = logger is not None and logger is not ...
    skip = False
    if os.path.isfile(out_filename):
        if skip_if_exists:
            skip = True
            if verbose:
                logger.warning('file "{}" exists, skip!'.format(out_filename))
        else:
            if verbose:
                logger.warning('file "{}" exists, removing...!'.format(out_filename))
            os.remove(out_filename)
    return skip


def print_progress_from_to(r0, r1):
    # print(str(round(r1)) + '%', end=" ")
    i0 = 0 if (r0 is None) or (r0 > r1) else round(r0) + 1
    i1 = round(r1) + 1
    for i in range(i0, i1):
        print(str(i) if i % 5 == 0 else '.', end="", flush=True)
    if r1 >= 100:
        print('% done!')


def print_progress_callback(print_progress):
    if print_progress:
        if print_progress is ...:
            last = None

            def print_progress(prog, *_):
                nonlocal last

                percent = prog * 100
                r0 = last
                r1 = percent
                print_progress_from_to(r0, r1)
                last = percent
    return print_progress


T = TypeVar('T')
MaybeSequence = Union[T, Sequence[T]]
Warp_crs_base = Union[str, int, Real]
default_multi_byte_nodata_value = -32768


@with_param_dict('all_args')
def gdalos_trans(filename: MaybeSequence[str], 
                 out_filename: str = None, out_path: str = None, out_path_with_src_folders: str = True,
                 skip_if_exists=True, create_info=True, cog=True, multi_file_as_vrt=False,
                 of: MaybeSequence[str] = 'GTiff', outext: str = 'tif', tiled=True, big_tiff: str = 'IF_SAFER',
                 config_options: dict = None, open_options: dict = None, common_options: dict = None,
                 creation_options: dict = None,
                 extent: Union[Optional[GeoRectangle], List[GeoRectangle]] = None, src_win=None,
                 warp_CRS: MaybeSequence[Warp_crs_base] = None, out_res: Tuple[Real, Real] = None,
                 ovr_type: Optional[OvrType] = OvrType.auto_select,
                 src_ovr: Optional[int] = None, keep_src_ovr_suffixes: bool = True, dst_ovr_count: Optional[int] = None,
                 src_nodatavalue: Real = ..., dst_nodatavalue: Real = ..., hide_nodatavalue: bool = False,
                 kind: RasterKind = None, resampling_alg=None, lossy: bool = None, expand_rgb: bool = False,
                 jpeg_quality: Real = 75, keep_alpha: bool = True,
                 final_files: list = None, ovr_files: list = None, aux_files: list = None, temp_files: list = None,
                 delete_temp_files=True, partition=None,
                 print_progress=..., logger=..., write_spec=True, *, all_args: dict = None):
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
    if isinstance(ovr_type, str):
        ovr_type = OvrType[ovr_type]
    if isinstance(out_res, str):
        out_res = float(out_res)

    if isinstance(partition, int):
        partition = [GeoRectangle(i, j, partition, partition) for i in range(partition) for j in range(partition)]
        all_args['partition'] = partition

    key_list_arguments = ['filename', 'extent', 'warp_CRS', 'of', 'expand_rgb', 'partition']
    for key in key_list_arguments:
        val = all_args[key]
        val = gdal_helper.flatten_and_expand_file_list(val, do_expand_glob=key == 'filename')
        if key == 'filename':
            if gdal_helper.is_list_like(val) and multi_file_as_vrt:
                vrt_path = gdalos_vrt(val, resampling_alg=resampling_alg, kind=kind, skip_if_exists=skip_if_exists, logger=logger)
                if vrt_path is None:
                    raise Exception('failed to create a vrt file: {}'.format(vrt_path))  # failed?
                temp_files.append(vrt_path)
                val = vrt_path
            filename = val

        if gdal_helper.is_list_like(val):
            # input argument is a list, recurse over its values
            all_args_new = all_args.copy()
            ret_code = None
            for idx, v in enumerate(val):
                print('iterate over {} ({}/{}) - {}'.format(key, idx+1, len(val), v))
                all_args_new[key] = v
                all_args_new['temp_files'] = []
                all_args_new['final_files'] = []
                all_args_new['ovr_files'] = []
                all_args_new['aux_files'] = []
                ret_code = gdalos_trans(**all_args_new)
                temp_files.extend(all_args_new['temp_files'])
                final_files.extend(all_args_new['final_files'])
                ovr_files.extend(all_args_new['ovr_files'])
                aux_files.extend(all_args_new['aux_files'])
                # if ret_code is None:
                #     break  # failed?
            return ret_code
        else:
            all_args[key] = val  # adding the default parameters

    if not filename:
        return None
    start_time = time.time()

    # region console logger initialization
    logger_handlers = []
    if logger is ...:
        logger = logging.getLogger(__name__)
        logger_handlers.append(gdalos_logger.set_logger_console(logger))
        logger.debug('console handler added')
    if write_spec and logger is None:
        logger = logging.getLogger(__name__)
    all_args['logger'] = logger
    verbose = logger is not None and logger is not ...
    if verbose:
        logger.info(all_args)
    # endregion

    filename = Path(filename.strip())
    if os.path.isdir(filename):
        raise Exception('input is a dir, not a file: "{}"'.format(filename))
    if not os.path.isfile(filename):
        raise OSError('file not found: "{}"'.format(filename))

    # creating a copy of the input dictionaries, as I don't want to change the input
    config_options = dict(config_options or dict())
    common_options = dict(common_options or dict())
    creation_options = dict(creation_options or dict())
    translate_options = {}
    warp_options = {}
    out_suffixes = []

    extent_was_cropped = False
    input_ext = os.path.splitext(filename)[1].lower()
    input_is_vrt = input_ext == '.vrt'

    ds = gdal_helper.open_ds(filename, src_ovr=src_ovr, open_options=open_options, logger=logger)

    # region decideing which overviews to make
    if src_ovr is None:
        src_ovr = -1  # base raster
    overview_count = gdal_helper.get_ovr_count(ds)
    src_ovr_last = overview_count - 1
    if dst_ovr_count is not None:
        if dst_ovr_count >= 0:
            src_ovr_last = min(overview_count - 1, src_ovr + dst_ovr_count)
        else:
            # in this case we'll reopen the ds with a new src_ovr, because we want only the last overviews
            new_src_ovr = max(-1, overview_count + dst_ovr_count)
            if new_src_ovr != src_ovr:
                src_ovr = new_src_ovr
                del ds
                ds = gdal_helper.open_ds(filename, src_ovr=src_ovr, open_options=open_options, logger=logger)
    # endregion

    geo_transform = ds.GetGeoTransform()
    input_res = (geo_transform[1], geo_transform[5])

    band_types = gdal_helper.get_band_types(ds)
    if kind in [None, ...]:
        kind = RasterKind.guess(band_types)

    # region warp CRS handling
    pjstr_src_srs = projdef.get_srs_pj_from_ds(ds)
    pjstr_tgt_srs = None
    tgt_zone = None
    if warp_CRS is not None:
        if isinstance(warp_CRS, str) and warp_CRS.startswith('+'):
            pjstr_tgt_srs = warp_CRS  # ProjString
        else:
            tgt_zone = projdef.get_number(warp_CRS)
            if tgt_zone is None:
                tgt_zone = projdef.get_zone_from_name(warp_CRS)
            else:
                warp_CRS = f'w84u{warp_CRS}'
            # "short ProjString"
            pjstr_tgt_srs = projdef.get_proj4_string(warp_CRS[0], tgt_zone)
        if projdef.proj_is_equivalent(pjstr_src_srs, pjstr_tgt_srs):
            warp_CRS = None  # no warp is really needed here

    do_warp = warp_CRS is not None
    if warp_CRS is not None:
        if tgt_zone is not None:
            if tgt_zone != 0:
                # cropping according to tgt_zone bounds
                zone_extent = GeoRectangle.from_points(projdef.get_utm_zone_extent_points(tgt_zone))
                if extent is None:
                    extent = zone_extent
                else:
                    extent = zone_extent.crop(extent)
                extent_was_cropped = True
            out_suffixes.append(projdef.get_canonic_name(warp_CRS[0], tgt_zone))
        if kind == RasterKind.dtm:
            common_options['outputType'] = gdal.GDT_Float32  # 'Float32'
        warp_options["dstSRS"] = pjstr_tgt_srs
    # endregion

    # region compression
    resample_is_needed = warp_CRS is not None or (out_res is not None)
    org_comp = gdal_helper.get_image_structure_metadata(ds, 'COMPRESSION')
    src_is_lossy = (org_comp is not None) and ('JPEG' in org_comp)
    if lossy in [None, ...]:
        lossy = src_is_lossy or resample_is_needed
    if lossy and (kind == RasterKind.dtm):
        lossy = False
    if not lossy:
        comp = 'DEFLATE'
    else:
        comp = 'JPEG'
        out_suffixes.append('jpg')
    # endregion

    # region expand_rgb
    if kind == RasterKind.pal and expand_rgb:
        translate_options['rgbExpand'] = 'rgb'
        out_suffixes.append('rgb')
    # endregion

    # region nodatavalue
    if (dst_nodatavalue is ...):
        if (kind == RasterKind.dtm):
            dst_nodatavalue = default_multi_byte_nodata_value
        else:
            dst_nodatavalue = None
    if (dst_nodatavalue is not None):
        src_nodatavalue_org = gdal_helper.get_nodatavalue(ds)
        if src_nodatavalue is ...:
            src_nodatavalue = src_nodatavalue_org
        if src_nodatavalue is None:
            # assume raster minimum is nodata if nodata isn't set
            src_min_value = gdal_helper.get_raster_minimum(ds)
            if abs(src_min_value - default_multi_byte_nodata_value) < 100:
                src_nodatavalue = src_min_value
        if src_nodatavalue is not None:
            if src_nodatavalue != dst_nodatavalue:
                do_warp = True
                warp_options['dstNodata'] = dst_nodatavalue

            if src_nodatavalue_org != src_nodatavalue:
                translate_options['noData'] = src_nodatavalue
                warp_options['srcNodata'] = src_nodatavalue
    # endregion

    # region extent
    org_points_extent, _ = get_extent.get_points_extent_from_ds(ds)
    org_extent_in_src_srs = GeoRectangle.from_points(org_points_extent)
    if org_extent_in_src_srs.is_empty():
        raise Exception(f'no input extent: {filename} [{org_extent_in_src_srs}]')
    out_extent_in_src_srs = org_extent_in_src_srs
    if extent is not None or partition is not None:
        pjstr_4326 = projdef.get_proj4_string('w')  # 'EPSG:4326'
        if extent is None:
            transform = get_extent.get_transform(pjstr_src_srs, pjstr_4326)
            extent = get_extent.translate_extent(org_extent_in_src_srs, transform)
        if pjstr_tgt_srs is None:
            pjstr_tgt_srs = pjstr_src_srs
            transform = None
        else:
            transform = get_extent.get_transform(pjstr_src_srs, pjstr_tgt_srs)

        org_extent_in_tgt_srs = get_extent.translate_extent(org_extent_in_src_srs, transform)
        if org_extent_in_tgt_srs.is_empty():
            raise Exception(f'no input extent: {filename} [{org_extent_in_tgt_srs}]')

        transform = get_extent.get_transform(pjstr_4326, pjstr_tgt_srs)
        out_extent_in_tgt_srs = get_extent.translate_extent(extent, transform)
        out_extent_in_tgt_srs = out_extent_in_tgt_srs.crop(org_extent_in_tgt_srs)

        if out_extent_in_tgt_srs != org_extent_in_tgt_srs:
            extent_was_cropped = True
            transform = get_extent.get_transform(pjstr_tgt_srs, pjstr_4326)
            extent = get_extent.translate_extent(out_extent_in_tgt_srs, transform)

        if out_extent_in_tgt_srs.is_empty():
            raise Exception(f'no output extent: {filename} [{out_extent_in_tgt_srs}]')

        if partition:
            out_extent_in_tgt_srs_part = out_extent_in_tgt_srs.get_partition(partition)
        else:
            out_extent_in_tgt_srs_part = out_extent_in_tgt_srs

        # -projwin minx maxy maxx miny (ulx uly lrx lry)
        translate_options['projWin'] = out_extent_in_tgt_srs_part.lurd
        # -te minx miny maxx maxy
        warp_options['outputBounds'] = out_extent_in_tgt_srs_part.ldru

        transform = get_extent.get_transform(pjstr_4326, pjstr_src_srs)
        out_extent_in_src_srs = get_extent.translate_extent(extent, transform)
        out_extent_in_src_srs = out_extent_in_src_srs.crop(org_extent_in_src_srs)
        if out_extent_in_src_srs.is_empty():
            raise Exception
    elif src_win is not None:
        translate_options['srcWin'] = src_win
    # endregion

    # region out_res
    if out_res is not None:
        if not isinstance(out_res, Sequence):
            out_res = [out_res, -out_res]
    elif warp_CRS is not None:
        transform_src_tgt = get_extent.get_transform(pjstr_src_srs, pjstr_tgt_srs)
        if transform_src_tgt is not None:
            out_res = get_extent.transform_resolution(transform_src_tgt, input_res, out_extent_in_src_srs)
    if out_res is not None:
        common_options['xRes'], common_options['yRes'] = out_res
        warp_options['targetAlignedPixels'] = True
        out_suffixes.append(str(out_res))
    elif src_ovr >= 0:
        out_res = input_res
    # endregion

    # region jpeg
    # if (comp == 'JPEG') and (len(bands) == 3) or ((len(bands) == 4) and (keep_alpha)):
    if (comp == 'JPEG') and (len(band_types) in (3, 4)):
        creation_options['PHOTOMETRIC'] = 'YCBCR'
        creation_options['JPEG_QUALITY'] = str(jpeg_quality)

        if len(band_types) == 4:  # alpha channel is not supported with PHOTOMETRIC=YCBCR, thus we drop it or keep it as a mask band
            if do_warp:
                raise Exception(
                    'this mode is not supported: warp RGBA raster with JPEG output, you could do it in two steps: 1. warp with lossless ouput, 2. save as jpeg')
            else:
                translate_options['bandList'] = [1, 2, 3]
                if keep_alpha:
                    translate_options['maskBand'] = 4  # keep the alpha band as mask
    # endregion

    # region decide ovr_type
    if ovr_type is None:
        cog = False
    cog_2_steps = cog
    if ovr_type in [..., OvrType.auto_select]:
        if overview_count > 0:
            # if the raster has overviews then use them, otherwise create overviews
            ovr_type = OvrType.existing_auto
        else:
            ovr_type = OvrType.create_external_auto

    trans_or_warp_is_needed = bool(extent or src_win or resample_is_needed or (lossy != src_is_lossy) or translate_options)
    if ovr_type in [None, OvrType.existing_reuse, OvrType.existing_auto]:
        can_cog = not trans_or_warp_is_needed
        if cog and can_cog:
            cog_2_steps = False
        elif ovr_type == OvrType.existing_auto:
            ovr_type = OvrType.existing_reuse
    # endregion

    # region make out_filename
    auto_out_filename = out_filename is None
    if auto_out_filename:
        if cog_2_steps and ovr_type == OvrType.create_external_auto and not trans_or_warp_is_needed and not input_is_vrt:
            # create overviews for the input file then create a cog
            out_filename = filename
        else:
            out_extent_in_4326 = extent
            if extent_was_cropped and (out_extent_in_src_srs is not None):
                transform = get_extent.get_transform(pjstr_src_srs, pjstr_4326)
                out_extent_in_4326 = get_extent.translate_extent(out_extent_in_src_srs, transform)
            if out_extent_in_4326 is not None:
                out_suffixes.append('x[{},{}]_y[{},{}]'.format(*(round(x,2) for x in out_extent_in_4326.lrdu)))
            elif src_win is not None:
                out_suffixes.append('off[{},{}]_size[{},{}]'.format(*src_win))
            if partition is not None:
                out_suffixes.append('part_x[{},{}]_y[{},{}]'.format(*partition.xwyh))
            if not out_suffixes:
                if '.' + outext.lower() == input_ext:
                    out_suffixes.append('new')
            if out_suffixes:
                out_suffixes = '.' + '.'.join(out_suffixes)
            else:
                out_suffixes = ''
            out_filename = gdal_helper.concat_paths(filename, out_suffixes + '.' + outext)
            if keep_src_ovr_suffixes:
                out_filename = gdal_helper.concat_paths(out_filename, '.ovr' * (src_ovr + 1))
    else:
        out_filename = Path(out_filename)

    if out_path is not None:
        if out_path_with_src_folders:
            out_src_path = out_filename.parts[1:]
        else:
            out_src_path = [out_filename.parts[-1]]
        out_filename = Path(out_path).joinpath(*out_src_path)

    if not os.path.exists(os.path.dirname(out_filename)):
        os.makedirs(os.path.dirname(out_filename), exist_ok=True)

    if cog:
        if auto_out_filename:
            cog_filename = out_filename.with_suffix('.cog' + '.' + outext)
            if not cog_2_steps:
                out_filename = cog_filename
        else:
            cog_filename = out_filename
            if cog_2_steps:
                out_filename = out_filename.with_suffix('.temp' + '.' + outext)
    else:
        cog_filename = out_filename
    # endregion

    if cog_2_steps:
        final_files_for_step_1 = temp_files
        ovr_files_for_step_1 = temp_files
    else:
        final_files_for_step_1 = final_files
        ovr_files_for_step_1 = ovr_files

    cog_ready = cog and do_skip_if_exists(cog_filename, skip_if_exists, logger)
    if cog_ready or ovr_type == OvrType.existing_reuse or (filename == out_filename):
        skipped = True
    else:
        skipped = do_skip_if_exists(out_filename, skip_if_exists, logger)

    if not cog_ready and write_spec:
        spec_filename = gdal_helper.concat_paths(cog_filename, '.spec')
        logger_handlers.append(gdalos_logger.set_file_logger(logger, spec_filename))
        logger.debug('spec file handler added: "{}"'.format(spec_filename))
        logger.debug('gdalos versoin: {}'.format(__version__))
        aux_files.append(spec_filename)
        # logger.debug('debug')
        # logger.info('info')
        # logger.warning('warning')
        # logger.error('error')
        # logger.critical('critical')

    # region create base raster
    ret_code = None
    if not skipped:
        no_yes = ('NO', 'YES')
        if not isinstance(tiled, str):
            tiled = no_yes[tiled]
        creation_options['TILED'] = tiled
        creation_options['BIGTIFF'] = big_tiff
        creation_options['COMPRESS'] = comp
        common_options['format'] = of
        if cog and not cog_2_steps:
            creation_options['COPY_SRC_OVERVIEWS'] = 'YES'

        if creation_options:
            creation_options_list = []
            for k, v in creation_options.items():
                creation_options_list.append('{}={}'.format(k, v))
            common_options['creationOptions'] = creation_options_list

        if print_progress:
            common_options['callback'] = print_progress_callback(print_progress)

        if resample_is_needed:
            if resampling_alg in [None, ...]:
                resampling_alg = resampling_alg_by_kind(kind, expand_rgb)
            if resampling_alg is not None:
                common_options['resampleAlg'] = resampling_alg

        if verbose:
            logger.info('filename: "' + str(out_filename) + '" ...')
            if common_options:
                logger.info('common options: ' + str(common_options))

        if input_ext == '.xml':
            config_options = {'GDAL_HTTP_UNSAFESSL': 'YES'}  # for gdal-wms xml files

        try:
            if config_options:
                if verbose:
                    logger.info('config options: ' + str(config_options))
                for k, v in config_options.items():
                    gdal.SetConfigOption(k, v)

            if do_warp:
                if verbose and warp_options:
                    logger.info('wrap options: ' + str(warp_options))
                ret_code = gdal.Warp(str(out_filename), ds, **common_options, **warp_options) is not None
            else:
                if verbose and translate_options:
                    logger.info('translate options: ' + str(translate_options))
                ret_code = gdal.Translate(str(out_filename), ds, **common_options, **translate_options) is not None
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
            logger.info('time: {} for creating file: "{}"'.format(time_string, out_filename))

    if verbose:
        logger.debug('closing file: "{}"'.format(filename))
    del ds
    #end region

    # region create overviews, cog, info
    if not cog_ready and (ret_code or skipped):
        if not skipped and hide_nodatavalue:
            gdal_helper.unset_nodatavalue(str(out_filename))

        if ovr_type == OvrType.existing_reuse:
            # overviews are numbered as follows (i.e. for dst_ovr_count=3, meaning create base+3 ovrs=4 files):
            # -1: base dataset, 0: first ovr, 1: second ovr, 2: third ovr

            all_args_new = all_args.copy()
            all_args_new['ovr_type'] = None
            all_args_new['dst_ovr_count'] = None
            all_args_new['out_path'] = None
            all_args_new['write_spec'] = False
            all_args_new['cog'] = False
            all_args_new['logger'] = logger
            # iterate backwards on the overviews
            if verbose:
                logger.debug('iterate on overviews creation, from {} to {}'.format(src_ovr_last, src_ovr))
            for ovr_index in range(src_ovr_last, src_ovr - 1, -1):
                all_args_new['final_files'] = []
                all_args_new['ovr_files'] = []  # there shouldn't be any
                all_args_new['aux_files'] = []
                all_args_new['temp_files'] = []  # there shouldn't be any
                all_args_new['out_filename'] = concat_paths(out_filename, '.ovr' * (ovr_index - src_ovr))
                all_args_new['src_ovr'] = ovr_index
                if out_res is not None:
                    res_factor = 2**(ovr_index+1)
                    all_args_new['out_res'] = [r * res_factor for r in out_res]
                all_args_new['create_info'] = create_info and (ovr_index == src_ovr) and not cog
                ret_code = gdalos_trans(**all_args_new)
                if not ret_code:
                    logger.warning('return code was None for creating {}'.format(all_args_new['out_filename']))
                if ovr_index == src_ovr:
                    final_files_for_step_1.extend(all_args_new['final_files'])
                else:
                    ovr_files_for_step_1.extend(all_args_new['final_files'])
                if verbose:
                    for f in ['ovr_files', 'temp_files']:
                        if all_args_new[f]:
                            logger.error(
                                'there shound not be any {} here, but there are! {}'.format(f, all_args_new[f]))
                    if len(all_args_new['final_files']) != 1:
                        logger.error(
                            'ovr creating should have made exactly 1 file! {}'.format(all_args_new['final_files']))
                aux_files.extend(all_args_new['aux_files'])
            create_info = create_info and cog
        elif (ovr_type not in [None, OvrType.existing_reuse, OvrType.existing_auto]):
            # create overviews from dataset (internal or external)
            ret_code = gdalos_ovr(out_filename, skip_if_exists=skip_if_exists,
                                  ovr_type=ovr_type, dst_ovr_count=dst_ovr_count,
                                  kind=kind, resampling_alg=resampling_alg,
                                  print_progress=print_progress, logger=logger, ovr_files=ovr_files_for_step_1)
        if cog_2_steps:
            if verbose:
                logger.debug('running cog 2nd step...')
            cog_final_files = []  # there should be exactly one!
            cog_temp_files = []  # there shouldn't be any!
            cog_ovr_files = []  # there shouldn't be any!
            cog_aux_files = []
            ret_code = gdalos_trans(out_filename, out_filename=cog_filename, cog=True, ovr_type=OvrType.existing_auto,
                                    of=of, outext=outext, tiled=tiled, big_tiff=big_tiff,
                                    print_progress=print_progress,
                                    final_files=cog_final_files, ovr_files=cog_ovr_files, aux_files=cog_aux_files,
                                    temp_files=cog_temp_files, delete_temp_files=False,
                                    logger=logger, skip_if_exists=skip_if_exists, create_info=create_info,
                                    write_spec=False)
            if ret_code and verbose:
                if cog_temp_files:
                    logger.error('cog 2nd step should not have any temp files, but it has! {}'.format(cog_temp_files))
                if len(cog_final_files) != 1:
                    logger.error('cog 2nd step should have made exactly 1 file! {}'.format(cog_final_files))
            final_files.extend(cog_final_files)
            aux_files.extend(cog_aux_files)
            create_info = False  # we don't need an info for the temp file from first step
        if create_info:
            info = gdalos_info(out_filename, skip_if_exists=skip_if_exists, logger=logger)
            if info is not None:
                aux_files.append(info)
    # endregion

    # region log file lists
    if verbose:
        if final_files:
            logger.info('final_files: {}'.format(final_files))
        if aux_files:
            logger.info('aux_files: {}'.format(aux_files))
        if temp_files:
            if delete_temp_files:
                deleted = ''
            else:
                deleted = 'not '
            logger.info('temp_files (will {}be deleted): {}'.format(deleted, temp_files))
    # endregion

    # region delete temp files
    if delete_temp_files and temp_files:
        for f in temp_files:
            if f == filename:
                if verbose:
                    logger.error('somehow the input file was set as a temp file for deletion: "{}")'.format(f))
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
        logger.info('*** done! ***\n')

    # region remove loggers
    if logger_handlers:
        logger.debug('removing {} logging handlers'.format(len(logger_handlers)))
        for handler in logger_handlers:
            handler.close()
            logger.removeHandler(handler)
        logger.debug('logging handlers removed')  # this shouldn't log anything
    # end region
    return ret_code


def add_ovr(filename, options, access_mode, skip_if_exists=False, logger=None, ovr_files: list = None):
    verbose = logger is not None and logger is not ...
    filename = Path(filename)
    out_filename = gdal_helper.concat_paths(filename, '.ovr')
    if not do_skip_if_exists(out_filename, skip_if_exists, logger):
        if verbose:
            logger.info('adding ovr for: "{}" options: {} access_mode: {}'.format(out_filename, options, access_mode))
        with gdal_helper.OpenDS(filename, access_mode=access_mode, logger=logger) as ds:
            ret_code = ds.BuildOverviews(**options) == 0
            if ret_code and ovr_files is not None:
                ovr_files.append(out_filename)
            return ret_code
    else:
        return None


default_dst_ovr_count = 10


def gdalos_ovr(filename, comp=None, skip_if_exists=False,
               ovr_type=..., dst_ovr_count=default_dst_ovr_count,
               kind=None, resampling_alg=None,
               config_options: dict = None, ovr_options: dict = None,
               ovr_files: list = None, print_progress=..., logger=None):
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

    if ovr_type in [..., OvrType.auto_select, OvrType.create_external_auto]:
        file_size = os.path.getsize(filename)
        max_ovr_gb = 1
        if file_size > max_ovr_gb * 1024 ** 3:
            ovr_type = OvrType.create_external_multi
        else:
            ovr_type = OvrType.create_external_single
    elif ovr_type not in [OvrType.create_internal, OvrType.create_external_single, OvrType.create_external_multi]:
        return None

    if ovr_options is None:
        ovr_options = dict()
    if config_options is None:
        config_options = dict()
    if resampling_alg in [None, ...]:
        if kind in [None, ...]:
            kind = RasterKind.guess(filename)
        resampling_alg = resampling_alg_by_kind(kind)
    if resampling_alg is not None:
        ovr_options['resampling'] = resampling_alg
    if print_progress:
        ovr_options['callback'] = print_progress_callback(print_progress)

    if comp is None:
        comp = gdal_helper.get_image_structure_metadata(filename, 'COMPRESSION')
    if comp == 'YCbCr JPEG':
        config_options['COMPRESS_OVERVIEW'] = 'JPEG'
        config_options['PHOTOMETRIC_OVERVIEW'] = 'YCBCR'
        config_options['INTERLEAVE_OVERVIEW'] = 'PIXEL'
    else:
        config_options['COMPRESS_OVERVIEW'] = comp

    try:
        if config_options:
            if verbose:
                logger.info('config options: ' + str(config_options))
            for k, v in config_options.items():
                gdal.SetConfigOption(k, v)

        out_filename = filename
        access_mode = gdal.GA_ReadOnly
        if ovr_type in (OvrType.create_internal, OvrType.create_external_single):
            if ovr_type == OvrType.create_internal:
                access_mode = gdal.GA_Update
            ovr_levels = []
            for i in range(dst_ovr_count):
                ovr_levels.append(2 ** (i + 1))  # ovr_levels = '2 4 8 16 32 64 128 256 512 1024'
            ovr_options['overviewlist'] = ovr_levels
            ret_code = add_ovr(out_filename, ovr_options, access_mode, skip_if_exists, logger, ovr_files)
        elif ovr_type == OvrType.create_external_multi:
            ovr_options['overviewlist'] = [2]
            ret_code = None
            for i in range(dst_ovr_count):
                ret_code = add_ovr(filename, ovr_options, access_mode, skip_if_exists, logger, ovr_files)
                if not ret_code:
                    break
                filename = gdal_helper.concat_paths(filename, '.ovr')
        else:
            raise Exception('invalid ovr type')
    finally:
        for key, val in config_options.items():
            gdal.SetConfigOption(key, None)
    return ret_code


def gdalos_info(filename, skip_if_exists=False, logger=None):
    filename = Path(filename)
    if os.path.isdir(filename):
        raise Exception(f'input is a dir, not a file: {filename}')
    if not os.path.isfile(filename):
        raise Exception('file not found: {}'.format(filename))
    out_filename = gdal_helper.concat_paths(filename, '.info')
    if not do_skip_if_exists(out_filename, skip_if_exists=skip_if_exists):
        with gdal_helper.OpenDS(filename, logger=logger) as ds:
            gdal_info = gdal.Info(ds)
        with open(out_filename, 'w') as w:
            w.write(gdal_info)
        return out_filename
    else:
        return None


def gdalos_vrt(filenames: MaybeSequence, vrt_path=None, kind=None, resampling_alg=None, skip_if_exists=True, logger=None):
    if gdal_helper.is_list_like(filenames):
        flatten_filenames = gdal_helper.flatten_and_expand_file_list(filenames)
    else:
        flatten_filenames = [filenames]
    flatten_filenames = [str(f) for f in flatten_filenames]
    if not flatten_filenames:
        return None
    first_filename = flatten_filenames[0]
    if vrt_path is None:
        vrt_path = first_filename + '.vrt'

    if os.path.isdir(vrt_path):
        vrt_path = os.path.join(vrt_path, os.path.basename(first_filename) + '.vrt')
    if do_skip_if_exists(vrt_path, skip_if_exists, logger):
        return vrt_path
    if os.path.isfile(vrt_path):
        raise Exception('could not delete var file: {}'.format(vrt_path))
    os.makedirs(os.path.dirname(vrt_path), exist_ok=True)
    vrt_options = dict()
    if resampling_alg in [None, ...]:
        if kind in [None, ...]:
            kind = RasterKind.guess(first_filename)
        resampling_alg = resampling_alg_by_kind(kind)
    if resampling_alg is not None:
        vrt_options['resampleAlg'] = resampling_alg
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
