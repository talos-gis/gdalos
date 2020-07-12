from enum import Enum
import sys
from functools import partial
import gdal, osr, ogr
import glob
import tempfile
import os
import time
from pathlib import Path
from enum import Enum
import copy
from attr import exceptions

from gdalos import projdef, gdalos_util, gdalos_color, gdalos_trans
from gdalos.calc import gdal_calc, gdal_to_czml, dict_util, gdalos_combine
from gdalos.viewshed import viewshed_params
from gdalos.viewshed.viewshed_params import ViewshedParams
from gdalos.viewshed.viewshed_grid_params import ViewshedGridParams
from gdalos.talos.ogr_util import create_layer_from_geometries
from gdalos.talos.geom_arc import PolygonizeSector
from gdalos.calc.gdal_dem_color_cutline import gdaldem_crop_and_color

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
    return_ds = not is_temp_file
    return is_temp_file, gdal_out_format, d_path, return_ds


def make_slice(slicer):
    if isinstance(slicer, slice):
        return slicer
    if slicer is None:
        return slice(None)
    return slice(*[{True: lambda n: None, False: int}[x == ''](x) for x in (slicer.split(':') + ['', '', ''])[:3]])


def viewshed_calc(output_filename, of='GTiff', **kwargs):
    output_filename = Path(output_filename)
    print(output_filename)
    # ext = output_filename.suffix
    ext = gdalos_util.get_ext_by_of(of)
    if output_filename:
        os.makedirs(os.path.dirname(str(output_filename)), exist_ok=True)
    is_czml = ext == '.czml'
    if is_czml:
        kwargs['out_crs'] = 0  # czml supprts only 4326
    temp_files=[]
    ds = viewshed_calc_to_ds(**kwargs, temp_files=temp_files)
    if not ds:
        raise Exception('error occurred')
    dst_ds = None
    if is_czml:
        gdal_to_czml.gdal_to_czml(ds, name=str(output_filename), out_filename=output_filename)
    else:
        driver = gdal.GetDriverByName(of)
        dst_ds = driver.CreateCopy(str(output_filename), ds)
        # dst_ds = None
    ds = None

    if temp_files:
        for f in temp_files:
            try:
                os.remove(f)
            except:
                print('failed to remove temp file:{}'.format(f))
    return dst_ds


