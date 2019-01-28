from typing import Optional

import os
from enum import Enum, auto

import gdal

from . import gdal_helper
from . import get_extent
from . import projdef
from .rectangle import GeoRectangle

import time
import datetime


class Kind(Enum):
    photo = auto()
    pal = auto()
    dtm = auto()

    @staticmethod
    def guess(bands):
        if isinstance(bands, str):
            bands = gdal_helper.get_band_types(bands)
        if len(bands) == 0:
            raise Exception('no bands in raster')
        if bands[0] == 'Byte':
            if len(bands) in (3, 4):
                return Kind.photo
            elif len(bands) == 1:
                return Kind.pal
            else:
                raise Exception("invalid raster band count")
        elif len(bands) == 1:
            return Kind.dtm
        raise Exception('could not guess raster kind')


def resample_method_by_kind(kind, expand_rgb=False):
    if kind == Kind.pal:
        if expand_rgb:
            return 'average'
        else:
            return 'near'
    elif kind == Kind.dtm:
        return 'average'
    else:
        return 'cubic'


def do_skip_if_exists(out_filename, skip_if_exist, verbose=True):
    skip = False
    if os.path.isfile(out_filename):
        if skip_if_exist:
            skip = True
            if verbose:
                print('file {} exits, skip!\n'.format(out_filename))
        else:
            if verbose:
                print('file {} exits, removing...!\n'.format(out_filename))
            os.remove(out_filename)
            if verbose:
                print('file {} removed!\n'.format(out_filename))
    return skip


def add_print_progress_callback(print_progress, options):
    if print_progress:
        if print_progress is ...:
            def print_progress(*data):
                # print('progress: ', data)
                print(str(round(data[0]*100))+'%', end =" ")
        options['callback'] = print_progress
    return options


def print_time():
    print('Current time: {}'.format(datetime.datetime.now()))


default_filename = 'map.vrt'


