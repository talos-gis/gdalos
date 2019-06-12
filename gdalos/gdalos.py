from typing import Optional, Sequence, List, Union, Tuple

import os
import time
import datetime
from numbers import Real
from logging import debug, info, warning
from enum import Enum, auto
from pathlib import Path

import gdal

from gdalos import gdal_helper
from gdalos import get_extent
from gdalos import projdef
from gdalos.rectangle import GeoRectangle


def is_path_like(s):
    return isinstance(s, (str, Path))


def is_list_like(lst):
    return isinstance(lst, Sequence) and not isinstance(lst, str)


def concat_paths(*argv):
    return Path(''.join([str(p) for p in argv]))


def print_time_now():
    info('Current time: {}'.format(datetime.datetime.now()))


class OvrType(Enum):
    auto_select = auto() # existing_reuse or create_external_auto (by existance of src overviews)
    create_external_auto = auto()  # create_external_single or create_external_multi (by size)
    create_external_single = auto()  # create a single .ovr file with all the overviews
    create_external_multi = auto()  # create one ovr file per overview: .ovr, .ovr.ovr, .ovr.ovr.orv ....
    create_internal = auto()  # create overviews inside the main dataset file
    existing_reuse = auto()  # work with existing overviews
    existing_copy = auto()  # COPY_SRC_OVERVIEWS


class RasterKind(Enum):
    photo = auto()
    pal = auto()
    dtm = auto()

    @classmethod
    def guess(cls, bands):
        if is_path_like(bands):
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


def do_skip_if_exists(out_filename, skip_if_exists, verbose=True):
    skip = False
    if os.path.isfile(out_filename):
        if skip_if_exists:
            skip = True
            if verbose:
                warning('file {} exits, skip!\n'.format(out_filename))
        else:
            if verbose:
                warning('file {} exits, removing...!\n'.format(out_filename))
            os.remove(out_filename)
            if verbose:
                warning('file {} removed!\n'.format(out_filename))
    return skip


def print_progress_from_to(r0, r1):
    # print(str(round(r1)) + '%', end=" ")
    i0 = 0 if (r0 is None) or (r0 > r1) else round(r0) + 1
    i1 = round(r1) + 1
    for i in range(i0, i1):
        print(str(i) if i % 5 == 0 else '.', end="")
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


Class_or_classlist = Union[str, Sequence[str]]
Warp_crs_base = Union[str, int, Real]
Warp_crs = Union[Warp_crs_base, Sequence[Warp_crs_base]]
Real_tuple = Tuple[Real, Real]
default_multi_byte_nodata_value = -32768