def viewshed_calc_to_ds(vp_array,
                        input_ds,
                        input_filename=None,
                        extent=2, cutline=None, operation: CalcOperation = CalcOperation.count,
                        in_coords_crs_pj=None, out_crs=None,
                        color_palette=None,
                        color_mode=True,
                        bi=1, co=None,
                        vp_slice=None,
                        backend:ViewshedBackend=None,
                        temp_files=None,
                        files=None):
    is_temp_file, gdal_out_format, d_path, return_ds = temp_params(False)

    color_table = gdalos_color.get_color_table(color_palette)
    if operation == CalcOperation.viewshed:
        operation = None

    do_color = False
    temp_files = temp_files or []

    combined_post_process_needed = False

    vp_slice = make_slice(vp_slice)

    if not files:
        files = []
    else:
        files = files.copy()[vp_slice]

    if input_filename is not None:
        input_filename = Path(input_filename).resolve()
        if input_ds is None:
            input_ds = gdalos_util.open_ds(input_filename)
    if input_ds is None:
        if not files:
            raise Exception('ds is None')
    else:
        input_band: gdal.Band = input_ds.GetRasterBand(bi)
        if input_band is None:
            raise Exception('band number out of range')

        pjstr_src_srs = projdef.get_srs_pj_from_ds(input_ds)
        pjstr_tgt_srs = projdef.get_proj_string(out_crs) if out_crs is not None else pjstr_src_srs
        combined_post_process_needed = cutline or not projdef.proj_is_equivalent(pjstr_src_srs, pjstr_tgt_srs)

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

        # in_raster_srs = projdef.get_srs_pj_from_ds(input_ds)
        in_raster_srs = osr.SpatialReference()
        in_raster_srs.ImportFromWkt(input_ds.GetProjection())
        if not in_raster_srs.IsProjected:
            raise Exception(f'input raster has to be projected')

        if in_coords_crs_pj is not None:
            in_coords_crs_pj = projdef.get_proj_string(in_coords_crs_pj)
            transform_coords_to_raster = projdef.get_transform(in_coords_crs_pj, in_raster_srs)
        else:
            transform_coords_to_raster = None

        for vp in vp_array:
            if transform_coords_to_raster:
                vp.ox, vp.oy, _ = transform_coords_to_raster.TransformPoint(vp.ox, vp.oy)

            if backend is None:
                backend = default_ViewshedBackend
            elif isinstance(backend, str):
                backend = ViewshedBackend[backend]

            inter_process = (backend == ViewshedBackend.gdal) and not vp.is_omni_h()
            is_base_calc = True
            if backend == ViewshedBackend.gdal:
                # TypeError: '>' not supported between instances of 'NoneType' and 'int'
                is_temp_file = True
                d_path = tempfile.mktemp(suffix='.tif')

                bnd_type = gdal.GDT_Byte
                # todo: why dosn't it work without it?
                is_temp_file, gdal_out_format, d_path, return_ds = temp_params(True)

                inputs = vp.get_as_gdal_params()
                print(inputs)
                ds = gdal.ViewshedGenerate(input_band, gdal_out_format, str(d_path), co, **inputs)
                if not ds:
                    raise Exception('Viewshed calculation failed')
            elif backend == ViewshedBackend.talos:
                # is_temp_file = True  # output is file, not ds
                if not input_filename:
                    raise Exception('to use talos backend you need to provide an input filename')
                # if 'talosgis.talos' not in sys.modules:
                global talos
                if talos is None:
                    try:
                        from talosgis import get_talos_gdal_path
                        from talosgis import talos2 as talos
                        import talosgis_data.__data__
                        import gdalos_data.__data__
                    except ImportError:
                        raise Exception('failed to load talos backend')

                    print('gdalos Version ', gdalos_data.__data__.__version__)
                    print('talos Version ', talosgis_data.__data__.__version__)
                    print('GS_GetIntVersion ', talos.GS_GetIntVersion())
                    print('GS_GetDLLVersion ', talos.GS_GetDLLVersion())

                    gdal_path = get_talos_gdal_path()
                    # gdal_path = r'd:\OSGeo4W64-20200613\bin\gdal204.dll'
                    talos.GS_SetGDALPath(gdal_path)
                    # print('GS_GetGDALPath ', talos.GS_GetGDALPath())
                    print('GS_talosInit ', talos.GS_talosInit())

                    # print('GS_IsGDALLoaded ', talos.GS_IsGDALLoaded())
                    # print('GS_GetGDALPath ', talos.GS_GetGDALPath())

                    # print('GS_SetCacheSize ', talos.GS_SetCacheSize(cache_size_mb))

                dtm_open_err = talos.GS_DtmOpenDTM(str(input_filename))
                if dtm_open_err != 0:
                    raise Exception('talos could not open input file {}'.format(input_filename))
                talos.GS_SetRefractionCoeff(vp.refraction_coeff)
                inputs = vp.get_as_talos_params()
                ras = talos.GS_Viewshed_Calc1(**inputs)

                bnd_type = inputs['result_dt']
                is_base_calc = bnd_type in [gdal.GDT_Byte]
                do_color = color_table and (bnd_type not in [gdal.GDT_Byte, gdal.GDT_UInt16])

                is_temp_file, gdal_out_format, d_path, return_ds = temp_params(True)

                talos.GS_SaveRaster(ras, str(d_path))
                ras = None
                # I will reopen the ds to change the color table and ndv
                # ds = gdalos_util.open_ds(d_path, access_mode=gdal.OF_UPDATE)
                ds = gdal.OpenEx(str(d_path), gdal.OF_RASTER | gdal.OF_UPDATE)
            else:
                raise Exception('unknown backend {}'.format(backend))

            input_ds = None
            input_band = None

            set_nodata = backend == ViewshedBackend.gdal
            # set_nodata = is_base_calc
            bnd = ds.GetRasterBand(1)
            if set_nodata:
                base_calc_ndv = vp.ndv
                bnd.SetNoDataValue(base_calc_ndv)
            else:
                base_calc_ndv = bnd.GetNoDataValue()
            if color_table and not do_color:
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
                is_temp_file, gdal_out_format, d_path, return_ds = temp_params(False)

            if inter_process:
                ring = PolygonizeSector(vp.ox, vp.oy, vp.max_r, vp.max_r, vp.azimuth, vp.h_aperture)
                calc_cutline = tempfile.mktemp(suffix='.gpkg')
                temp_files.append(calc_cutline)
                create_layer_from_geometries([ring], calc_cutline)

                ds = gdalos_trans(ds, out_filename=d_path, #warp_CRS=pjstr_tgt_srs,
                                  cutline=calc_cutline, of=gdal_out_format, return_ds=return_ds, ovr_type=None)
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

    if combined_post_process_needed:
        ds = gdalos_trans(ds, out_filename=d_path, warp_CRS=pjstr_tgt_srs,
                          cutline=cutline, of=gdal_out_format, return_ds=return_ds, ovr_type=None)

        if return_ds:
            if not ds:
                raise Exception('error occurred')

    if do_color:
        ds, _pal = gdaldem_crop_and_color(ds, out_filename=d_path, color_palette=color_palette,
                                          color_mode=color_mode)
        if not ds:
            raise Exception('Viewshed calculation failed to color result')
        # steps -= 1

    if temp_files:
        for f in temp_files:
            try:
                os.remove(f)
            except:
                pass
                # probably this is a file that backs the ds that we'll return
                # print('failed to remove temp file:{}'.format(f))

    return ds


