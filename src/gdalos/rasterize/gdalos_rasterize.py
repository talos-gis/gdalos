from numbers import Real
from osgeo import gdal
from gdalos.gdalos_trans import gdalos_trans, GeoRectangle, gdalos_extent, gdalos_util, projdef
from pathlib import Path

# https://www.programcreek.com/python/example/101827/gdal.RasterizeLayer
# https://trac.osgeo.org/gdal/ticket/5581
# https://github.com/OSGeo/gdal/blob/master/gdal/apps/gdal_rasterize_lib.cpp


def gdalos_rasterize(
        in_filename: str, shp_filename_or_ds: str,
        out_filename: str = None, shp_layer_name: str = None, shp_z_attribute: str = 'Height',
        add: bool = True, extent: GeoRectangle = ..., **kwargs):

    """rasterize a vector layer into a given raster layer, overriding or adding the values

    Parameters
    ----------
    in_filename:str
        input raster filename
    out_filename:str
        ouput raster filename, if None - input raster would be updated inplace
    shp_filename_or_ds: str
        input vector filename or dataset
    shp_layer_name: str
        name of the layer from the vector dataset to use
    shp_z_attribute: str='Height'
        name of the attribute to extract the z value from
    add: bool=True
        True to add to dtm values to shape values into the raster, False to burn shape values into the raster
    extent: GeoRectangle = ...
        None - use the extent of the input raster
        ... - use the extent of the input vector layer
        GeoRectangle - custom extent
    out_res: Real
        output resolution (if None then auto select)
    warp_srs: str=None
        output srs
    overwrite: bool=True
        what to do if the output exists (fail of overwrite)

    Returns
    -------
        output raster dataset
    """

    # shp = gdalos_util.open_ds(shp_filename, gdal.gdalconst.OF_VECTOR)
    if shp_filename_or_ds is None:
        shp = None
    elif isinstance(shp_filename_or_ds, (str, Path)):
        shp = gdal.OpenEx(str(shp_filename_or_ds), gdal.gdalconst.OF_VECTOR)
    else:
        shp = shp_filename_or_ds

    if out_filename is None:
        dstDs = gdalos_util.open_ds(in_filename, gdal.GA_Update)
    else:
        pj4326 = projdef.get_srs_pj(4326)
        if extent is ...:
            cov_pj_srs = projdef.get_srs_pj(shp)
            if not cov_pj_srs:
                cov_pj_srs = pj4326
            cov_extent = ogr_get_layer_extent(shp.GetLayer())
            transform = projdef.get_transform(cov_pj_srs, pj4326)
            extent = gdalos_extent.transform_extent(cov_extent, transform)

        dstDs = gdalos_trans(in_filename, out_filename, extent=extent,
                             cog=False, ovr_type=None, return_ds=True, **kwargs)

    if shp is not None:
        rasteize_options = gdal.RasterizeOptions(
            layers=shp_layer_name, add=add, attribute=shp_z_attribute)
        ret = gdal.Rasterize(dstDs, shp, options=rasteize_options)
        if ret != 1:
            raise Exception('Rasterize failed')

    return dstDs


if __name__ == '__main__':
    out_dir = Path(r'd:\temp\rasterize')
    my_out_filename = out_dir / 'output.tif'
    cov_filename = out_dir / Path('ras_cov.gpkg')

    my_out_srs = projdef.get_proj_string(36)
    out_res = 10
    do_overwrite = True
    do_cog = True
    do_add = False
    do_shp = True
    do_inplace = False

    if do_shp:
        shp_filename_or_ds = cov_filename
        out_extent = ...
    else:
        shp_filename_or_ds = None
        out_extent = GeoRectangle.from_min_max(34.0, 34.2, 32.0, 32.2)

    if do_inplace:
        input_raster = out_dir / 'input.tif'
        out_filename = None
    else:
        input_raster = Path(r'd:\Maps\w84geo\dtm\SRTM1_hgt.tif.x20-80_y20-40.cog.tif')
        out_filename = my_out_filename

    dstDs = gdalos_rasterize(
        input_raster,
        shp_filename_or_ds=shp_filename_or_ds, out_filename=out_filename,
        add=do_add, extent=out_extent,
        warp_srs=my_out_srs, out_res=out_res, overwrite=do_overwrite)

    if do_cog:
        if out_filename is None:
            out_filename = my_out_filename
        gdalos_trans(dstDs, out_filename=str(out_filename) + '.cog.tif', overwrite=do_overwrite)

    del dstDs
    print('done!')
