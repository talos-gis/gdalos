from typing import Optional

import os
from enum import Enum, auto
import time
import datetime

import gdal

from gdalos import gdal_helper
from gdalos import get_extent
from gdalos import projdef
from gdalos.rectangle import GeoRectangle


class OvrType(Enum):
    create_internal = auto()  # create overviews inside the main dataset file
    create_single_external = auto()  # create a single .ovr file with all the overviews
    create_multi_external = auto()  # create one ovr file per overview: .ovr, .ovr.ovr, .ovr.ovr.orv ....
    translate_existing = auto()  # work with existing overviews
    copy_internal = auto()  # COPY_SRC_OVERVIEWS
    copy_single_external = auto()  # COPY_SRC_OVERVIEWS for .ovr file


class RasterKind(Enum):
    photo = auto()
    pal = auto()
    dtm = auto()

    @classmethod
    def guess(cls, bands):
        if isinstance(bands, str):
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


def resample_method_by_kind(kind, expand_rgb=False):
    if kind == RasterKind.pal:
        if expand_rgb:
            return 'average'
        else:
            return 'near'
    elif kind == RasterKind.dtm:
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


def print_time():
    print('Current time: {}'.format(datetime.datetime.now()))


default_filename = 'map.vrt'


# todo this function is made of warnings
# todo document this (I'm pretty sure src_ovr is int, but who knows)
def gdalos_trans(filename, out_filename=None, out_base_path=None, skip_if_exists=True, create_info=True,
                 of='GTiff', outext='tif', tiled='YES', big_tiff='IF_SAFER',
                 extent: Optional[GeoRectangle] = None, src_win=None,
                 warp_CRS=None, out_res=None,
                 ovr_type: Optional[OvrType] = ..., src_ovr=None, resample_method=...,
                 src_nodatavalue=..., dst_nodatavalue=-32768, hide_nodatavalue=False,
                 kind: RasterKind = ..., lossy=False, expand_rgb=False,
                 jpeg_quality=75, keep_alpha=True,
                 config: dict = None, print_progress=..., verbose=True):
    if verbose:
        print_time()
        start_time = time.time()
        # r- this is just an additional functionality that clutters both the code and the output
        #  (and is enabled by default) recommend: either remove or opt-in
    else:
        start_time = None
    extent_was_cropped = False

    if isinstance(ovr_type, str):
        ovr_type = OvrType[ovr_type]
    if isinstance(kind, str):
        kind = RasterKind[kind]

    if os.path.isdir(filename):
        # r- there's a lot wrong with this. It's very circumstantial, and may cause a lot more problems than it solves
        filename = os.path.join(filename, default_filename)

    if ovr_type == OvrType.copy_single_external:
        # r- So if you set ovr_type to copy_single_external it just flat out ignores the original file?
        filename = os.path.join(filename, '.ovr')

    if not os.path.isfile(filename):
        raise OSError(f'file not found: {filename}')

    # r- it might be a good idea to add a parameter for initial creation options
    common_options = {'creationOptions': []}
    if print_progress:
        common_options['callback'] = print_progress_callback(print_progress)

    translate_options = {}
    warp_options = {}

    do_warp = (src_ovr is not None) or (warp_CRS is not None)

    # todo needs a parameter to pass Open options
    ds = gdal.Open(filename)
    geo_transform = ds.GetGeoTransform()
    bnd_res = (geo_transform[1], geo_transform[5])

    bnd = gdal_helper.get_raster_band(ds)
    bnd_size = (bnd.XSize, bnd.YSize)
    # r- this if-else is a perfect example of this function's problems:
    #  * inexplicable and undocumented
    #  * it sets the output to None, ignoring parameters is never a good idea
    if src_ovr is not None:
        ovr = bnd.GetOverview(src_ovr)
        ovr_res = (
            bnd_res[0] * bnd_size[0] / ovr.XSize,
            bnd_res[1] * bnd_size[1] / ovr.YSize
        )
        ovr_type = None
        warp_options['overviewLevel'] = src_ovr
    else:
        ovr_res = bnd_res

    out_res_xy = out_res

    band_types = gdal_helper.get_band_types(ds)
    if kind is ...:
        kind = RasterKind.guess(band_types)
    # r- so what's the point of dst_nodatavalue if we're not dealing with DTM?
    #  note that kind can be guessed, meaning that dst_nodatavalue might be ignored on a heuristic
    if (dst_nodatavalue is not None) and (kind == RasterKind.dtm):
        src_nodatavalue_org = gdal_helper.get_nodatavalue(ds)
        if src_nodatavalue is ...:
            src_nodatavalue = src_nodatavalue_org
        if src_nodatavalue is None:
            # assume raster minimum is nodata if nodata isn't set
            # r- why? can't we have a raster in which all the values are applicable?
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

    if resample_method is ...:
        resample_method = resample_method_by_kind(kind, expand_rgb)
    # r- can't it just be None?
    common_options['resampleAlg'] = resample_method

    pjstr_tgt_srs = None
    if warp_CRS is not None:
        lossy = True

        if isinstance(warp_CRS, str) and warp_CRS.startswith('+'):
            pjstr_tgt_srs = warp_CRS  # ProjString
        else:
            if isinstance(warp_CRS, (int, float)):
                warp_CRS = f'w84u{warp_CRS}'
            # "short ProjString"
            zone = projdef.get_zone_from_name(warp_CRS)
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
        org_points_extent, pjstr_src_srs, _ = get_extent.get_points_extent_from_file(filename)
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

    if out_res_xy is None and src_ovr is not None:
        out_res_xy = ovr_res

    if out_res_xy is not None:
        common_options['xRes'], common_options['yRes'] = out_res_xy
        warp_options['targetAlignedPixels'] = True
        out_suffixes.append(str(out_res_xy))

    org_comp = gdal_helper.get_image_structure_metadata(ds, 'COMPRESSION')
    if (org_comp is not None) and 'JPEG' in org_comp:
        lossy = True

    if lossy and (kind != RasterKind.dtm):
        comp = 'JPEG'
        out_suffixes.append('jpg')
    else:
        comp = 'DEFLATE'
    if ovr_type == OvrType.copy_internal or ovr_type == OvrType.copy_single_external:
        common_options['creationOptions'].append('COPY_SRC_OVERVIEWS=YES')

    if out_filename is None:
        out_extent_in_4326 = extent
        if extent_was_cropped and (out_extent_in_src_srs is not None):
            transform = get_extent.get_transform(pjstr_src_srs, pjstr_4326)
            if transform is not None:
                out_extent_in_4326 = get_extent.translate_extent(out_extent_in_src_srs, transform)
            out_extent_in_4326 = round(out_extent_in_4326, 2)
        if out_extent_in_4326 is not None:
            out_suffixes.append('x[{},{}]_y[{},{}]'.format(*out_extent_in_4326.lrdu))
        elif src_win is not None:
            out_suffixes.append('off[{},{}]_size[{},{}]'.format(*src_win))
        if not out_suffixes:
            out_suffixes.append('new')
        out_filename = filename + '.'.join(out_suffixes) + '.' + outext
    else:
        out_filename = str(out_filename)

    if out_base_path is not None:
        out_filename = os.path.join(out_base_path, os.path.splitdrive(out_filename)[1])

    if not os.path.exists(os.path.dirname(out_filename)):
        os.makedirs(os.path.dirname(out_filename), exist_ok=True)

    # if (comp == 'JPEG') and (len(bands) == 3) or ((len(bands) == 4) and (keep_alpha)):
    if (not do_warp) and (comp == 'JPEG') and (len(band_types) in (3, 4)):
        common_options['creationOptions'].append('PHOTOMETRIC=YCBCR')
        common_options['creationOptions'].append('JPEG_QUALITY=' + str(jpeg_quality))

        if len(band_types) == 4:  # alpha channel is not supported with PHOTOMETRIC=YCBCR, thus we drop it
            translate_options['bandList'] = [1, 2, 3]
            if keep_alpha:
                translate_options['maskBand'] = 4  # keep the alpha band as mask

    common_options['creationOptions'].extend((
        f'TILED={tiled}',
        f'BIGTIFF={big_tiff}',
        f'COMPRESS={comp}'
    ))

    common_options['format'] = of

    if config is None:
        config = dict()
    config['GDAL_HTTP_UNSAFESSL'] = 'YES'

    if config:
        for k, v in config.items():
            gdal.SetConfigOption(k, v)

    if verbose:
        print('filename: ' + out_filename + ' ...')
        print('common options: ' + str(common_options))

    ret_code = 0
    skipped = do_skip_if_exists(out_filename, skip_if_exists, verbose)
    if skipped:
        pass
    elif do_warp:
        if verbose:
            print('wrap options: ' + str(warp_options))
        ret_code = gdal.Warp(out_filename, filename, **common_options, **warp_options)
    else:
        if verbose:
            print('translate options: ' + str(translate_options))
        ret_code = gdal.Translate(out_filename, filename, **common_options, **translate_options)

    if not skipped and verbose:
        print_time()
        print('Time for creating file: {} is {} seconds'.format(filename, round(time.time() - start_time)))

    if ret_code is not None:
        if not skipped and hide_nodatavalue:
            gdal_helper.unset_nodatavalue(out_filename)

        if (ovr_type is not None) and (ovr_type != OvrType.copy_internal) and (ovr_type != OvrType.copy_single_external):
            if ovr_type != OvrType.translate_existing:
                gdalos_ovr(out_filename, skip_if_exist=skip_if_exists, ovr_type=ovr_type, print_progress=print_progress,
                           verbose=verbose)
            else:
                overview_count = gdal_helper.get_ovr_count(ds)
                for ovr_index in range(overview_count - 1, -1, -1):
                    out_ovr_filename = out_filename + '.ovr' * (ovr_index + 1)
                    ret_code = gdalos_trans(filename=filename, src_ovr=ovr_index, of=of, tiled=tiled, big_tiff=big_tiff,
                                            warp_CRS=warp_CRS,
                                            out_filename=out_ovr_filename, kind=kind, lossy=lossy,
                                            skip_if_exists=skip_if_exists, out_res=out_res, create_info=False,
                                            dst_nodatavalue=dst_nodatavalue, hide_nodatavalue=hide_nodatavalue,
                                            extent=extent,
                                            src_win=src_win, ovr_type=None, resample_method=resample_method,
                                            keep_alpha=keep_alpha, jpeg_quality=jpeg_quality,
                                            print_progress=print_progress, verbose=verbose)
                    if ret_code is None:
                        break
        if create_info:
            gdalos_info(out_filename, skip_if_exist=skip_if_exists)

    del ds
    return ret_code


