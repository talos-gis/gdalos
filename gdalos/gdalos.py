from typing import Optional, Sequence, List, Union, Tuple, TypeVar

import os
import time
import datetime
from numbers import Real
import logging
from gdalos import gdalos_logger
from enum import Enum, auto
from pathlib import Path

import gdal

from gdalos import gdal_helper
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
    def guess(cls, bands):
        if gdal_helper.is_path_like(bands):
            bands = gdal_helper.get_band_types(bands)
        if len(bands) == 0:
            raise Exception('no bands in raster')

        if bands[0] == 'Byte':
            if len(bands) in (3, 4):
                return cls.photo
            elif len(bands) == 1:
                return cls.pal
            else:
                raise Exception("invalid raster band count")
        elif len(bands) == 1:
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
    verbose = logger is not None
    skip = False
    if os.path.isfile(out_filename):
        if skip_if_exists:
            skip = True
            if verbose:
                logger.warning('file {} exits, skip!\n'.format(out_filename))
        else:
            if verbose:
                logger.warning('file {} exits, removing...!\n'.format(out_filename))
            os.remove(out_filename)
            if verbose:
                logger.warning('file {} removed!\n'.format(out_filename))
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
def gdalos_trans(filename: MaybeSequence[str], out_filename: str = None, out_base_path: str = None,
                 skip_if_exists=True, create_info=True, cog=False, multi_file_as_vrt=False,
                 of: MaybeSequence[str] = 'GTiff', outext: str = 'tif', tiled=True, big_tiff: str = 'IF_SAFER',
                 config_options: dict = None, open_options: dict = None, common_options:dict=None, creation_options:dict = None,
                 extent: Union[Optional[GeoRectangle], List[GeoRectangle]] = None, src_win=None,
                 warp_CRS: MaybeSequence[Warp_crs_base] = None, out_res: Tuple[Real, Real] = None,
                 ovr_type: Optional[OvrType] = OvrType.auto_select,
                 src_ovr: Optional[int] = None, keep_src_ovr_suffixes: bool = True, dst_ovr_count: Optional[int] = None,
                 src_nodatavalue: Real = ..., dst_nodatavalue: Real = ..., hide_nodatavalue: bool = False,
                 kind: RasterKind = None, resampling_alg=None, lossy: bool = None, expand_rgb: bool = False,
                 jpeg_quality: Real = 75, keep_alpha: bool = True,
                 print_progress=..., print_time=False, logger=..., write_spec=True, *, all_args: dict = None):

    logger_handlers = []
    if logger is ...:
        logger = logging.getLogger(__name__)
        logger_handlers.append(gdalos_logger.set_logger_console(logger))
    if write_spec and logger is None:
        logger = logging.getLogger(__name__)
    all_args['logger'] = logger
    verbose = logger is not None
    if verbose:
        logger.info(all_args)

    if isinstance(ovr_type, str):
        ovr_type = OvrType[ovr_type]
    if isinstance(kind, str):
        kind = RasterKind[kind]

    key_list_arguments = ['filename', 'extent', 'warp_CRS', 'of', 'expand_rgb']

    for key in key_list_arguments:
        val = all_args[key]
        val = gdal_helper.flatten_and_expand_file_list(val, do_expand_glob=key == 'filename')
        if key == 'filename':
            if gdal_helper.is_list_like(val) and multi_file_as_vrt:
                vrt_filename = gdalos_vrt(val, resampling_alg=resampling_alg)
                if vrt_filename is None:
                    raise Exception  # failed?
            filename = val

        if gdal_helper.is_list_like(val):
            # input argument is a list, recurse over its values
            all_args_new = all_args.copy()
            ret_code = None
            for v in val:
                all_args_new[key] = v
                ret_code = gdalos_trans(**all_args_new)
                if ret_code is None:
                    break  # failed?
            return ret_code
        else:
            all_args[key] = val  # adding the default parameters

    if not filename:
        return None
    filename = Path(filename.strip())

    if os.path.isdir(filename):
        raise Exception(f'input is a dir, not a file: {filename}')

    if not os.path.isfile(filename):
        raise OSError(f'file not found: {filename}')

    if print_time:
        start_time = time.time()
    else:
        start_time = None

    if config_options is None:
        config_options = dict()
    if common_options is None:
        common_options = dict()
    if creation_options is None:
        creation_options = dict()

    extent_was_cropped = False
    input_ext = os.path.splitext(filename)[1].lower()

    if print_progress:
        common_options['callback'] = print_progress_callback(print_progress)

    ds = gdal_helper.open_ds(filename, src_ovr=src_ovr, open_options=open_options, logger=logger)

    if src_ovr is None:
        src_ovr = -1  # base raster
    overview_count = gdal_helper.get_ovr_count(ds)
    src_ovr_last = overview_count - 1
    if dst_ovr_count is not None:
        if dst_ovr_count >= 0:
            src_ovr_last = min(overview_count - 1, src_ovr + dst_ovr_count)
        else:
            # in this case we'll reopen the ds with a new src_ovr, becuase we want only the last ovrs
            new_src_ovr = max(-1, overview_count + dst_ovr_count)
            if new_src_ovr != src_ovr:
                src_ovr = new_src_ovr
                del ds
                ds = gdal_helper.open_ds(filename, src_ovr=src_ovr, open_options=open_options, logger=logger)

    geo_transform = ds.GetGeoTransform()
    input_res = (geo_transform[1], geo_transform[5])
    translate_options = {}
    warp_options = {}
    do_warp = (warp_CRS is not None)

    band_types = gdal_helper.get_band_types(ds)
    if kind in [None, ...]:
        kind = RasterKind.guess(band_types)
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
            src_nodatavalue = gdal_helper.get_raster_minimum(ds)
            if abs(src_nodatavalue - default_multi_byte_nodata_value)>100:
                src_nodatavalue = None

        if src_nodatavalue != dst_nodatavalue:
            do_warp = True
            warp_options['dstNodata'] = dst_nodatavalue

        if src_nodatavalue_org != src_nodatavalue:
            translate_options['noData'] = src_nodatavalue
            warp_options['srcNodata'] = src_nodatavalue

    out_suffixes = []

    if kind == RasterKind.pal and expand_rgb:
        translate_options['rgbExpand'] = 'rgb'
        out_suffixes.append('rgb')

    if resampling_alg in [None, ...]:
        resampling_alg = resampling_alg_by_kind(kind, expand_rgb)
    if resampling_alg is not None:
        common_options['resampleAlg'] = resampling_alg

    pjstr_tgt_srs = None
    if warp_CRS is not None:
        if lossy is None:
            lossy = True

        if isinstance(warp_CRS, str) and warp_CRS.startswith('+'):
            pjstr_tgt_srs = warp_CRS  # ProjString
        else:
            zone = projdef.get_number(warp_CRS)
            if zone is None:
                zone = projdef.get_zone_from_name(warp_CRS)
            else:
                warp_CRS = f'w84u{warp_CRS}'
            # "short ProjString"
            pjstr_tgt_srs = projdef.get_proj4_string(warp_CRS[0], zone)
            if zone != 0:
                # cropping according to zone bounds
                zone_extent = GeoRectangle.from_points(projdef.get_utm_zone_extent_points(zone))
                if extent is None:
                    extent = zone_extent
                else:
                    extent = zone_extent.crop(extent)
                extent_was_cropped = True
            out_suffixes.append(projdef.get_canonic_name(warp_CRS[0], zone))

        if kind == RasterKind.dtm:
            common_options['outputType'] = gdal.GDT_Float32  # 'Float32'

        warp_options["dstSRS"] = pjstr_tgt_srs

    # todo I dunno what this is but instinct says var names this long should be in their own function
    out_extent_in_src_srs = None
    if extent is not None:
        org_points_extent, pjstr_src_srs, _ = get_extent.get_points_extent_from_ds(ds)
        org_extent_in_src_srs = GeoRectangle.from_points(org_points_extent)
        if org_extent_in_src_srs.is_empty():
            raise Exception(f'no input extent: {filename} [{org_extent_in_src_srs}]')

        if pjstr_tgt_srs is None:
            pjstr_tgt_srs = pjstr_src_srs
            transform = None
        else:
            transform = get_extent.get_transform(pjstr_src_srs, pjstr_tgt_srs)

        org_extent_in_tgt_srs = get_extent.translate_extent(org_extent_in_src_srs, transform)
        if org_extent_in_tgt_srs.is_empty():
            raise Exception(f'no input extent: {filename} [{org_extent_in_tgt_srs}]')

        pjstr_4326 = projdef.get_proj4_string('w')  # 'EPSG:4326'
        transform = get_extent.get_transform(pjstr_4326, pjstr_tgt_srs)
        out_extent_in_tgt_srs = get_extent.translate_extent(extent, transform)
        out_extent_in_tgt_srs = out_extent_in_tgt_srs.crop(org_extent_in_tgt_srs)
        if not ((out_extent_in_tgt_srs == org_extent_in_tgt_srs)
                or (transform is None and out_extent_in_tgt_srs == extent)):
            extent_was_cropped = True

        if out_extent_in_tgt_srs.is_empty():
            raise Exception(f'no output extent: {filename} [{out_extent_in_tgt_srs}]')

        # -projwin minx maxy maxx miny (ulx uly lrx lry)
        translate_options['projWin'] = out_extent_in_tgt_srs.lurd
        # -te minx miny maxx maxy
        warp_options['outputBounds'] = out_extent_in_tgt_srs.ldru

        transform = get_extent.get_transform(pjstr_4326, pjstr_src_srs)
        if transform is not None:
            out_extent_in_src_srs = get_extent.translate_extent(extent, transform)
        else:
            out_extent_in_src_srs = extent
        out_extent_in_src_srs = out_extent_in_src_srs.crop(org_extent_in_src_srs)
        if out_extent_in_src_srs.is_empty():
            raise Exception

        if out_res is None:
            transform_src_tgt = get_extent.get_transform(pjstr_src_srs, pjstr_tgt_srs)
            if transform_src_tgt is not None:
                in_res_y = input_res[1]  # geo_transform[5]  # Mpp.Y == geotransform[5]
                out_res_x = get_extent.transform_resolution(transform_src_tgt, in_res_y, *out_extent_in_src_srs.lrdu)
                out_res_x = get_extent.round_to_sig(out_res_x, -1)
                out_res = (out_res_x, -out_res_x)
    elif src_win is not None:
        translate_options['srcWin'] = src_win

    if out_res is None and src_ovr >= 0:
        out_res = input_res

    if out_res is not None:
        common_options['xRes'], common_options['yRes'] = out_res
        warp_options['targetAlignedPixels'] = True
        out_suffixes.append(str(out_res))

    org_comp = gdal_helper.get_image_structure_metadata(ds, 'COMPRESSION')
    if lossy is None:
        lossy = (org_comp is not None) and ('JPEG' in org_comp)
    if lossy and (kind != RasterKind.dtm):
        comp = 'JPEG'
        out_suffixes.append('jpg')
    else:
        lossy = False
        comp = 'DEFLATE'

    # if (comp == 'JPEG') and (len(bands) == 3) or ((len(bands) == 4) and (keep_alpha)):
    if (comp == 'JPEG') and (len(band_types) in (3, 4)):
        creation_options['PHOTOMETRIC'] = 'YCBCR'
        creation_options['JPEG_QUALITY'] = str(jpeg_quality)

        if len(band_types) == 4:  # alpha channel is not supported with PHOTOMETRIC=YCBCR, thus we drop it
            translate_options['bandList'] = [1, 2, 3]
            if keep_alpha:
                translate_options['maskBand'] = 4  # keep the alpha band as mask

    no_yes = ('NO', 'YES')
    if not isinstance(tiled, str):
        tiled = no_yes[tiled]
    creation_options['TILED'] = tiled
    creation_options['BIGTIFF'] = big_tiff
    creation_options['COMPRESS'] = comp
    common_options['format'] = of

    # decide ovr_type
    cog_2_steps = cog
    if ovr_type in [..., OvrType.auto_select]:
        if overview_count > 0:
            # if the raster has overviews then use them, otherwise create overviews
            ovr_type = OvrType.existing_auto
        else:
            ovr_type = OvrType.create_external_auto

    trans_or_warp = extent or src_win or warp_CRS or out_res or lossy or translate_options or warp_options
    if ovr_type == OvrType.existing_auto:
        can_cog = not trans_or_warp
        if cog and can_cog:
            cog_2_steps = False
        else:
            ovr_type = OvrType.existing_reuse

    if cog and not cog_2_steps:
        creation_options['COPY_SRC_OVERVIEWS'] = 'YES'

    # make out_filename
    auto_out_filename = out_filename is None
    if auto_out_filename:
        if cog_2_steps and ovr_type == OvrType.create_external_auto and not trans_or_warp:
            # create overviews for the input file then create a cog
            out_filename = filename
        else:
            out_extent_in_4326 = extent
            if extent_was_cropped and (out_extent_in_src_srs is not None):
                transform = get_extent.get_transform(pjstr_src_srs, pjstr_4326)
                if transform is not None:
                    out_extent_in_4326 = get_extent.translate_extent(out_extent_in_src_srs, transform)
                else:
                    out_extent_in_4326 = out_extent_in_src_srs
                out_extent_in_4326 = round(out_extent_in_4326, 2)
            if out_extent_in_4326 is not None:
                out_suffixes.append('x[{},{}]_y[{},{}]'.format(*out_extent_in_4326.lrdu))
            elif src_win is not None:
                out_suffixes.append('off[{},{}]_size[{},{}]'.format(*src_win))
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

    if out_base_path is not None:
        out_filename = Path(out_base_path).joinpath(*out_filename.parts[1:])

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

    if write_spec:
        spec_filename = gdal_helper.concat_paths(cog_filename, '.spec')
        logger_handlers.append(gdalos_logger.set_file_logger(logger, spec_filename))

    if ovr_type == OvrType.existing_reuse or (filename==out_filename):
        skipped = True
    else:
        skipped = do_skip_if_exists(out_filename, skip_if_exists, logger)

    ret_code = 0
    if not skipped:
        if print_time:
            print_time_now()

        if creation_options:
            creation_options_list = []
            for k,v in creation_options.items():
                creation_options_list.append('{}={}'.format(k,v))
            common_options['creationOptions'] = creation_options_list

        if verbose:
            logger.info('filename: ' + str(out_filename) + ' ...')
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
                if verbose:
                    logger.info('wrap options: ' + str(warp_options))
                ret_code = gdal.Warp(str(out_filename), ds, **common_options, **warp_options)
            else:
                if verbose:
                    logger.info('translate options: ' + str(translate_options))
                ret_code = gdal.Translate(str(out_filename), ds, **common_options, **translate_options)
        except Exception as e:
            if verbose:
                logger.error(str(e))
        finally:
            del ds
            for key, val in config_options.items():
                gdal.SetConfigOption(key, None)

        if print_time:
            print_time_now()
            logger.warning('Time for creating file: {} is {} seconds'.format(out_filename, round(time.time() - start_time)))

    if ret_code is not None:
        if not skipped and hide_nodatavalue:
            gdal_helper.unset_nodatavalue(str(out_filename))

        if ovr_type == OvrType.existing_reuse:
            # overviews are numbered as follows (i.e. for dst_ovr_count=3, meaning create base+3 ovrs=4 files):
            # -1: base ds, 0: first ovr, 1: second ovr, 2: third ovr

            all_args_new = all_args.copy()
            all_args_new['ovr_type'] = None
            all_args_new['dst_ovr_count'] = None
            all_args_new['out_base_path'] = None
            all_args_new['write_spec'] = False
            all_args_new['cog'] = False
            # iterate backwards on the overviews
            for ovr_index in range(src_ovr_last, src_ovr - 1, -1):
                all_args_new['out_filename'] = concat_paths(out_filename, '.ovr' * (ovr_index - src_ovr))
                all_args_new['src_ovr'] = ovr_index
                all_args_new['create_info'] = create_info and (ovr_index == src_ovr) and not cog
                ret_code = gdalos_trans(**all_args_new)
                # if ret_code is None:
                #     break
            create_info = create_info and cog
        elif (ovr_type is not None) and (ovr_type != OvrType.existing_auto):
            # create overviews from ds (internal or external)
            gdalos_ovr(out_filename, skip_if_exists=skip_if_exists,
                       ovr_type=ovr_type, dst_ovr_count=dst_ovr_count,
                       kind=kind, resampling_alg=resampling_alg,
                       print_progress=print_progress, logger=logger)
        if cog_2_steps:
            gdalos_trans(out_filename, out_filename=cog_filename, cog=True,
                         of=of, outext=outext, tiled=tiled, big_tiff=big_tiff, src_ovr=src_ovr,
                         print_progress=print_progress, print_time=print_time,
                         logger=logger, skip_if_exists=skip_if_exists, create_info=create_info, write_spec=False)
            create_info = False
        if create_info:
            gdalos_info(out_filename, skip_if_exists=skip_if_exists)

    for handler in logger_handlers:
        logging.getLogger().removeHandler(handler)
    return ret_code


