import gdal, osr
import glob
import tempfile
import os
import numpy as np
from pathlib import Path
from gdalos import projdef, gdalos_util, gdalos_color, gdalos_trans
from gdalos.calc import gdal_calc, gdal_to_czml, dict_util
from gdalos.viewshed import viewshed_consts, viewshed_params
from gdalos.viewshed.viewshed_consts import viewshed_defaults


def unique(arrs, multiple_nz=254, all_zero=255):
    arrs = [np.array(a) for a in arrs]
    concatenate = np.stack(arrs)
    nz_count = np.count_nonzero(concatenate, 0)
    ret = np.full_like(arrs[0], all_zero)
    ret[nz_count > 1] = multiple_nz
    singular = nz_count == 1
    for i, arr in enumerate(arrs):
        ret[(arr != 0) & singular] = i
    return ret


def viewshed_calc(input_ds,
                  output_filename,
                  arrays_dict, extent=2, cutline=None, operation=1,
                  in_coords_crs_pj=None, out_crs=None,
                  color_palette=None,
                  bi=1, co=None, of='GTiff',
                  files=[]):
    ext = gdalos_util.get_ext_by_of(of)
    is_czml = ext == '.czml'
    color_table = gdalos_color.get_color_table(color_palette)
    # steps:
    # 1. viewshed
    # 2. calc
    # 3. post process
    # 4. czml
    steps = 1
    if operation:
        steps += 1
    if is_czml:
        steps += 1
    temp_files = []

    post_process_needed = False
    if input_ds is None:
        if not files:
            raise Exception('ds is None')
    else:
        input_band: gdal.Band = input_ds.GetRasterBand(bi)
        if input_band is None:
            raise Exception('band number out of range')

        pjstr_src_srs = projdef.get_srs_pj_from_ds(input_ds)
        pjstr_tgt_srs = projdef.get_proj_string(out_crs) if out_crs is not None else pjstr_src_srs
        post_process_needed = cutline or not projdef.proj_is_equivalent(pjstr_src_srs, pjstr_tgt_srs)
        if post_process_needed:
            steps += 1

    if not files:
        use_temp_tif = True  # todo: why dosn't it work without it?
        # TypeError: '>' not supported between instances of 'NoneType' and 'int'

        # gdal_out_format = 'GTiff' if use_temp_tif or (output_tif and not operation) else 'MEM'
        # gdal_out_format = 'GTiff' if steps == 1 else 'MEM'

        params = 'md', 'ox', 'oy', 'oz', 'tz', \
                 'vv', 'iv', 'ov', 'ndv', \
                 'cc', 'mode'

        new_keys = \
            'maxDistance', 'observerX', 'observerY', 'observerHeight', 'targetHeight', \
            'visibleVal', 'invisibleVal', 'outOfRangeVal', 'noDataVal', \
            'dfCurvCoeff', 'mode'
        key_map = dict(zip(params, new_keys))
        arrays_dict = dict_util.make_dicts_list_from_lists_dict(arrays_dict, key_map)
        if operation:
            # restore viewshed consts default values
            my_viewshed_defaults = dict_util.replace_keys(viewshed_defaults, key_map)
            for a in arrays_dict:
                a.update(my_viewshed_defaults)
        else:
            arrays_dict = arrays_dict[0:1]

        max_rasters_count = 1000 if operation == 1 else 254 if operation == 2 else 1
        if len(arrays_dict) > max_rasters_count:
            arrays_dict = arrays_dict[0:max_rasters_count]

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

        gdal_out_format = 'GTiff' if steps == 1 or use_temp_tif else 'MEM'
        for vp in arrays_dict:
            if transform_coords_to_raster:
                vp['observerX'], vp['observerY'], _ = transform_coords_to_raster.TransformPoint(vp['observerX'],
                                                                                                vp['observerY'])
            d_path = tempfile.mktemp(
                suffix='.tif') if (use_temp_tif and steps>1) else output_filename if gdal_out_format != 'MEM' else ''
            ds = gdal.ViewshedGenerate(input_band, gdal_out_format, str(d_path), co, **vp)

            if not ds:
                raise Exception('Viewshed calculation failed')

            src_band = ds.GetRasterBand(1)
            src_band.SetNoDataValue(vp['noDataVal'])

            if operation:
                if use_temp_tif:
                    temp_files.append(d_path)
                    files.append(d_path)
                    ds = None
                else:
                    files.append(ds)
            else:
                if color_table:
                    src_band.SetRasterColorTable(color_table)
                    src_band.SetRasterColorInterpretation(gdal.GCI_PaletteIndex)
            src_band = None

        input_ds = None
        input_band = None

    steps -= 1
    if operation:
        cutoff_value = viewshed_defaults['iv']
        alpha_pattern = '1*({{}}>{})'.format(cutoff_value)
        if operation == 1:
            old_sum = False
            if old_sum:
                calc, kwargs = gdal_calc.make_calc_with_operand(files, alpha_pattern, '+')
            else:
                calc, kwargs = gdal_calc.make_calc_with_func(files, alpha_pattern, 'sum')
        elif operation == 2:
            calc, kwargs = gdal_calc.make_calc_with_func(files, alpha_pattern, 'f', f=unique)
        else:
            raise Exception('Unknown operation: {}'.format(operation))

        hide_nodata = True
        use_temp_tif = False
        # gdal_out_format = 'GTiff' if steps == 1 or use_temp_tif else 'MEM'
        # d_path = tempfile.mktemp(
        #     suffix='.tif') if use_temp_tif else tif_output_filename if gdal_out_format != 'MEM' else ''

        # gdal_out_format = 'MEM' if is_czml else 'GTiff'
        # d_path = output_filename

        gdal_out_format = 'GTiff' if steps == 1 or use_temp_tif else 'MEM'
        d_path = tempfile.mktemp(
            suffix='.tif') if (use_temp_tif and steps > 1) else output_filename if gdal_out_format != 'MEM' else ''

        # return_ds = gdal_out_format == 'MEM'
        return_ds = True
        ds = gdal_calc.Calc(
            calc, outfile=str(d_path), extent=extent, cutline=cutline, format=gdal_out_format,
            color_table=color_table, hideNodata=hide_nodata, return_ds=return_ds, overwrite=True, **kwargs)
        if return_ds:
            if not ds:
                raise Exception('error occurred')
        elif steps > 1:
            ds = gdalos_util.open_ds(d_path)
        for i in range(len(files)):
            files[i] = None  # close calc input ds(s)
        steps -= 1

    if post_process_needed:
        # gdal_out_format = 'GTiff' if steps == 1 else 'MEM'
        use_temp_tif = False
        gdal_out_format = 'GTiff' if steps == 1 or use_temp_tif else 'MEM'
        d_path = tempfile.mktemp(
            suffix='.tif') if (use_temp_tif and steps > 1) else output_filename if gdal_out_format != 'MEM' else ''

        return_ds = True
        ds = gdalos_trans(ds, out_filename=d_path, warp_CRS=pjstr_tgt_srs,
                          cutline=cutline, of=gdal_out_format, return_ds=return_ds, ovr_type=None, write_spec=False)

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
            os.remove(f)

    return True


