import collections
import copy
import glob
import json
import math
import os
import tempfile
import time
from enum import Enum
from functools import partial
from pathlib import Path
from typing import Union, Sequence, Optional

import numpy as np
from osgeo import gdal

from gdalos import gdalos_base, gdalos_color, projdef, gdalos_util, gdalos_extent
from gdalos.calc import gdal_calc, gdal_to_czml, gdalos_combine
from gdalos.calc.discrete_mode import DiscreteMode
from gdalos.calc.gdalos_raster_color import gdalos_raster_color
from gdalos.gdalos_base import PathLikeOrStr
from gdalos.gdalos_color import ColorPaletteOrPathOrStrings
from gdalos.gdalos_trans import gdalos_trans, workaround_warp_scale_bug
from gdalos.gdalos_selector import get_projected_pj, DataSetSelector
from gdalos.rectangle import GeoRectangle
from gdalos.talos.geom_arc import PolygonizeSector
from gdalos.talos.ogr_util import create_layer_from_geometries
from gdalos.viewshed import viewshed_params
from gdalos.viewshed.viewshed_grid_params import ViewshedGridParams
from gdalos.viewshed.viewshed_params import ViewshedParams, MultiPointParams, dict_of_selected_items, \
    dict_of_reduce_if_same
from osgeo_utils.auxiliary.extent_util import Extent
from osgeo_utils.auxiliary.util import get_ovr_idx

talos = None


class ViewshedBackend(Enum):
    gdal = 0
    talos = 1
    radio = 2
    rfmodel = 3
    # radio = 2
    # t_radio = 3
    # z_radio = 4


default_LOSBackend = ViewshedBackend.talos
default_ViewshedBackend = ViewshedBackend.gdal
default_RFBackend = ViewshedBackend.rfmodel


class CalcOperation(Enum):
    viewshed = 0
    max = 1
    min = 2
    count = 3
    count_z = 4
    unique = 5


def temp_params(is_temp_file):
    gdal_out_format = 'GTiff' if is_temp_file else 'MEM'
    d_path = tempfile.mktemp(suffix='.tif') if is_temp_file else ''
    return_ds = True
    # return_ds = not is_temp_file
    return is_temp_file, gdal_out_format, d_path, return_ds


def make_slice(slicer):
    if isinstance(slicer, slice):
        return slicer
    if slicer is None:
        return slice(None)
    return slice(*[{True: lambda n: None, False: int}[x == ''](x) for x in (slicer.split(':') + ['', '', ''])[:3]])


def viewshed_calc(output_filename, of='GTiff', **kwargs):
    output_filename = Path(output_filename)
    # ext = output_filename.suffix
    ext = gdalos_util.get_ext_by_of(of)
    if output_filename:
        os.makedirs(os.path.dirname(str(output_filename)), exist_ok=True)
    is_czml = ext == '.czml'
    if is_czml:
        kwargs['out_crs'] = 0  # czml supprts only 4326
    temp_files = []
    ds = viewshed_calc_to_ds(**kwargs, temp_files=temp_files)
    if not ds:
        raise Exception('error occurred')
    if is_czml:
        ds = gdal_to_czml.gdal_to_czml(ds, name=str(output_filename), out_filename=output_filename)
    elif of.upper() != 'MEM':
        driver = gdal.GetDriverByName(of)
        ds = driver.CreateCopy(str(output_filename), ds)

    if temp_files:
        for f in temp_files:
            try:
                os.remove(f)
            except:
                print('failed to remove temp file:{}'.format(f))
    return ds