def add_ovr(filename, options, access_mode, skip_if_exists=False, logger=None):
    verbose = logger is not None
    filename = Path(filename)
    out_filename = gdal_helper.concat_paths(filename, '.ovr')
    if not do_skip_if_exists(out_filename, skip_if_exists, logger):
        if verbose:
            logger.info('adding ovr: {} options: {} access_mode: {}'.format(out_filename, options, access_mode))
        with gdal_helper.OpenDS(filename, access_mode=access_mode) as ds:
            return ds.BuildOverviews(**options)
    else:
        return 0

default_dst_ovr_count = 10


def gdalos_ovr(filename, comp=None, skip_if_exists=False,
               ovr_type=...,  dst_ovr_count=default_dst_ovr_count,
               kind=None, resampling_alg=None,
               config_options: dict = None, ovr_options: dict = None,
               print_progress=..., logger=None):
    verbose = logger is not None
    filename = Path(filename)
    if os.path.isdir(filename):
        raise Exception(f'input is a dir, not a file: {filename}')

    if not os.path.isfile(filename):
        raise Exception(f'file not found: {filename}')

    if dst_ovr_count is None or dst_ovr_count <= 0:
        dst_ovr_count = default_dst_ovr_count

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
            ret_code = add_ovr(out_filename, ovr_options, access_mode, skip_if_exists, logger)
        elif ovr_type == OvrType.create_external_multi:
            ovr_options['overviewlist'] = [2]
            ret_code = 0
            for i in range(dst_ovr_count):
                ret_code = add_ovr(filename, ovr_options, access_mode, skip_if_exists, logger)
                if ret_code != 0:
                    break
                filename = gdal_helper.concat_paths(filename, '.ovr')
        else:
            raise Exception('invalid ovr type')
    finally:
        for key, val in config_options.items():
            gdal.SetConfigOption(key, None)
    return ret_code