if __name__ == "__main__":
    dir_path = Path('/home/idan/maps')
    output_path = dir_path / Path('comb')
    raster_filename = Path(output_path) / Path('srtm1_36_sample.tif')
    color_palette = './sample/color_files/comb.txt'
    input_ds = ds = gdalos_util.open_ds(raster_filename)

    vp = viewshed_params.get_test_viewshed_params()

    oxs = []
    oys = []
    j = 1
    grid_range = range(-j, j + 1)
    for i in grid_range:
        for j in grid_range:
            ox = vp.center[0] + i * vp.interval
            oy = vp.center[1] + j * vp.interval
            oxs.append(ox)
            oys.append(oy)

    inputs = dict()
    inputs['md'] = [vp.md]
    inputs['ox'] = oxs
    inputs['oy'] = oys
    inputs['oz'] = [vp.oz]
    inputs['tz'] = [vp.tz]
    inputs['vv'] = [viewshed_consts.st_seen]
    inputs['iv'] = [viewshed_consts.st_hidden]
    inputs['ov'] = [viewshed_consts.st_nodata]
    inputs['ndv'] = [viewshed_consts.st_nodtm]
    inputs['cc'] = [viewshed_consts.cc_atmospheric_refraction]
    inputs['mode'] = [2]

    use_input_files = False
    run_single = False
    run_comb = False
    run_comb_with_post = True

    if use_input_files:
        files_path = Path('/home/idan/maps/grid_comb/viewshed')
        files = glob.glob(str(files_path / '*.tif'))
    else:
        files = []

    if run_single:
        output_filename = output_path / 'single.tif'
        viewshed_calc(input_ds,
                      output_filename,
                      inputs,
                      operation=0,
                      color_palette=color_palette,
                      files=files)

    if run_comb:
        output_filename = output_path / 'combine.tif'
        viewshed_calc(input_ds,
                      output_filename,
                      inputs,
                      operation=1,
                      color_palette=color_palette,
                      files=files)

    if run_comb_with_post:
        output_filename = output_path / 'combine_post.tif'
        cutline = r'sample/shp/comb_poly.gml'
        viewshed_calc(input_ds,
                      output_filename,
                      inputs,
                      operation=1,
                      color_palette=color_palette,
                      cutline=cutline,
                      out_crs=0,
                      files=files)