def viewshed_calc_to_ds(
        vp_array,
        input_filename: Union[gdal.Dataset, PathLikeOrStr, DataSetSelector],
        extent=Extent.UNION, cutline=None, operation: CalcOperation = CalcOperation.count,
        in_coords_srs=None, out_crs=None,
        color_palette: ColorPaletteOrPathOrStrings = None,
        discrete_mode: DiscreteMode = DiscreteMode.interp,
        bi=1, ovr_idx=0, co=None,
        vp_slice=None,
        backend: ViewshedBackend = None,
        temp_files=None,
        files=None):
    input_selector = None
    input_ds = None
    if isinstance(input_filename, PathLikeOrStr.__args__):
        input_ds = gdalos_util.open_ds(input_filename, ovr_idx=ovr_idx)
    elif isinstance(input_filename, DataSetSelector):
        input_selector = input_filename
    else:
        input_ds = input_filename

    if isinstance(extent, int):
        extent = Extent(extent)
    elif isinstance(extent, str):
        extent = Extent[extent]

    is_temp_file, gdal_out_format, d_path, return_ds = temp_params(False)

    color_palette = gdalos_color.get_color_palette(color_palette)
    color_table = gdalos_color.get_color_table(color_palette)
    if operation == CalcOperation.viewshed:
        operation = None

    do_post_color = False
    temp_files = temp_files if temp_files is not None else []

    vp_slice = make_slice(vp_slice)

    if isinstance(discrete_mode, str):
        discrete_mode = DiscreteMode[discrete_mode]

    if not files:
        files = []
    else:
        files = files.copy()[vp_slice]

    if not files:
        if isinstance(vp_array, ViewshedParams):
            vp_array = [vp_array]
        else:
            if isinstance(vp_array, dict):
                vp_array = ViewshedParams.get_list_from_lists_dict(vp_array)
            vp_array = vp_array[vp_slice]

        if operation:
            # restore viewshed consts default values
            my_viewshed_defaults = viewshed_params.viewshed_defaults
            for a in vp_array:
                a.update(my_viewshed_defaults)
        else:
            vp_array = vp_array[0:1]

        max_rasters_count = 1 if operation is None else 254 if operation == CalcOperation.unique else 1000
        if len(vp_array) > max_rasters_count:
            vp_array = vp_array[0:max_rasters_count]

        srs_4326 = projdef.get_srs(4326)
        pjstr_4326 = srs_4326.ExportToProj4()

        first_vs = True

        if in_coords_srs is not None:
            in_coords_srs = projdef.get_proj_string(in_coords_srs)

        for vp in vp_array:
            # vp might get changed, so make a copy
            vp = copy.copy(vp)
            if first_vs or input_selector is not None:
                first_vs = False
                # figure out in_coords_crs_pj for getting the geo_ox, geo_oy
                if input_selector is None:
                    if in_coords_srs is None:
                        if input_ds is None:
                            input_ds = gdalos_util.open_ds(input_filename, ovr_idx=ovr_idx)
                        in_coords_srs = projdef.get_srs_from_ds(input_ds)
                else:
                    if in_coords_srs is None:
                        in_coords_srs = pjstr_4326

                transform_coords_to_4326 = projdef.get_transform(in_coords_srs, pjstr_4326)
                if transform_coords_to_4326:
                    geo_ox, geo_oy, _ = transform_coords_to_4326.TransformPoint(vp.ox, vp.oy)
                else:
                    geo_ox, geo_oy = vp.ox, vp.oy

                # select the ds
                if input_selector is not None:
                    input_filename, input_ds = input_selector.get_item_projected(geo_ox, geo_oy)
                    input_filename = Path(input_filename).resolve()
                if input_ds is None:
                    input_ds = gdalos_util.open_ds(input_filename, ovr_idx=ovr_idx)
                    if input_ds is None:
                        raise Exception(f'cannot open input file: {input_filename}')

                # figure out the input, output and intermediate srs
                # the intermediate srs will be used for combining the output rasters, if needed
                pjstr_input_srs = projdef.get_srs_pj(input_ds)
                pjstr_output_srs = projdef.get_proj_string(out_crs) if out_crs is not None else \
                    pjstr_input_srs if input_selector is None else pjstr_4326
                if input_selector is None:
                    pjstr_inter_srs = pjstr_input_srs
                else:
                    pjstr_inter_srs = pjstr_output_srs

                input_srs = projdef.get_srs_from_ds(input_ds)
                input_raster_is_projected = input_srs.IsProjected()
                if input_raster_is_projected:
                    transform_coords_to_raster = projdef.get_transform(in_coords_srs, pjstr_input_srs)
                else:
                    raise Exception(f'input raster has to be projected')
            if input_raster_is_projected:
                projected_filename = input_filename
                if transform_coords_to_raster:
                    vp.ox, vp.oy, _ = transform_coords_to_raster.TransformPoint(vp.ox, vp.oy)
            else:
                projected_pj = get_projected_pj(geo_ox, geo_oy)
                transform_coords_to_raster = projdef.get_transform(in_coords_srs, projected_pj)
                vp.ox, vp.oy, _ = transform_coords_to_raster.TransformPoint(vp.ox, vp.oy)
                d = gdalos_extent.transform_resolution_p(transform_coords_to_raster, 10, 10, vp.ox, vp.oy)
                extent = GeoRectangle.from_center_and_radius(vp.ox, vp.oy, vp.max_r + d, vp.max_r + d)

                projected_filename = tempfile.mktemp('.tif')
                projected_ds = gdalos_trans(
                    input_ds, out_filename=projected_filename, warp_srs=projected_pj,
                    extent=extent, return_ds=True, write_info=False, write_spec=False)
                if not projected_ds:
                    raise Exception('input raster projection faild')
                input_ds = projected_ds

            if backend is None:
                backend = default_ViewshedBackend
            elif isinstance(backend, str):
                backend = ViewshedBackend[backend]

            is_base_calc = True
            if backend == ViewshedBackend.gdal:
                # TypeError: '>' not supported between instances of 'NoneType' and 'int'
                bnd_type = gdal.GDT_Byte
                # todo: why dosn't it work without it?
                is_temp_file, gdal_out_format, d_path, return_ds = temp_params(True)

                inputs = vp.get_as_gdal_params()
                print(inputs)

                input_band: Optional[gdal.Band] = input_ds.GetRasterBand(bi)
                if input_band is None:
                    raise Exception('band number out of range')
                ds = gdal.ViewshedGenerate(input_band, gdal_out_format, str(d_path), co, **inputs)
                input_band = None  # close band

                if not ds:
                    raise Exception('Viewshed calculation failed')
            elif backend == ViewshedBackend.talos:
                # is_temp_file = True  # output is file, not ds
                if not projected_filename:
                    raise Exception('to use talos backend you need to provide an input filename')
                # if 'talosgis.talos' not in sys.modules:
                global talos
                if talos is None:
                    try:
                        import talosgis
                        from talosgis import talos
                        from talosgis import talos_utils
                        talos_utils.talos_init()
                    except ImportError:
                        raise Exception('failed to load talos backend')

                dtm_open_err = talos.GS_DtmOpenDTM(str(projected_filename))
                talos.GS_SetProjectCRSFromActiveDTM()
                talos.GS_DtmSelectOvle(ovr_idx or 0)
                if dtm_open_err != 0:
                    raise Exception('talos could not open input file {}'.format(projected_filename))
                talos.GS_SetRefractionCoeff(vp.refraction_coeff)

                inputs = vp.get_as_talos_params()
                bnd_type = inputs['result_dt']
                is_base_calc = bnd_type in [gdal.GDT_Byte]
                inputs['low_nodata'] = is_base_calc or operation == CalcOperation.max

                if hasattr(talos, 'GS_SetCalcModule'):
                    talos.GS_SetCalcModule(vp.get_calc_module())
                if vp.is_radio():
                    if not hasattr(talos, 'GS_SetRadioParameters'):
                        raise Exception('This version does not support radio')
                    radio_params = vp.get_radio_as_talos_params(0)
                    talos.GS_SetRadioParameters(**radio_params)

                if 'GS_Viewshed_Calc2' in dir(talos):
                    ras = talos.GS_Viewshed_Calc2(**inputs)
                else:
                    del inputs['out_res']
                    ras = talos.GS_Viewshed_Calc1(**inputs)

                if ras is None:
                    raise Exception(f'fail to calc viewshed: {inputs}')

                do_post_color = color_table and (bnd_type not in [gdal.GDT_Byte, gdal.GDT_UInt16])

                # talos supports only file output (not ds)
                is_temp_file, gdal_out_format, d_path, return_ds = temp_params(True)

                talos.GS_SaveRaster(ras, str(d_path))
                ras = None
                # I will reopen the ds to change the color table and ndv
                # ds = gdalos_util.open_ds(d_path, access_mode=gdal.OF_UPDATE)
                ds = gdal.OpenEx(str(d_path), gdal.OF_RASTER | gdal.OF_UPDATE)
            else:
                raise Exception('unknown backend {}'.format(backend))

            input_ds = None

            set_nodata = backend == ViewshedBackend.gdal
            # set_nodata = is_base_calc
            bnd = ds.GetRasterBand(1)
            if set_nodata:
                base_calc_ndv = vp.ndv
                bnd.SetNoDataValue(base_calc_ndv)
            else:
                base_calc_ndv = bnd.GetNoDataValue()
            if color_table and not do_post_color:
                if bnd_type != bnd.DataType:
                    raise Exception('Unexpected band type, expected: {}, got {}'.format(bnd_type, bnd.DataType))
                bnd.SetRasterColorTable(color_table)
                bnd.SetRasterColorInterpretation(gdal.GCI_PaletteIndex)
            bnd = None

            if is_temp_file:
                # close original ds and reopen
                ds = None
                ds = gdalos_util.open_ds(d_path)
                temp_files.append(d_path)

            cut_sector = (backend == ViewshedBackend.gdal) and not vp.is_omni_h()
            # warp_result = False
            warp_result = (input_selector is not None)
            if warp_result or cut_sector:
                if cut_sector:
                    ring = PolygonizeSector(vp.ox, vp.oy, vp.max_r, vp.max_r, vp.azimuth, vp.h_aperture)
                    calc_cutline = tempfile.mktemp(suffix='.gpkg')
                    temp_files.append(calc_cutline)
                    create_layer_from_geometries([ring], calc_cutline)
                else:
                    calc_cutline = None
                # todo: check why without temp file it crashes on operation
                is_temp_file, gdal_out_format, d_path, return_ds = temp_params(True)
                scale = ds.GetRasterBand(1).GetScale()
                ds = gdalos_trans(ds, out_filename=d_path, warp_srs=pjstr_inter_srs,
                                  cutline=calc_cutline, of=gdal_out_format, return_ds=return_ds, ovr_type=None)
                if is_temp_file:
                    # close original ds and reopen
                    ds = None
                    ds = gdalos_util.open_ds(d_path)
                    if scale and workaround_warp_scale_bug:
                        ds.GetRasterBand(1).SetScale(scale)
                    temp_files.append(d_path)
                if not ds:
                    raise Exception('Viewshed calculation failed to cut')

            if operation:
                files.append(ds)

    if operation:
        # alpha_pattern = '1*({{}}>{})'.format(viewshed_thresh)
        # alpha_pattern = 'np.multiply({{}}>{}, dtype=np.uint8)'.format(viewshed_thresh)
        no_data_value = base_calc_ndv
        if operation == CalcOperation.viewshed:
            # no_data_value = viewshed_params.viewshed_ndv
            f = gdalos_combine.get_by_index
            # calc_expr, calc_kwargs, f = gdal_calc.make_calc_with_func(files, alpha_pattern, 'f'), sum
        elif operation == CalcOperation.max:
            # no_data_value = viewshed_params.viewshed_ndv
            f = gdalos_combine.vs_max
            # calc_expr, calc_kwargs, f = gdal_calc.make_calc_with_func(files, alpha_pattern, 'f'), sum
        elif operation == CalcOperation.min:
            f = gdalos_combine.vs_min
        elif operation == CalcOperation.count:
            no_data_value = 0
            f = gdalos_combine.vs_count
            # calc_expr, calc_kwargs = gdal_calc.make_calc_with_operand(files, alpha_pattern, '+')
            # calc_expr, calc_kwargs, f = gdal_calc.make_calc_with_func(files, alpha_pattern), sum
        elif operation == CalcOperation.count_z:
            no_data_value = viewshed_params.viewshed_comb_ndv
            f = partial(gdalos_combine.vs_count_z, in_ndv=base_calc_ndv)
            # calc_expr, calc_kwargs f, = gdal_calc.make_calc_with_func(files, alpha_pattern, 'f'), sum
        elif operation == CalcOperation.unique:
            no_data_value = viewshed_params.viewshed_comb_ndv
            f = gdalos_combine.vs_unique
            # calc_expr, calc_kwargs, f = gdal_calc.make_calc_with_func(files, alpha_pattern, 'f'), unique
        else:
            raise Exception('Unknown operation: {}'.format(operation))

        calc_expr = 'f(x)'
        calc_kwargs = dict(x=files)
        user_namespace = dict(f=f)

        hide_nodata = True

        debug_time = 1
        t = time.time()
        for i in range(debug_time):
            is_temp_file, gdal_out_format, d_path, return_ds = temp_params(False)
            ds = gdal_calc.Calc(
                calc_expr, outfile=str(d_path), extent=extent, format=gdal_out_format,
                color_table=color_table, hideNodata=hide_nodata, overwrite=True,
                NoDataValue=no_data_value, user_namespace=user_namespace, **calc_kwargs)
        t = time.time() - t
        print('time for calc: {:.3f} seconds'.format(t))

        if not ds:
            raise Exception('error occurred')
        for i in range(len(files)):
            files[i] = None  # close calc input ds(s)

    combined_post_process_needed = cutline or not projdef.are_srs_equivalent(pjstr_inter_srs, pjstr_output_srs)
    if combined_post_process_needed:
        is_temp_file, gdal_out_format, d_path, return_ds = temp_params(False)
        ds = gdalos_trans(ds, out_filename=d_path, warp_srs=pjstr_output_srs,
                          cutline=cutline, of=gdal_out_format, return_ds=return_ds, ovr_type=None)

        if return_ds:
            if not ds:
                raise Exception('error occurred')

    if do_post_color:
        is_temp_file, gdal_out_format, d_path, return_ds = temp_params(False)
        ds = gdalos_raster_color(ds, out_filename=d_path, color_palette=color_palette, discrete_mode=discrete_mode)
        if not ds:
            raise Exception('Viewshed calculation failed to color result')

    removed = []
    if temp_files:
        for f in temp_files:
            try:
                os.remove(f)
                removed.append(f)
            except:
                pass
                # probably this is a file that backs the ds that we'll return
                # print('failed to remove temp file:{}'.format(f))
    for f in removed:
        temp_files.remove(f)
    return ds


