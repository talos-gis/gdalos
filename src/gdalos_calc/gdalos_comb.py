import os
import glob
import gdal
import tempfile
from pathlib import Path
from gdalos import gdal_helper, get_extent, GeoRectangle
from gdalos_calc.gdal_calc import Calc, AlphaList
from gdalos_calc.gdalos_color import ColorPalette


def do_comb(filenames, alpha_pattern, operand='+', **kwargs):
    calc = None
    for filename, alpha in zip(filenames, AlphaList):
        kwargs[alpha] = filename
        alpha1 = alpha_pattern.format(alpha)
        # alpha1 = alpha
        if calc is None:
            calc = alpha1
        else:
            calc = '{}{}{}'.format(calc, operand, alpha1)
    Calc(calc, **kwargs)


def make_verts(filenames, isUnion):
    # extents = []
    dss = []
    c_extent = None
    for filename in filenames:
        ds = gdal_helper.open_ds(filename)
        org_points_extent, _ = get_extent.get_points_extent_from_ds(ds)
        extent = GeoRectangle.from_points(org_points_extent)

        dss.append(ds)
        # extents.append(extent)
        c_extent = extent if c_extent is None else c_extent.union(extent) if isUnion else c_extent.intersect(extent)

    suffix = '_u.vrt' if isUnion else '_i.vrt'
    vrt_filenames = build_vrts(filenames, dss, c_extent, suffix)
    return vrt_filenames, c_extent


# def combine(filenames, outpath, alpha_pattern, **kwargs):
#     extents = []
#     dss = []
#     union_extent = None
#     intersect_extent = None
#     for filename in filenames:
#         ds = gdal_helper.open_ds(filename)
#         org_points_extent, _ = get_extent.get_points_extent_from_ds(ds)
#         extent = GeoRectangle.from_points(org_points_extent)
#
#         dss.append(ds)
#         extents.append(extent)
#         if union_extent is None:
#             union_extent = extent
#             intersect_extent = extent
#         else:
#             intersect_extent = intersect_extent.intersect(extent)
#             union_extent = union_extent.union(extent)
#
#     vrt_filenames = build_vrts(filenames, dss, union_extent, '_u.vrt')
#     outfile = tempfile.mktemp(suffix='_union_combine.tif', dir=str(outpath))
#     # outfile = outpath / suffix
#     do_comb(vrt_filenames, alpha_pattern, outfile=outfile, **kwargs)
#
#     vrt_filenames = build_vrts(filenames, dss, intersect_extent, '_i.vrt')
#     outfile = tempfile.mktemp(suffix='_intersect_combine.tif', dir=str(outpath))
#     # outfile = outpath / suffix
#     do_comb(vrt_filenames, alpha_pattern, outfile=outfile, **kwargs)
#     return extents


def build_vrts(filenames, dss, extent: GeoRectangle, suffix):
    vrt_filenames = []
    for filename, ds in zip(filenames, dss):
        options = gdal.BuildVRTOptions(outputBounds=(extent.min_x, extent.min_y, extent.max_x, extent.max_y))
                                       # hideNodata=True,
                                       # separate=False)
        out_vrt = filename + suffix
        vrt_filenames.append(out_vrt)
        out_ds = gdal.BuildVRT(out_vrt, ds, options=options)
        if out_ds is None:
            return None
        del out_ds
    return vrt_filenames


if __name__ == '__main__':
    path = Path(r'../../sample')
    color_filename = path / Path(r'color_files/comb.qlr')
    pal = ColorPalette()
    pal.read(color_filename)
    pal.write_color_file(color_filename.with_suffix('.txt'))
    color_table = pal.get_color_table()
    alpha_pattern = '1*({}>3)'

    path = Path('/home/idan/maps/comb/vs')
    outpath = path / 'comb'
    pattern = Path('*.tif')
    os.makedirs(str(outpath), exist_ok=True)
    dirpath = path / pattern
    filenames = list(glob.glob(str(dirpath)))
    print(filenames)

    for geotransforms in [2, 3]:
        for method in [1, 2]:
            isUnion = geotransforms == 2
            outfile = tempfile.mktemp(suffix='_{}{}.tif'.format('u' if isUnion else 'i', method), dir=str(outpath))
            kwargs = dict()
            if method == 1:
                vrt_filenames, c_extent = make_verts(filenames, isUnion)
                kwargs['filenames'] = vrt_filenames
            else:
                kwargs['filenames'] = filenames
                kwargs['geotransforms'] = geotransforms

            do_comb(alpha_pattern=alpha_pattern, outfile=outfile, color_table=color_table, hideNodata=True, **kwargs)

