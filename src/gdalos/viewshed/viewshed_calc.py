import gdal, osr, ogr
import glob
import tempfile
import os
import time
from pathlib import Path
from enum import Enum
from gdalos import projdef, gdalos_util, gdalos_color, gdalos_trans
from gdalos.calc import gdal_calc, gdal_to_czml, dict_util, gdalos_combine
from gdalos.viewshed import viewshed_params
from gdalos.viewshed.viewshed_grid_params import ViewshedGridParams
from gdalos.talos.ogr_util import create_layer_from_geometries
from gdalos.talos.geom_arc import PolygonizeSector


class CalcOperation(Enum):
    viewshed = 0
    max = 1
    count = 2
    count_z = 3
    unique = 4


def tempthing(use_temp_tif, steps, output_filename):
    is_temp_file = (use_temp_tif and steps > 1)
    gdal_out_format = 'GTiff' if steps == 1 or use_temp_tif else 'MEM'
    d_path = tempfile.mktemp(
        suffix='.tif') if is_temp_file else output_filename if gdal_out_format != 'MEM' else ''
    return_ds = not is_temp_file
    return is_temp_file, gdal_out_format, d_path, return_ds


def viewshed_calc(input_ds,
                  output_filename,
                  vp_array, extent=2, cutline=None, operation: CalcOperation = CalcOperation.count,
                  in_coords_crs_pj=None, out_crs=None,
                  color_palette=None,
                  bi=1, co=None, of='GTiff',
                  input_slice_from=None, input_slice_to=None,
                  files=[]):
    ext = gdalos_util.get_ext_by_of(of)
    is_czml = ext == '.czml'
    color_table = gdalos_color.get_color_table(color_palette)
    # steps:
    # 1. viewshed
    # 2. calc + calc_post_process
    # 3. combined_post_process
    # 4. czml
    steps = 1
    if operation == CalcOperation.viewshed:
        operation = None
    if operation:
        steps += 1
    if is_czml:
        out_crs = 0  # czml supprts only 4326
        steps += 1
    temp_files = []

    combined_post_process_needed = False

    if not files:
        files = []
    else:
        files = files.copy()

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
        if combined_post_process_needed:
            steps += 1

    if not files:
        vp_array = ViewshedGridParams.get_list_from_lists_dict(vp_array)
        vp_array = vp_array[input_slice_from:input_slice_to]

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
            inter_process = not vp.is_omni_h()
            if inter_process:
                steps += 1

            # TypeError: '>' not supported between instances of 'NoneType' and 'int'
            # todo: why dosn't it work without it?
            is_temp_file, gdal_out_format, d_path, return_ds = tempthing(True, steps, output_filename)

            inputs = vp.get_as_gdal_params()
            ds = gdal.ViewshedGenerate(input_band, gdal_out_format, str(d_path), co, **inputs)

            if not ds:
                raise Exception('Viewshed calculation failed')

            src_band = ds.GetRasterBand(1)
            src_band.SetNoDataValue(vp.ndv)
            if color_table and not operation:
                src_band.SetRasterColorTable(color_table)
                src_band.SetRasterColorInterpretation(gdal.GCI_PaletteIndex)
            src_band = None

            if is_temp_file:
                # close original ds and reopen
                ds = None
                ds = gdalos_util.open_ds(d_path)
                temp_files.append(d_path)

            if inter_process:
                ring = PolygonizeSector(vp.ox, vp.oy, vp.max_r, vp.max_r, vp.azimuth, vp.h_aperture)
                calc_cutline = tempfile.mktemp(suffix='.gpkg')
                temp_files.append(calc_cutline)
                create_layer_from_geometries([ring], calc_cutline)

                is_temp_file, gdal_out_format, d_path, return_ds = tempthing(True, steps, output_filename)

                ds = gdalos_trans(ds, out_filename=d_path, #warp_CRS=pjstr_tgt_srs,
                                  cutline=calc_cutline, of=gdal_out_format, return_ds=return_ds, ovr_type=None)

                if is_temp_file:
                    # close original ds and reopen
                    ds = None
                    ds = gdalos_util.open_ds(d_path)
                    temp_files.append(d_path)
                if not ds:
                    raise Exception('Viewshed calculation failed to cut')

                steps -= 1

            if operation:
                files.append(ds)

        input_ds = None
        input_band = None

    steps -= 1
    if operation:
        # alpha_pattern = '1*({{}}>{})'.format(viewshed_thresh)
        # alpha_pattern = 'np.multiply({{}}>{}, dtype=np.uint8)'.format(viewshed_thresh)
        if operation == CalcOperation.viewshed:
            no_data_value = viewshed_params.viewshed_ndv
            f = gdalos_combine.get_by_index
            # calc_expr, calc_kwargs, f = gdal_calc.make_calc_with_func(files, alpha_pattern, 'f'), sum
        elif operation == CalcOperation.max:
            no_data_value = viewshed_params.viewshed_ndv
            f = gdalos_combine.vs_max
            # calc_expr, calc_kwargs, f = gdal_calc.make_calc_with_func(files, alpha_pattern, 'f'), sum
        elif operation == CalcOperation.count:
            no_data_value = 0
            f = gdalos_combine.vs_count
            # calc_expr, calc_kwargs = gdal_calc.make_calc_with_operand(files, alpha_pattern, '+')
            # calc_expr, calc_kwargs, f = gdal_calc.make_calc_with_func(files, alpha_pattern), sum
        elif operation == CalcOperation.count_z:
            no_data_value = viewshed_params.viewshed_comb_ndv
            f = gdalos_combine.vs_count_z
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

        is_temp_file, gdal_out_format, d_path, return_ds = tempthing(False, steps, output_filename)

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
        elif steps > 1:
            ds = gdalos_util.open_ds(d_path)
        for i in range(len(files)):
            files[i] = None  # close calc input ds(s)
        steps -= 1

    if combined_post_process_needed:
        is_temp_file, gdal_out_format, d_path, return_ds = tempthing(False, steps, output_filename)
        ds = gdalos_trans(ds, out_filename=d_path, warp_CRS=pjstr_tgt_srs,
                          cutline=cutline, of=gdal_out_format, return_ds=return_ds, ovr_type=None)

        if return_ds:
            if not ds:
                raise Exception('error occurred')
        elif steps>1:
            ds = gdalos_util.open_ds(d_path)

        steps -= 1

    if is_czml and ds is not None:
        gdal_to_czml.gdal_to_czml(ds, name=output_filename, out_filename=output_filename)

    ds = None  # close ds

    if temp_files:
        for f in temp_files:
            try:
                os.remove(f)
            except:
                print('failed to remove temp file:{}'.format(f))

    return True