# def mock_los_arr(rows=10, cols=6) -> np.ndarray:
#     return np.arange(rows*cols).reshape((rows, cols))


def los_calc(
        vp,
        input_filename: Union[gdal.Dataset, PathLikeOrStr, DataSetSelector],
        del_s: float,
        in_coords_srs=None, out_crs=None,
        bi=1, ovr_idx=0, co=None, of='xyz',
        backend: ViewshedBackend = None,
        output_filename=None,
        mock=False):
    input_selector = None
    input_ds = None
    if isinstance(input_filename, PathLikeOrStr.__args__):
        input_ds = gdalos_util.open_ds(input_filename, ovr_idx=ovr_idx)
    elif isinstance(input_filename, DataSetSelector):
        input_selector = input_filename
    else:
        input_ds = input_filename

    srs_4326 = projdef.get_srs(4326)
    pjstr_4326 = srs_4326.ExportToProj4()

    if in_coords_srs is not None:
        in_coords_srs = projdef.get_proj_string(in_coords_srs)

    # figure out in_coords_crs_pj for getting the geo_ox, geo_oy
    if input_selector is None:
        if in_coords_srs is None:
            if input_ds is None:
                input_ds = gdalos_util.open_ds(input_filename, ovr_idx=ovr_idx)
            in_coords_srs = projdef.get_srs_from_ds(input_ds)
    else:
        if in_coords_srs is None:
            in_coords_srs = pjstr_4326

    if isinstance(vp, dict):
        vp = MultiPointParams.get_object_from_lists_dict(vp)
    transform_coords_to_4326 = projdef.get_transform(in_coords_srs, pjstr_4326)
    vp.make_xy_lists()
    o_points = vp.oxy
    t_points = vp.txy
    if transform_coords_to_4326:
        # todo: use TransformPoints
        geo_o = transform_coords_to_4326.TransformPoints(o_points)
        geo_t = transform_coords_to_4326.TransformPoints(t_points)
    else:
        geo_o = o_points
        geo_t = t_points

    # select the ds
    if input_selector is not None:
        min_x = min_y = math.inf
        max_x = max_y = -math.inf
        for x, y in geo_o:
            if x < min_x:
                min_x = x
            if x > max_x:
                max_x = x
            if y < min_y:
                min_y = y
            if y > max_y:
                max_y = y
        for x, y in geo_t:
            if x < min_x:
                min_x = x
            if x > max_x:
                max_x = x
            if y < min_y:
                min_y = y
            if y > max_y:
                max_y = y
        input_filename, input_ds = input_selector.get_item_projected((min_x+max_x)/2, (min_y+max_y)/2)
        input_filename = Path(input_filename).resolve()
    if input_ds is None and not mock:
        input_ds = gdalos_util.open_ds(input_filename, ovr_idx=ovr_idx)
        if input_ds is None:
            raise Exception(f'cannot open input file: {input_filename}')

    # figure out the input, output and intermediate srs
    # the intermediate srs will be used for combining the output rasters, if needed
    if input_ds is not None:
        pjstr_input_srs = projdef.get_srs_pj(input_ds)
        pjstr_output_srs = projdef.get_proj_string(out_crs) if out_crs is not None else \
            pjstr_input_srs if input_selector is None else pjstr_4326
        if input_selector is None:
            pjstr_inter_srs = pjstr_input_srs
        else:
            pjstr_inter_srs = pjstr_output_srs

        input_srs = projdef.get_srs_from_ds(input_ds)
        input_raster_is_projected = input_srs.IsProjected()

        is_radio = vp.radio_parameters is not None
        if isinstance(backend, str):
            backend = ViewshedBackend[backend]
        if backend == ViewshedBackend.radio and not is_radio:
            raise Exception('No radio parameters were provided')
        if backend is None or backend == ViewshedBackend.radio:
            backend = default_RFBackend if (is_radio and not input_raster_is_projected) else default_LOSBackend

        backend_requires_projected_ds = backend != ViewshedBackend.rfmodel

        if input_raster_is_projected:
            transform_coords_to_raster = projdef.get_transform(in_coords_srs, pjstr_input_srs)
            projected_filename = input_filename
            if transform_coords_to_raster:
                o_points = transform_coords_to_raster.TransformPoints(o_points)
                t_points = transform_coords_to_raster.TransformPoints(t_points)
        elif backend_requires_projected_ds:
            raise Exception(f'input raster has to be projected')
        else:
            pass
            # projected_pj = get_projected_pj(geo_o[0][0], geo_o[0][1])
            # transform_coords_to_raster = projdef.get_transform(in_coords_srs, projected_pj)
            # vp.ox, vp.oy, _ = transform_coords_to_raster.TransformPoints(vp.ox, vp.oy)
            # d = gdalos_extent.transform_resolution_p(transform_coords_to_raster, 10, 10, vp.ox, vp.oy)
            # extent = GeoRectangle.from_center_and_radius(vp.ox, vp.oy, vp.max_r + d, vp.max_r + d)
            #
            # projected_filename = tempfile.mktemp('.tif')
            # projected_ds = gdalos_trans(
            #     input_ds, out_filename=projected_filename, warp_srs=projected_pj,
            #     extent=extent, return_ds=True, write_info=False, write_spec=False)
            # if not projected_ds:
            #     raise Exception('input raster projection faild')
            # # input_ds = projected_ds

    o_points, t_points = gdalos_base.make_pairs(o_points, t_points, vp.ot_fill)
    vp.oxy = list(o_points)
    vp.txy = list(t_points)

    if backend == ViewshedBackend.rfmodel:
        from rfmodel.rfmodel import calc_path_loss_lonlat_multi
        from tirem.tirem3 import calc_tirem_loss

        inputs = vp.get_as_rfmodel_params(del_s=del_s)
        output_arrays = calc_path_loss_lonlat_multi(calc_tirem_loss, input_ds, **inputs)

        res = collections.OrderedDict()
        output_names = vp.mode
        mode_map = dict(PathLoss=1, FreeSpaceLoss=2)
        for idx, name in enumerate(output_names):
            res[name] = output_arrays[mode_map[name]]

    elif backend == ViewshedBackend.talos:
        inputs = vp.get_as_talos_params()

        if not mock:
            if not projected_filename:
                raise Exception('to use talos backend you need to provide an input filename')
            global talos
            if talos is None:
                try:
                    import talosgis
                    from talosgis import talos
                    from talosgis import talos_utils
                    talos_utils.talos_init()
                except ImportError:
                    raise Exception('failed to load talos backend')
            dtm_open_err = talos.GS_DtmOpenDTM(str(projected_filename))
            if dtm_open_err != 0:
                raise Exception('talos could not open input file {}'.format(projected_filename))
            talos.GS_SetProjectCRSFromActiveDTM()
            ovr_idx = get_ovr_idx(projected_filename, ovr_idx)
            talos.GS_DtmSelectOvle(ovr_idx)

            refraction_coeff = vp.refraction_coeff
            if isinstance(refraction_coeff, Sequence):
                refraction_coeff = refraction_coeff[0]
            talos.GS_SetRefractionCoeff(refraction_coeff)

            if hasattr(talos, 'GS_SetCalcModule'):
                talos.GS_SetCalcModule(vp.get_calc_module())
            radio_params = vp.get_radio_as_talos_params()
            if radio_params is not None and not hasattr(talos, 'GS_SetRadioParameters'):
                raise Exception('This version does not support radio')

            dict_of_selected_items(radio_params, index=0)
            # multi_radio_params = dict_of_selected_items(radio_params, check_only=True)
            multi_radio_params = dict_of_reduce_if_same(radio_params)
            if multi_radio_params:
                # raise Exception('unsupported multiple radio parameters')
                dict_of_selected_items(radio_params, index=0)
                talos.GS_SetRadioParameters(**radio_params)
                result = talos.GS_Radio_Calc(**inputs)
            else:
                if radio_params:
                    talos.GS_SetRadioParameters(**radio_params)
                result = talos.GS_Radio_Calc(**inputs)
            if result:
                raise Exception('talos calc error')

        input_names = ['ox', 'oy', 'oz', 'tx', 'ty', 'tz']
        # input_names = ['ox', 'oy', 'tx', 'ty']

        output_names = vp.mode
        output_arrays = inputs['AIO_re']
        output_arrays = [output_arrays[i] for i in range(len(output_arrays))]

        res = collections.OrderedDict()
        for name in input_names:
            res[name] = inputs[f'AIO_{name}']
        for idx, name in enumerate(output_names):
            res[vp.mode[idx]] = output_arrays[idx]
    else:
        raise Exception('unknown or unsupported backend {}'.format(backend))

    if res is None:
        raise Exception('error occurred')
    elif output_filename is not None:
        os.makedirs(os.path.dirname(str(output_filename)), exist_ok=True)
        output_filename = Path(output_filename)
        if of == 'json':
            res['r'] = [input_filename]
            with open(output_filename, 'w') as outfile:
                json_dump = {k: v.tolist() if isinstance(v, np.ndarray) else str(v) for k, v in res.items()}
                json.dump(json_dump, outfile, indent=2)
        else:
            xyz = np.stack(res.values()).transpose()
            np.savetxt(output_filename, xyz, fmt='%s')

    return res