def gdalos_trans(filename, of='GTiff', outext='tif', tiled='YES', big_tiff='IF_SAFER',
                warp_CRS=None, out_filename=None, out_base_path=None, kind: Kind = ..., lossy=False, expand_rgb=False,
                skip_if_exist=False, out_res=None, create_info=True, dst_NDV=...,
                hide_NDV=False, extent: Optional[GeoRectangle] = None, src_win=None, ovr_type=..., resample_method=...,
                alpha=1, config: dict = None, print_progress=..., verbose=True):
    if verbose:
        print_time()
    timer = time.time()
    if os.path.isdir(filename):
        filename = os.path.join(filename, default_filename)

    if ovr_type == OvrType.copy_single_external:
        filename = os.path.join(filename, '.ovr')

    if not os.path.isfile(filename):
        raise OSError(f'file not found: {filename}')

    creation_options = {'creationOptions': []}
    creation_options = add_print_progress_callback(print_progress, creation_options)

    translate_options = {}
    warp_options = {}

    do_warp = False

    bands = gdal_helper.get_band_types(filename)
    if kind is ...:
        kind = Kind.guess(bands)

    if (dst_NDV is ...) and (kind == Kind.dtm):
        dst_NDV = -32768
        src_nodatavalue = gdal_helper.get_nodatavalue(filename)
        if src_nodatavalue is None:
            # assume raster minimum is nodata if nodata isn't set
            src_nodatavalue = gdal_helper.get_raster_minimum(filename)
            translate_options['noData'] = src_nodatavalue

        if src_nodatavalue != dst_NDV:
            do_warp = True
            warp_options['srcNodata'] = src_nodatavalue
            warp_options['dstNodata'] = dst_NDV

    out_suffix = ''

    if kind == Kind.pal and expand_rgb:
        translate_options['rgbExpand'] = 'rgb'
        out_suffix += '.rgb'

    if resample_method is ...:
        resample_method = resample_method_by_kind(kind, expand_rgb)

    pjstr_tgt_srs = None
    if warp_CRS is not None:
        do_warp = True
        lossy = True

        if isinstance(warp_CRS, (int, float)):
            warp_CRS = f'w84u{warp_CRS}'
        elif warp_CRS.startswith('+'):
            pjstr_tgt_srs = warp_CRS  # ProjString
        else:  # "short ProjString"
            zone = projdef.get_zone_from_name(warp_CRS)
            pjstr_tgt_srs = projdef.get_proj4_string(warp_CRS[0], zone)
            if zone != 0:
                # cropping according to zone bounds
                zone_extent = GeoRectangle.from_points(projdef.get_utm_zone_extent_points(zone))
                if extent is None:
                    extent = zone_extent
                else:
                    extent = zone_extent.crop(extent)
            out_suffix += '.' + projdef.get_canonic_name(warp_CRS[0], zone)

        if kind == Kind.dtm:
            creation_options['outputType'] = 'Float32'

        warp_options["dstSRS"] = pjstr_tgt_srs
        creation_options['resampleAlg'] = resample_method

    if extent is not None:
        org_points_extent, pjstr_src_srs, geo_transform = get_extent.get_points_extent_from_file(filename)
        org_extent_in_src_srs = GeoRectangle.from_points(org_points_extent)

        if pjstr_tgt_srs is None:
            pjstr_tgt_srs = pjstr_src_srs
            transform = None
        else:
            transform = get_extent.get_transform(pjstr_src_srs, pjstr_tgt_srs)

        org_extent_in_tgt_srs = get_extent.translate_extent(org_extent_in_src_srs, transform)

        pjstr_4326 = projdef.get_proj4_string('w')  # 'EPSG:4326'
        transform = get_extent.get_transform(pjstr_4326, pjstr_tgt_srs)
        out_extent_in_tgt_srs = get_extent.translate_extent(extent, transform)
        out_extent_in_tgt_srs = out_extent_in_tgt_srs.crop(org_extent_in_tgt_srs) if out_extent_in_tgt_srs else org_extent_in_tgt_srs

        if out_extent_in_tgt_srs is None:
            raise Exception('no output extent: {}'.format(filename))

        if not do_warp:
            # -projwin minx maxy maxx miny (ulx uly lrx lry)
            translate_options['projWin'] = out_extent_in_tgt_srs.lurd
        else:
            # -te minx miny maxx maxy
            warp_options['outputBounds'] = out_extent_in_tgt_srs.ldru

        if out_res is None:
            transform_src_tgt = get_extent.get_transform(pjstr_src_srs, pjstr_tgt_srs)
            if (pjstr_src_srs != pjstr_tgt_srs) and transform_src_tgt is not None:
                transform = get_extent.get_transform(pjstr_4326, pjstr_src_srs)
                if transform is not None:
                    out_extent_in_src_srs = get_extent.translate_extent(extent, transform)
                    out_extent_in_src_srs = out_extent_in_src_srs.crop(org_extent_in_src_srs)

                    in_res_y = geo_transform[5]  # Mpp.Y == geotransform[5]

                    out_res = get_extent.transform_resolution(transform_src_tgt, in_res_y, *out_extent_in_src_srs.lrdu)
                    out_res = get_extent.round_to_sig(out_res, -1)

    elif src_win is not None:
        translate_options['srcWin'] = src_win

    if out_res is not None:
        creation_options['xRes'], creation_options['yRes'] = (out_res, -out_res)
        warp_options['targetAlignedPixels'] = True
        out_suffix = out_suffix + '.' + str(out_res)

    org_comp = gdal_helper.get_image_structure_metadata(filename, 'COMPRESSION')
    if (org_comp is not None) and 'JPEG' in org_comp:
        lossy = True

    if lossy and (kind != 'dtm'):
        comp = 'JPEG'
        out_suffix = out_suffix + '.jpg'
    else:
        comp = 'DEFLATE'
    if ovr_type == OvrType.copy_internal or ovr_type == OvrType.copy_single_external:
        creation_options['creationOptions'].append('COPY_SRC_OVERVIEWS=YES')

    if out_filename is None:
        if extent is None:
            if src_win is None:
                out_suffix = out_suffix + '.new'
            else:
                out_suffix = out_suffix + '.off[{},{}]_size[{},{}]'.format(*src_win)
        else:
            out_suffix = out_suffix + '.x[{},{}]_y[{},{}]'.format(*extent.lrdu)
        out_filename = filename + out_suffix + '.' + outext

    if out_base_path is not None:
        out_filename = os.path.join(out_base_path, os.path.splitdrive(out_filename)[1])

    if not os.path.exists(os.path.dirname(out_filename)):
        os.makedirs(os.path.dirname(out_filename), exist_ok=True)

    # if (comp == 'JPEG') and (len(bands) == 3) or ((len(bands) == 4) and (alpha == 0)):
    if (not do_warp) and (comp == 'JPEG') and (len(bands) in (3, 4)):
        creation_options['creationOptions'].append('PHOTOMETRIC=YCBCR')
        if len(bands) == 4:  # alpha channel is not supported with PHOTOMETRIC=YCBCR, thus we drop it
            translate_options['bandList'] = [1, 2, 3]
            if alpha > 0:
                translate_options['maskBand'] = 4

    creation_options['creationOptions'].extend((
        f'TILED={tiled}',
        f'BIGTIFF={big_tiff}',
        f'COMPRESS={comp}'
    ))

    creation_options['format'] = of

    if config:
        for k, v in config.items():
            gdal.SetConfigOption(k, v)

    if verbose:
        print('filename: '+out_filename + ' ...')
        print('creation options: ' + str(creation_options))

    ret_code = 0
    if do_skip_if_exists(out_filename, skip_if_exist, verbose):
        pass
    elif do_warp:
        cutoff = 'z'
        #options.clear()
        for k in list(creation_options):
            if k > cutoff:
                creation_options.pop(k)
        if verbose:
            print('wrap options: '+str(warp_options))
        ret_code = gdal.Warp(out_filename, filename, **creation_options, **warp_options)
    else:
        if verbose:
            print('translate options: ' + str(translate_options))
        ret_code = gdal.Translate(out_filename, filename, **creation_options, **translate_options)
    if verbose:
        print('.\n')

    if verbose:
        print_time()
        print('Time for creating file: {} is {} seconds'.format(filename, round(time.time() - timer)))

    if ret_code is not None:
        if hide_NDV:
            gdal_helper.unset_nodatavalue(out_filename)

        if (ovr_type is not None) and (ovr_type != OvrType.copy_internal) and (ovr_type != OvrType.copy_single_external):
            if ovr_type != OvrType.existing:
                gdalos_ovr(out_filename, skip_if_exist=skip_if_exist, ovr_type=ovr_type, print_progress=print_progress, verbose=verbose)
            else:
                ovr_levels_count = 20
                in_ovr_filename = filename
                out_ovr_filename = out_filename
                for i in range(ovr_levels_count):
                    in_ovr_filename = in_ovr_filename + '.ovr'
                    out_ovr_filename = out_ovr_filename + '.ovr'
                    if not os.path.isfile(in_ovr_filename):
                        break
                    ret_code = gdalos_trans(filename=in_ovr_filename, of=of, tiled=tiled, big_tiff=big_tiff,
                                           warp_CRS=warp_CRS,
                                           out_filename=out_ovr_filename, kind=kind, lossy=lossy,
                                           skip_if_exist=skip_if_exist, out_res=out_res, create_info=False,
                                           dst_NDV=dst_NDV, hide_NDV=hide_NDV, extent=extent,
                                           src_win=src_win, ovr_type=None, resample_method=resample_method, alpha=alpha,
                                           print_progress=print_progress, verbose=verbose)
                    if ret_code > 0:
                        break
        if create_info:
            gdalos_info(out_filename)

    return ret_code


