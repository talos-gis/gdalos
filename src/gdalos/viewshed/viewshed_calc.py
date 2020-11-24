from functools import partial
from typing import Union

from osgeo import gdal
import glob
import tempfile
import os
import time
from pathlib import Path
from enum import Enum

import copy

from gdalos.gdalos_types import FileName
from gdalos.rectangle import GeoRectangle
from gdalos import projdef, gdalos_util, gdalos_color, gdalos_trans, gdalos_extent
from gdalos.gdalos_color import ColorPaletteOrPathOrStrings
from gdalos.calc import gdal_calc, gdal_to_czml, dict_util, gdalos_combine
from gdalos.viewshed import viewshed_params
from gdalos.viewshed.viewshed_params import ViewshedParams
from gdalos.viewshed.viewshed_grid_params import ViewshedGridParams
from gdalos.talos.ogr_util import create_layer_from_geometries
from gdalos.talos.geom_arc import PolygonizeSector
from gdalos.calc.discrete_mode import DiscreteMode
from gdalos.calc.gdalos_raster_color import gdalos_raster_color
from gdalos.gdalos_selector import get_projected_pj, DataSetSelector

talos = None


class ViewshedBackend(Enum):
    gdal = 0
    talos = 1


default_ViewshedBackend = ViewshedBackend.gdal


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


def viewshed_calc(output_filename, of='GTiff', return_ds=None, **kwargs):
    output_filename = Path(output_filename)
    print(output_filename)
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
    if not return_ds:
        ds = None

    if temp_files:
        for f in temp_files:
            try:
                os.remove(f)
            except:
                print('failed to remove temp file:{}'.format(f))
    return ds


def viewshed_calc_to_ds(vp_array,
                        input_filename:Union[gdal.Dataset, FileName, DataSetSelector],
                        extent=2, cutline=None, operation: CalcOperation = CalcOperation.count,
                        in_coords_srs=None, out_crs=None,
                        color_palette: ColorPaletteOrPathOrStrings=None,
                        discrete_mode: DiscreteMode=DiscreteMode.interp,
                        bi=1, ovr_idx=0, co=None,
                        vp_slice=None,
                        backend:ViewshedBackend=None,
                        temp_files=None,
                        files=None):
    input_selector = None
    input_ds = None
    if isinstance(input_filename, FileName.__args__):
        input_ds = gdalos_util.open_ds(input_filename, ovr_idx=ovr_idx)
    elif isinstance(input_filename, DataSetSelector):
        input_selector = input_filename
        if input_selector.get_map_count() == 1:
            input_filename = input_selector.get_map(0)
            input_selector = None
    else:
        input_ds = input_filename

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
                vp_array = ViewshedGridParams.get_list_from_lists_dict(vp_array)
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
                # figure out in_coords_crs_pj for getting the geo_x, geo_y
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
                    geo_x, geo_y, _ = transform_coords_to_4326.TransformPoint(vp.ox, vp.oy)
                else:
                    geo_x, geo_y = vp.ox, vp.oy

                # select the ds
                if input_selector is not None:
                    input_filename, input_ds = input_selector.get_item_projected(geo_x, geo_y)
                    input_filename = Path(input_filename).resolve()
                if input_ds is None:
                    input_ds = gdalos_util.open_ds(input_filename, ovr_idx=ovr_idx)
                    if input_ds is None:
                        raise Exception(f'cannot open input file: {input_filename}')

                # figure out the input, output and intermediate srs
                # the intermediate srs will be used for combining the output rasters, if needed
                pjstr_input_srs = projdef.get_srs_pj_from_ds(input_ds)
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
                projected_pj = get_projected_pj(geo_x, geo_y)
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

                input_band: gdal.Band = input_ds.GetRasterBand(bi)
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
                        from talosgis import talos2 as talos
                        import talosgis_data.__data__
                        import gdalos_data.__data__
                    except ImportError:
                        raise Exception('failed to load talos backend')

                    print('gdalos Version ', gdalos_data.__data__.__version__)
                    print('talos Version ', talosgis_data.__data__.__version__)
                    talos_ver = talos.GS_GetIntVersion()
                    print('GS_GetIntVersion ', talos_ver)
                    print('GS_GetDLLVersion ', talos.GS_GetDLLVersion())
                    print('GS_DtmGetCalcThreadsCount ', talos.GS_DtmGetCalcThreadsCount())

                    if hasattr(talos, 'GS_SetGDALPath'):
                        gdal_path = talosgis.get_talos_gdal_path()
                        talos.GS_SetGDALPath(gdal_path)
                    if hasattr(talos, 'GS_SetProjPath'):
                        proj_path = talosgis.get_talos_proj_path()
                        talos.GS_SetProjPath(proj_path)
                    if hasattr(talos, 'GS_SetRadioPath'):
                        radio_path = talosgis.get_talos_radio_path()
                        talos.GS_SetRadioPath(radio_path)

                    # print('GS_GetGDALPath ', talos.GS_GetGDALPath())
                    print('GS_talosInit ', talos.GS_talosInit())

                    # print('GS_IsGDALLoaded ', talos.GS_IsGDALLoaded())
                    # print('GS_GetGDALPath ', talos.GS_GetGDALPath())

                    # print('GS_SetCacheSize ', talos.GS_SetCacheSize(cache_size_mb))

                dtm_open_err = talos.GS_DtmOpenDTM(str(projected_filename))
                talos.GS_SetProjectCRSFromActiveDTM()
                if ovr_idx:
                    talos.GS_DtmSelectOvle(ovr_idx)
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
                    talos.GS_SetRadioParameters(**vp.get_radio_as_talos_params())

                ras = talos.GS_Viewshed_Calc1(**inputs)

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
                ds = gdalos_trans(ds, out_filename=d_path, warp_srs=pjstr_inter_srs,
                                  cutline=calc_cutline, of=gdal_out_format, return_ds=return_ds, ovr_type=None)
                if is_temp_file:
                    # close original ds and reopen
                    ds = None
                    ds = gdalos_util.open_ds(d_path)
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
                color_table=color_table, hideNodata=hide_nodata, return_ds=return_ds, overwrite=True,
                NoDataValue=no_data_value, user_namespace=user_namespace, **calc_kwargs)
        t = time.time() - t
        print('time for calc: {:.3f} seconds'.format(t))

        if return_ds:
            if not ds:
                raise Exception('error occurred')
        for i in range(len(files)):
            files[i] = None  # close calc input ds(s)

    combined_post_process_needed = cutline or not projdef.proj_is_equivalent(pjstr_inter_srs, pjstr_output_srs)
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