def gdalos_trans(filename: Class_or_classlist, out_filename: str = None, out_base_path: str = None,
                 skip_if_exists=True, create_info=True,
                 of: Class_or_classlist = 'GTiff', outext: str = 'tif', tiled=True, big_tiff: str = 'IF_SAFER',
                 creation_options=None, config_options: dict = ...,
                 extent: Union[Optional[GeoRectangle], List[GeoRectangle]] = None, src_win=None,
                 warp_CRS: Warp_crs = None, out_res: Real_tuple = None,
                 ovr_type: Optional[OvrType] = OvrType.auto_select,
                 src_ovr: int = None, keep_src_ovr_suffixes=False, dst_overview_count=None,
                 src_nodatavalue: Real = ..., dst_nodatavalue: Real = ..., hide_nodatavalue: bool = False,
                 kind: RasterKind = None, resampling_alg=None, lossy: bool = None, expand_rgb=False,
                 jpeg_quality=75, keep_alpha=True,
                 print_progress=..., verbose=True, print_time=False):
    all_args = dict(locals())
    if verbose:
        info(all_args)

    key_list_arguments = ['filename', 'extent', 'warp_CRS', 'of', 'expand_rgb']
    for key in key_list_arguments:
        val = all_args[key]
        if is_path_like(val):
            if Path(val.strip()).suffix.lower() == '.txt':
                # input argument is a txt file, replace it with a list of its lines
                with open(val) as f:
                    val = f.read().splitlines()
                    all_args[key] = val
        if is_list_like(val):
            # input argument is a list, recurse over its values
            all_args_new = all_args.copy()
            ret_code = None
            for v in val:
                all_args_new[key] = v
                ret_code = gdalos_trans(**all_args_new)
                if ret_code is None:
                    break  # failed?
            return ret_code

    if not filename:
        return None
    filename = Path(filename.strip())

    if os.path.isdir(filename):
        raise Exception(f'input is a dir, not a file: {filename}')

    if isinstance(ovr_type, str):
        ovr_type = OvrType[ovr_type]
    if isinstance(kind, str):
        kind = RasterKind[kind]

    if not os.path.isfile(filename):
        raise OSError(f'file not found: {filename}')

    if print_time:
        start_time = time.time()
    else:
        start_time = None
    extent_was_cropped = False

    common_options = {'creationOptions': list(creation_options or [])}
    if print_progress:
        common_options['callback'] = print_progress_callback(print_progress)

    translate_options = {}
    warp_options = {}

    # todo needs a parameter to pass Open options
    ds = gdal.Open(str(filename))
    geo_transform = ds.GetGeoTransform()
    bnd_res = (geo_transform[1], geo_transform[5])
    bnd = gdal_helper.get_raster_band(ds)
    bnd_size = (bnd.XSize, bnd.YSize)

    if src_ovr is None:
        src_ovr = -1  # base ds
    overview_count = gdal_helper.get_ovr_count(ds)
    src_ovr_last = overview_count - 1
    if dst_overview_count is not None:
        if dst_overview_count >= 0:
            src_ovr_last = min(overview_count - 1, src_ovr + dst_overview_count)
        else:
            # in this case we need to discard the selected src_ovr, becuase we want only the last ovrs
            src_ovr = max(-1, overview_count + dst_overview_count)

    do_warp = (src_ovr >= 0) or (warp_CRS is not None)

    if src_ovr >= 0:
        # we should process only the given src_ovr, thus discarding ovr_type
        ovr = bnd.GetOverview(src_ovr)
        ovr_res = (
            bnd_res[0] * bnd_size[0] / ovr.XSize,
            bnd_res[1] * bnd_size[1] / ovr.YSize
        )
        warp_options['overviewLevel'] = src_ovr
    else:
        ovr_res = bnd_res
    out_res_xy = out_res

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

        if out_res_xy is None:
            transform_src_tgt = get_extent.get_transform(pjstr_src_srs, pjstr_tgt_srs)
            if transform_src_tgt is not None:
                in_res_y = ovr_res[1]  # geo_transform[5]  # Mpp.Y == geotransform[5]
                out_res_x = get_extent.transform_resolution(transform_src_tgt, in_res_y, *out_extent_in_src_srs.lrdu)
                out_res_x = get_extent.round_to_sig(out_res_x, -1)
                out_res_xy = (out_res_x, -out_res_x)
    elif src_win is not None:
        translate_options['srcWin'] = src_win

    if out_res_xy is None and src_ovr >= 0:
        out_res_xy = ovr_res

    if out_res_xy is not None:
        common_options['xRes'], common_options['yRes'] = out_res_xy
        warp_options['targetAlignedPixels'] = True
        out_suffixes.append(str(out_res_xy))

    org_comp = gdal_helper.get_image_structure_metadata(ds, 'COMPRESSION')
    if lossy is None:
        lossy = (org_comp is not None) and ('JPEG' in org_comp)
    if lossy and (kind != RasterKind.dtm):
        comp = 'JPEG'
        out_suffixes.append('jpg')
    else:
        comp = 'DEFLATE'

    if out_filename is None:
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
            if '.' + outext == os.path.splitext(filename)[1]:  # input and output have the same extension
                out_suffixes.append('new')
        if out_suffixes:
            out_suffixes = '.' + '.'.join(out_suffixes)
        else:
            out_suffixes = ''
        out_filename = filename.with_suffix(out_suffixes + '.' + outext)
        if keep_src_ovr_suffixes:
            out_filename = concat_paths(out_filename, '.ovr' * (src_ovr + 1))
    else:
        out_filename = Path(out_filename)

    if out_base_path is not None:
        out_filename = Path(out_base_path).joinpath(*out_filename.parts[1:])

    if not os.path.exists(os.path.dirname(out_filename)):
        os.makedirs(os.path.dirname(out_filename), exist_ok=True)

    # if (comp == 'JPEG') and (len(bands) == 3) or ((len(bands) == 4) and (keep_alpha)):
    if (comp == 'JPEG') and (len(band_types) in (3, 4)):
        common_options['creationOptions'].append('PHOTOMETRIC=YCBCR')
        common_options['creationOptions'].append('JPEG_QUALITY=' + str(jpeg_quality))

        if len(band_types) == 4:  # alpha channel is not supported with PHOTOMETRIC=YCBCR, thus we drop it
            translate_options['bandList'] = [1, 2, 3]
            if keep_alpha:
                translate_options['maskBand'] = 4  # keep the alpha band as mask

    no_yes = ('NO', 'YES')
    if not isinstance(tiled, str):
        tiled = no_yes[tiled]
    common_options['creationOptions'].extend((
        f'TILED={tiled}',
        f'BIGTIFF={big_tiff}',
        f'COMPRESS={comp}'
    ))
    common_options['format'] = of

    if ovr_type is not None:
        if ovr_type == OvrType.existing_copy:
            common_options['creationOptions'].append('COPY_SRC_OVERVIEWS=YES')
        elif ovr_type in [..., OvrType.auto_select]:
            if overview_count > 0:
                # if ds has overviews then use them, otherwise create overviews
                ovr_type = OvrType.existing_reuse
            else:
                ovr_type = OvrType.create_external_auto

    if ovr_type == OvrType.existing_reuse:
        skipped = True
    else:
        skipped = do_skip_if_exists(out_filename, skip_if_exists, verbose)

    ret_code = 0
    if not skipped:
        if print_time:
            print_time_now()

        if verbose:
            info('filename: ' + str(out_filename) + ' ...')
            info('common options: ' + str(common_options))

        if config_options is None:
            config_options = dict()
        elif config_options is ...:
            config_options = {'GDAL_HTTP_UNSAFESSL': 'YES'}  # for gdal-wms xml files
        try:
            if config_options:
                if verbose:
                    info('config options: ' + str(config_options))
                for k, v in config_options.items():
                    gdal.SetConfigOption(k, v)

            if do_warp:
                if verbose:
                    info('wrap options: ' + str(warp_options))
                ret_code = gdal.Warp(str(out_filename), str(filename), **common_options, **warp_options)
            else:
                if verbose:
                    info('translate options: ' + str(translate_options))
                ret_code = gdal.Translate(str(out_filename), str(filename), **common_options, **translate_options)
        finally:
            for key, val in config_options.items():
                gdal.SetConfigOption(key, None)

        if print_time:
            print_time_now()
            warning('Time for creating file: {} is {} seconds'.format(out_filename, round(time.time() - start_time)))

    if ret_code is not None:
        if not skipped and hide_nodatavalue:
            gdal_helper.unset_nodatavalue(str(out_filename))

        if ovr_type == OvrType.existing_reuse:
            # overviews are numbered as follows (i.e. for dst_overview_count=3, meaning create base+3 ovrs=4 files):
            # -1: base ds, 0: first ovr, 1: second ovr, 2: third ovr

            all_args_new = all_args.copy()
            all_args_new['ovr_type'] = None
            all_args_new['dst_overview_count'] = None
            all_args_new['out_base_path'] = None
            # iterate backwards on the overviews
            for ovr_index in range(src_ovr_last, src_ovr - 1, -1):
                all_args_new['out_filename'] = concat_paths(out_filename, '.ovr' * (ovr_index - src_ovr ))
                all_args_new['src_ovr'] = ovr_index
                all_args_new['create_info'] = create_info and (ovr_index == src_ovr)
                ret_code = gdalos_trans(**all_args_new)
                if ret_code is None:
                    break
            create_info = False
        elif (ovr_type is not None) and (ovr_type != OvrType.existing_copy):
            # create overviews from ds (internal or external)
            gdalos_ovr(out_filename, skip_if_exists=skip_if_exists,
                       ovr_type=ovr_type, dst_overview_count=dst_overview_count,
                       kind=kind, resampling_alg=resampling_alg,
                       print_progress=print_progress, verbose=verbose)

        if create_info:
            gdalos_info(out_filename, skip_if_exists=skip_if_exists)

    del ds
    return ret_code