def gdalos_info(filename, skip_if_exists=False):
    filename = Path(filename)
    if os.path.isdir(filename):
        raise Exception(f'input is a dir, not a file: {filename}')
    if not os.path.isfile(filename):
        raise Exception('file not found: {}'.format(filename))
    out_filename = gdal_helper.concat_paths(filename, '.info')
    if not do_skip_if_exists(out_filename, skip_if_exists=skip_if_exists):
        with gdal_helper.OpenDS(filename) as ds:
            gdal_info = gdal.Info(ds)
        with open(out_filename, 'w') as w:
            w.write(gdal_info)
        ret_code = 0
    else:
        ret_code = 0
    return ret_code


def gdalos_vrt(filenames: MaybeSequence, vrt_filename=None, resampling_alg=None):
    if gdal_helper.is_list_like(filenames):
        flatten_filenames = gdal_helper.flatten_and_expand_file_list(filenames)
    else:
        flatten_filenames = [filenames]
    flatten_filenames = [str(f) for f in flatten_filenames]
    if vrt_filename is None:
        vrt_filename = flatten_filenames[0] + '.vrt'

    if os.path.isdir(vrt_filename):
        return None
    if os.path.isfile(vrt_filename):
        os.remove(vrt_filename)
    if os.path.isfile(vrt_filename):
        return None
    os.makedirs(os.path.dirname(vrt_filename), exist_ok=True)
    vrt_options = gdal.BuildVRTOptions(resampleAlg=resampling_alg)
    ret = gdal.BuildVRT(vrt_filename, flatten_filenames, options=vrt_options)
    if ret is None:  # how does BuildVRT indicates an error?
        return None
    if os.path.isfile(vrt_filename):
        return vrt_filename