def test_calcz(vp_array, raster_filename, dir_path, calcs=None, **kwargs):
    if calcs is None:
        calcs = CalcOperation
    cwd = Path.cwd()
    backend = ViewshedBackend.talos
    for color_palette in [..., None]:
        prefix = 'calcz_color_' if color_palette else 'calcz_'
        output_path = dir_path / Path(prefix + str(backend))
        for calc in calcs:
            # if calc != CalcOperation.viewshed:
            #     continue
            if color_palette is ...:
                color_palette = cwd / 'sample/color_files/gradient/{}.txt'.format('percentages')  #calc.name)
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


def test_simple_viewshed(vp_array, raster_filename, dir_path, run_comb_with_post=False, **kwargs):
    calc_filter = CalcOperation
    # calc_filter = [CalcOperation.count_z]
    cwd = Path.cwd()
    for backend in reversed(ViewshedBackend):
        output_path = dir_path / Path('comb_' + str(backend))
        for calc in calc_filter:
            if calc == CalcOperation.viewshed:
                for i, vp in enumerate(vp_array):
                    color_palette = None if vp.is_radio else cwd / 'sample/color_files/viewshed/{}.txt'.format(calc.name)
                    output_filename = output_path / Path('{}_{}.tif'.format(calc.name, i))
                    viewshed_calc(input_filename=raster_filename,
                                  output_filename=output_filename,
                                  vp_array=vp,
                                  backend=backend,
                                  operation=calc,
                                  color_palette=color_palette,
                                  **kwargs,
                                  )
            else:
                output_filename = output_path / Path('{}.tif'.format(calc.name))
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
                    print('failed to run viewshed calc with backend: {}, inputs: {}'.format(backend, vp_array))

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
        test_simple_viewshed(vp_array=vp_array, run_comb_with_post=False, files=files, in_coords_srs=in_coords_srs,
                             dir_path=dir_path, raster_filename=raster_filename)
    if calcz:
        vp1 = copy.copy(vp)
        vp1.tz = None
        vp_array = vp1.get_array()
        test_calcz(vp_array=vp_array, raster_filename=raster_filename, in_coords_srs=in_coords_srs, dir_path=dir_path,
                   # calcs=[CalcOperation.max],
                   files=files)


if __name__ == "__main__":
    main_test(is_geo_coords=False,
              is_radio=True,
              # simple_viewshed=False
              )