def test_calcz(vp_array, raster_filename, dir_path,
               backends=(ViewshedBackend.talos,), calc_filter=CalcOperation, **kwargs):
    cwd = Path.cwd()
    for backend in backends:
        for color_palette in [..., None]:
            prefix = 'calcz_color' if color_palette else 'calcz'
            output_path = dir_path / str(backend) / prefix
            for calc in calc_filter:
                # if calc != CalcOperation.viewshed:
                #     continue
                if color_palette is ...:
                    color_palette = cwd / 'sample/color_files/gradient/{}.txt'.format('percentages')  # calc.name)
                if calc == CalcOperation.viewshed:
                    # continue
                    for i, vp in enumerate(vp_array):
                        output_filename = output_path / Path('{}_{}.tif'.format(calc.name, i))
                        viewshed_calc(input_filename=raster_filename,
                                      output_filename=output_filename,
                                      vp_array=vp,
                                      backend=backend,
                                      operation=calc,
                                      color_palette=color_palette,
                                      **kwargs
                                      )
                elif calc in [CalcOperation.max, CalcOperation.min]:
                    output_filename = output_path / Path('{}.tif'.format(calc.name))
                    viewshed_calc(input_filename=raster_filename,
                                  output_filename=output_filename,
                                  vp_array=vp_array,
                                  backend=backend,
                                  operation=calc,
                                  color_palette=color_palette,
                                  **kwargs,
                                  # vp_slice=slice(0, 2)
                                  )