def test_calcz(inputs, raster_filename, input_ds):
    cwd = Path.cwd()
    backend = ViewshedBackend.talos
    for color_palette in [..., None]:
        prefix = 'calcz_color_' if color_palette else 'calcz_'
        output_path = dir_path / Path(prefix + str(backend))
        for calc in CalcOperation:
            # if calc != CalcOperation.viewshed:
            #     continue
            if color_palette is ...:
                color_palette = cwd / 'sample/color_files/gradient/{}.txt'.format('percentages')  #calc.name)
            if calc == CalcOperation.viewshed:
                # continue
                for i, vp in enumerate(inputs):
                    output_filename = output_path / Path('{}_{}.tif'.format(calc.name, i))
                    viewshed_calc(input_ds=input_ds, input_filename=raster_filename,
                                  output_filename=output_filename,
                                  vp_array=vp,
                                  backend=backend,
                                  operation=calc,
                                  color_palette=color_palette,
                                  files=files,
                                  )
            elif calc in [CalcOperation.max, CalcOperation.min]:
                output_filename = output_path / Path('{}.tif'.format(calc.name))
                viewshed_calc(input_ds=input_ds, input_filename=raster_filename,
                              output_filename=output_filename,
                              vp_array=inputs,
                              backend=backend,
                              operation=calc,
                              color_palette=color_palette,
                              files=files,
                              # vp_slice=slice(0, 2)
                              )


def test_simple_viewshed(inputs, raster_filename, input_ds, dir_path, files=None, run_comb_with_post=False):
    calc_filter = CalcOperation
    calc_filter = [CalcOperation.count_z]
    cwd = Path.cwd()
    for backend in reversed(ViewshedBackend):
        output_path = dir_path / Path('comb_' + str(backend))
        for calc in calc_filter:
            color_palette = cwd / 'sample/color_files/viewshed/{}.txt'.format(calc.name)
            if calc == CalcOperation.viewshed:
                for i, vp in enumerate(inputs):
                    output_filename = output_path / Path('{}_{}.tif'.format(calc.name, i))
                    viewshed_calc(input_ds=input_ds, input_filename=raster_filename,
                                  output_filename=output_filename,
                                  vp_array=vp,
                                  backend=backend,
                                  operation=calc,
                                  color_palette=color_palette,
                                  files=files,
                                  )
            else:
                output_filename = output_path / Path('{}.tif'.format(calc.name))
                try:
                    viewshed_calc(input_ds=input_ds, input_filename=raster_filename,
                                  output_filename=output_filename,
                                  vp_array=inputs,
                                  backend=backend,
                                  operation=calc,
                                  color_palette=color_palette,
                                  files=files,
                                  # vp_slice=slice(0, 2)
                                  )
                except:
                    print('failed to run viewshed calc with backend: {}, inputs: {}'.format(backend, inputs))

        if run_comb_with_post:
            output_filename = output_path / 'combine_post.tif'
            cutline = cwd / r'sample/shp/comb_poly.gml'
            viewshed_calc(input_ds=input_ds, input_filename=raster_filename,
                          output_filename=output_filename,
                          vp_array=inputs,
                          backend=backend,
                          operation=CalcOperation.count,
                          color_palette=color_palette,
                          cutline=cutline,
                          out_crs=0,
                          files=files)


if __name__ == "__main__":
    # dir_path = Path('/home/idan/maps')
    dir_path = Path(r'd:\dev\gis\maps')
    raster_filename = Path(dir_path) / Path('srtm1_36_sample.tif')
    input_ds = ds = gdalos_util.open_ds(raster_filename)

    vp = ViewshedGridParams()
    inputs = vp.get_array()

    use_input_files = False
    if use_input_files:
        files_path = Path('/home/idan/maps/grid_comb/viewshed')
        files = glob.glob(str(files_path / '*.tif'))
    else:
        files = None

    # if True:
    #     vp1 = copy.copy(vp)
    #     vp1.tz = None
    #     inputs = vp1.get_array()
    #     test_calcz(inputs=inputs, raster_filename=raster_filename, input_ds=input_ds)
    if True:
        inputs = vp.get_array()
        test_simple_viewshed(inputs=inputs, run_comb_with_post=False, files=files,
                             dir_path=dir_path, raster_filename=raster_filename, input_ds=input_ds)