def add_ovr(filename, options, open_options, skip_if_exist, verbose=True):
    out_filename = filename + '.ovr'
    if verbose:
        print('.\n')
        print('adding ovr: {} options: {} open_options: {}'.format(out_filename, options, open_options))

    if not do_skip_if_exists(out_filename, skip_if_exist, verbose):
        with gdal_helper.OpenDS(filename, open_options) as ds:
            return ds.BuildOverviews(**options)
    else:
        return 0


class OvrType(Enum):
    internal = auto()  # create overviews inside the main dataset file
    single_external = auto()  # create a single .ovr file with all the overviews
    multi_external = auto()  # create one ovr file per overview: .ovr, .ovr.ovr, .ovr.ovr.orv ....
    existing = auto()  # work with existing overviews
    copy_internal = auto()  # COPY_SRC_OVERVIEWS
    copy_single_external = auto()  # COPY_SRC_OVERVIEWS for .ovr file


def gdalos_ovr(filename, comp=None, kind=None, skip_if_exist=False, ovr_type=..., resampling_method=None, print_progress=...,
              ovr_levels_count=10, verbose=True):
    if os.path.isdir(filename):
        filename = os.path.join(filename, default_filename)

    ovr_options = {}

    if not os.path.isfile(filename):
        raise Exception(f'file not found: {filename}')
    if kind is None:
        kind = Kind.guess(filename)
    if kind is None:
        raise Exception('could not guess kind')

    if resampling_method is None:
        resampling_method = resample_method_by_kind(kind)

    if comp is None:
        comp = gdal_helper.get_image_structure_metadata(filename, 'COMPRESSION')

    ovr_options['resampling'] = resampling_method
    ovr_options = add_print_progress_callback(print_progress, ovr_options)

    if comp == 'YCbCr JPEG':
        gdal.SetConfigOption('COMPRESS_OVERVIEW', 'JPEG')
        gdal.SetConfigOption('PHOTOMETRIC_OVERVIEW', 'YCBCR')
        gdal.SetConfigOption('INTERLEAVE_OVERVIEW', 'PIXEL')
    else:
        gdal.SetConfigOption('COMPRESS_OVERVIEW', comp)

    if ovr_type is ...:
        file_size = os.path.getsize(filename)
        max_ovr_gb = 1
        if file_size > max_ovr_gb * 1024 ** 3:
            ovr_type = OvrType.multi_external
        else:
            ovr_type = OvrType.single_external

    out_filename = filename

    open_options = gdal.GA_ReadOnly
    if ovr_type in (OvrType.internal, OvrType.single_external):
        if ovr_type == OvrType.internal:
            open_options = gdal.GA_Update
        ovr_levels = []
        for i in range(ovr_levels_count):
            ovr_levels.append(2 ** (i + 1))  # ovr_levels = '2 4 8 16 32 64 128 256 512 1024'
        ovr_options['overviewlist'] = ovr_levels
        ret_code = add_ovr(out_filename, ovr_options, open_options, skip_if_exist, verbose)
    elif ovr_type == OvrType.multi_external:
        ovr_options['overviewlist'] = [2]
        ret_code = 0
        for i in range(ovr_levels_count):
            ret_code = add_ovr(filename, ovr_options, open_options, skip_if_exist, verbose)
            if ret_code != 0:
                break
            filename = filename + '.ovr'
    else:
        raise Exception('invalid ovr type')
    return ret_code


def gdalos_info(filename):
    if os.path.isdir(filename):
        filename = os.path.join(filename, default_filename)
    if not os.path.isfile(filename):
        raise Exception('file not found: {}'.format(filename))
    out_filename = filename + '.info'
    if not do_skip_if_exists(out_filename, False):
        with gdal_helper.OpenDS(filename) as ds:
            info = gdal.Info(ds)
        with open(out_filename, 'w') as w:
            w.write(info)
        ret_code = 0
    else:
        ret_code = 0
    return ret_code