def test_simple_viewshed(vp_array, raster_filename, dir_path, run_comb_with_post=False,
                         backends=reversed(ViewshedBackend), calc_filter=CalcOperation, **kwargs):
    # calc_filter = [CalcOperation.count_z]
    cwd = Path.cwd()
    for backend in backends:
        output_path = dir_path / str(backend) / 'normal'
        for calc in calc_filter:
            if calc == CalcOperation.viewshed:
                for i, vp in enumerate(vp_array):
                    color_palette = None if vp.is_radio() else cwd / f'sample/color_files/viewshed/{calc.name}.txt'
                    prefix = 'radio' if vp.is_radio() else 'vs'
                    output_filename = output_path / f'{prefix}_{calc.name}_{i}.tif'
                    viewshed_calc(input_filename=raster_filename,
                                  output_filename=output_filename,
                                  vp_array=vp,
                                  backend=backend,
                                  operation=calc,
                                  color_palette=color_palette,
                                  **kwargs,
                                  )
            else:
                prefix = 'radio' if vp_array[0].is_radio() else 'vs'
                output_filename = output_path / f'{prefix}_{calc.name}.tif'
                try:
                    viewshed_calc(input_filename=raster_filename,
                                  output_filename=output_filename,
                                  vp_array=vp_array,
                                  backend=backend,
                                  operation=calc,
                                  color_palette=color_palette,
                                  **kwargs,
                                  # vp_slice=slice(0, 2)
                                  )
                except:
                    print(f'failed to run viewshed calc with backend: {backend}, inputs: {vp_array}')

        if run_comb_with_post:
            output_filename = output_path / 'combine_post.tif'
            cutline = cwd / r'sample/shp/comb_poly.gml'
            viewshed_calc(input_filename=raster_filename,
                          output_filename=output_filename,
                          vp_array=vp_array,
                          backend=backend,
                          operation=CalcOperation.count,
                          color_palette=color_palette,
                          cutline=cutline,
                          out_crs=0,
                          **kwargs)