def add_ovr(filename, options, open_options, skip_if_exist=False, verbose=True):
    out_filename = filename + '.ovr'
    if verbose:
        print('adding ovr: {} options: {} open_options: {}'.format(out_filename, options, open_options))

    if not do_skip_if_exists(out_filename, skip_if_exist, verbose):
        with gdal_helper.OpenDS(filename, open_options) as ds:
            return ds.BuildOverviews(**options)
    else:
        return 0


def gdalos_ovr(filename, comp=None, kind=None, skip_if_exist=False, ovr_type=..., resampling_method=None,
               print_progress=...,
               ovr_levels_count=10, verbose=True):
    if os.path.isdir(filename):
        filename = os.path.join(filename, default_filename)

    ovr_options = {}

    if not os.path.isfile(filename):
        raise Exception(f'file not found: {filename}')
    if kind is None:
        kind = RasterKind.guess(filename)
    if kind is None:
        raise Exception('could not guess kind')

    if resampling_method is None:
        resampling_method = resample_method_by_kind(kind)

    if comp is None:
        comp = gdal_helper.get_image_structure_metadata(filename, 'COMPRESSION')

    ovr_options['resampling'] = resampling_method
    ovr_options = print_progress_callback(print_progress, ovr_options)

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
            ovr_type = OvrType.create_multi_external
        else:
            ovr_type = OvrType.create_single_external

    out_filename = filename

    open_options = gdal.GA_ReadOnly
    if ovr_type in (OvrType.create_internal, OvrType.create_single_external):
        if ovr_type == OvrType.create_internal:
            open_options = gdal.GA_Update
        ovr_levels = []
        for i in range(ovr_levels_count):
            ovr_levels.append(2 ** (i + 1))  # ovr_levels = '2 4 8 16 32 64 128 256 512 1024'
        ovr_options['overviewlist'] = ovr_levels
        ret_code = add_ovr(out_filename, ovr_options, open_options, skip_if_exist, verbose)
    elif ovr_type == OvrType.create_multi_external:
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


def gdalos_info(filename, skip_if_exist=False):
    if os.path.isdir(filename):
        filename = os.path.join(filename, default_filename)
    if not os.path.isfile(filename):
        raise Exception('file not found: {}'.format(filename))
    out_filename = filename + '.info'
    if not do_skip_if_exists(out_filename, skip_if_exist=skip_if_exist):
        with gdal_helper.OpenDS(filename) as ds:
            info = gdal.Info(ds)
        with open(out_filename, 'w') as w:
            w.write(info)
        ret_code = 0
    else:
        ret_code = 0
    return ret_code