if __name__ == "__main__":
    dir_path = Path('/home/idan/maps')
    output_path = dir_path / Path('comb')
    raster_filename = Path(output_path) / Path('srtm1_36_sample.tif')
    input_ds = ds = gdalos_util.open_ds(raster_filename)

    vp = ViewshedGridParams()

    inputs = vp.get_as_gdal_params_array()

    use_input_files = False
    run_comb_with_post = False

    if use_input_files:
        files_path = Path('/home/idan/maps/grid_comb/viewshed')
        files = glob.glob(str(files_path / '*.tif'))
    else:
        files = []
    for calc in CalcOperation:
        # if calc != CalcOperation.viewshed:
        #     continue
        color_palette = './sample/color_files/viewshed/{}.txt'.format(calc.name)
        if calc == CalcOperation.viewshed:
            input_size = max(len(x) for x in inputs.values())
            for i in range(input_size):
                output_filename = output_path / Path('{}_{}.tif'.format(calc.name, i))
                viewshed_calc(input_ds,
                              output_filename,
                              inputs,
                              operation=calc,
                              color_palette=color_palette,
                              files=files,
                              input_slice_from=i, input_slice_to=i+1
                              )
        else:
            output_filename = output_path / Path('{}.tif'.format(calc.name))
            viewshed_calc(input_ds,
                          output_filename,
                          inputs,
                          operation=calc,
                          color_palette=color_palette,
                          files=files,
                          # input_slice_from=0, input_slice_to=2
                          )

    if run_comb_with_post:
        output_filename = output_path / 'combine_post.tif'
        cutline = r'sample/shp/comb_poly.gml'
        viewshed_calc(input_ds,
                      output_filename,
                      inputs,
                      operation=CalcOperation.count,
                      color_palette=color_palette,
                      cutline=cutline,
                      out_crs=0,
                      files=files)