def main_test(calcz=True, simple_viewshed=True, is_geo_coords=False, is_geo_raster=False, is_radio=False):
    # dir_path = Path('/home/idan/maps')
    dir_path = Path(r'd:\dev\gis\maps')

    vp = ViewshedGridParams(is_geo_coords, is_radio)
    in_coords_srs = 4326 if is_geo_coords else None

    if is_geo_raster:
        raster_filename = Path(r'd:\Maps\w84geo\dtm_SRTM1_hgt_ndv0.cog.tif.new.cog.tif.x[20,80]_y[20,40].cog.tif')
    else:
        if is_geo_coords:
            raster_filename = DataSetSelector(r'd:\Maps\srtm3.tif\utm.cog2\*.tif')
        else:
            raster_filename = Path(dir_path) / Path('srtm1_36_sample.tif')

    use_input_files = False
    if use_input_files:
        files_path = Path('/home/idan/maps/grid_comb/viewshed')
        files = glob.glob(str(files_path / '*.tif'))
    else:
        files = None

    if simple_viewshed:
        vp_array = vp.get_array()
        backends = [ViewshedBackend.talos] if is_radio else reversed(ViewshedBackend)
        test_simple_viewshed(vp_array=vp_array, run_comb_with_post=False, files=files, in_coords_srs=in_coords_srs,
                             dir_path=dir_path, raster_filename=raster_filename, backends=backends)
    if calcz:
        vp1 = copy.copy(vp)
        vp1.tz = None
        vp_array = vp1.get_array()
        test_calcz(vp_array=vp_array, raster_filename=raster_filename, in_coords_srs=in_coords_srs, dir_path=dir_path,
                   # calc_filter=[CalcOperation.max],
                   files=files)


if __name__ == "__main__":
    # main_test(is_geo_coords=False, simple_viewshed=True, calcz=True, is_radio=False)
    # main_test(is_geo_coords=False, simple_viewshed=True, calcz=False, is_radio=True)
    filename=r'd:\temp\1.txt'
    los_calc(filename)