def add_ovr(filename, options, open_options, skip_if_exists=False, verbose=True):
    filename = Path(filename)
    out_filename = concat_paths(filename, '.ovr')
    if not do_skip_if_exists(out_filename, skip_if_exists, verbose):
        if verbose:
            info('adding ovr: {} options: {} open_options: {}'.format(out_filename, options, open_options))
        with gdal_helper.OpenDS(filename, open_options) as ds:
            return ds.BuildOverviews(**options)
    else:
        return 0

default_dst_overview_count = 10
def gdalos_ovr(filename, comp=None, skip_if_exists=False,
               ovr_type=...,  dst_overview_count=default_dst_overview_count,
               kind=None, resampling_alg=None,
               config_options: dict = None, ovr_options: dict = None,
               print_progress=..., verbose=True):
    filename = Path(filename)
    if os.path.isdir(filename):
        raise Exception(f'input is a dir, not a file: {filename}')

    if not os.path.isfile(filename):
        raise Exception(f'file not found: {filename}')

    if dst_overview_count is None or dst_overview_count <= 0:
        dst_overview_count = default_dst_overview_count

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
    if resampling_alg in [None, ...]:
        if kind in [None, ...]:
            kind = RasterKind.guess(filename)
        resampling_alg = resampling_alg_by_kind(kind)
    if resampling_alg is not None:
        ovr_options['resampling'] = resampling_alg
    if print_progress:
        ovr_options['callback'] = print_progress_callback(print_progress)

    if config_options is None:
        config_options = dict()
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
                info('config options: ' + str(config_options))
            for k, v in config_options.items():
                gdal.SetConfigOption(k, v)

        out_filename = filename
        open_options = gdal.GA_ReadOnly
        if ovr_type in (OvrType.create_internal, OvrType.create_external_single):
            if ovr_type == OvrType.create_internal:
                open_options = gdal.GA_Update
            ovr_levels = []
            for i in range(dst_overview_count):
                ovr_levels.append(2 ** (i + 1))  # ovr_levels = '2 4 8 16 32 64 128 256 512 1024'
            ovr_options['overviewlist'] = ovr_levels
            ret_code = add_ovr(out_filename, ovr_options, open_options, skip_if_exists, verbose)
        elif ovr_type == OvrType.create_external_multi:
            ovr_options['overviewlist'] = [2]
            ret_code = 0
            for i in range(dst_overview_count):
                ret_code = add_ovr(filename, ovr_options, open_options, skip_if_exists, verbose)
                if ret_code != 0:
                    break
                filename = concat_paths(filename, '.ovr')
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
    out_filename = concat_paths(filename, '.info')
    if not do_skip_if_exists(out_filename, skip_if_exists=skip_if_exists):
        with gdal_helper.OpenDS(filename) as ds:
            info = gdal.Info(ds)
        with open(out_filename, 'w') as w:
            w.write(info)
        ret_code = 0
    else:
        ret_code = 0
    return ret_code
