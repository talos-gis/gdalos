from typing import Sequence

from osgeo import gdal
from gdalos import projdef, gdalos_extent
from gdalos.rectangle import GeoRectangle, gt_and_size_from_rect
from gdalos.gdalos_util import get_creation_options, GetOutputDriverFor


def create_empty_raster(filename,
                        size, gt=None, srs=None,
                        of=None, dt=gdal.GDT_Float32,
                        bands=1, val=0, ndv=0,
                        creation_options=None):
    filename = str(filename)
    creation_options = creation_options or []

    if of is None:
        of = GetOutputDriverFor(filename)
    drv = gdal.GetDriverByName(of)
    ds = drv.Create(
        filename, size[0], size[1], bands,
        dt, creation_options)
    if gt:
        ds.SetGeoTransform(gt)
    if srs:
        ds.SetProjection(srs)
    if not isinstance(val, Sequence):
        val = [val]
    if not isinstance(ndv, Sequence):
        ndv = [ndv]
    for b, v, nv in zip(range(bands), val, ndv):
        bnd = ds.GetRasterBand(b+1)
        if nv:
            bnd.SetNoDataValue(nv)
        if v:
            bnd.Fill(v)
    return ds


def create_empty_raster_by_extent(pixel_size, srs, extent: GeoRectangle, extent_srs=None, **kwargs):
    srs, _tgt_zone = projdef.parse_proj_string_and_zone(srs)

    if extent_srs is not None:
        extent_srs = projdef.get_proj_string(extent_srs)  # 'EPSG:4326'
        transform = projdef.get_transform(extent_srs, srs)
        extent = gdalos_extent.translate_extent(extent, transform)

    size, gt = gt_and_size_from_rect(extent, pixel_size=pixel_size)
    create_empty_raster(size=size, gt=gt, srs=srs, **kwargs)


def test():
    o_extent = GeoRectangle.from_min_max(35, 36, 31, 32)
    o_srs = 36
    o_extent_srs = 0
    o_val = 0
    o_ndv = None
    o_res = (20, -20)
    o_filename = r'd:\temp\x.tif'
    creation_opt = get_creation_options()
    create_empty_raster_by_extent(
        filename=o_filename, pixel_size=o_res, srs=o_srs, extent=o_extent, extent_srs=o_extent_srs,
        val=o_val, ndv=o_ndv, creation_options=creation_opt)


if __name__ == '__main__':
    test()
