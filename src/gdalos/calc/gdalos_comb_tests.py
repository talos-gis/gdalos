import os
import glob
import gdal
import tempfile
from pathlib import Path
from gdalos import gdalos_util, gdalos_extent, GeoRectangle
from gdalos.calc import gdal_calc
from gdalos.gdalos_color import ColorPalette
from gdalos.calc.gdalcompare import compare
from gdalos.calc import gdalos_combine


def do_comb(filenames, alpha_pattern, operand='+', **kwargs):
    calc, kwargs = gdalos_combine.make_calc_with_operand(filenames, alpha_pattern, operand, **kwargs)
    gdal_calc.Calc(calc, **kwargs)


def make_verts(filenames, isUnion):
    # extents = []
    dss = []
    res_extent = None
    for filename in filenames:
        ds = gdalos_util.open_ds(filename)
        extent = gdalos_extent.get_extent(ds)

        dss.append(ds)
        # extents.append(extent)
        res_extent = extent if res_extent is None else res_extent.union(extent) if isUnion else res_extent.intersect(extent)

    suffix = '_u.vrt' if isUnion else '_i.vrt'
    vrt_filenames = build_vrts(filenames, dss, res_extent, suffix)
    return vrt_filenames, res_extent


# def combine(filenames, outpath, alpha_pattern, **kwargs):
#     extents = []
#     dss = []
#     union_extent = None
#     intersect_extent = None
#     for filename in filenames:
#         ds = gdalos_util.open_ds(filename)
#         extent = gdalos_extent.get_extent(ds)
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
        # vrt_filename = filename + suffix
        vrt_filename = tempfile.mktemp(suffix='.vrt')
        vrt_filenames.append(vrt_filename)
        vrt_ds = gdal.BuildVRT(vrt_filename, ds, options=options)
        if vrt_ds is None:
            return None
        del vrt_ds
    return vrt_filenames


def compare_rasters(pattern):
    golden = None
    total = 0
    for filename in glob.glob(str(pattern)):
        if golden is None:
            golden = filename
        else:
            print('{} vs {}'.format(golden, filename))
            res = compare(golden, filename)
            print(res)
            total += res
    print('total: {}'.format(total))
    return total


def combine_all(path, outpath):
    pattern = Path('*.tif')
    os.makedirs(str(outpath), exist_ok=True)
    dirpath = path / pattern
    filenames = list(glob.glob(str(dirpath)))
    print(filenames)

    custom_extent = GeoRectangle.from_lrud(698386, 700147, 3552332, 3550964)
    for extent in [2, 3, custom_extent]:
        for method in [1, 2]:
            isUnion = extent == 2
            isIntersection = extent == 3
            outfile = tempfile.mktemp(suffix='_{}{}.tif'.format(
                'u' if isUnion else 'i' if isIntersection else 'c', method), dir=str(outpath))
            kwargs = dict()
            if method == 1:
                kwargs['filenames'] = filenames
                kwargs['extent'] = extent
            else:
                if not isUnion and not isIntersection:
                    continue
                vrt_filenames, c_extent = make_verts(filenames, isUnion)
                kwargs['filenames'] = vrt_filenames

            do_comb(alpha_pattern=alpha_pattern, outfile=outfile, color_table=color_table, hideNodata=True, **kwargs)


if __name__ == '__main__':
    path = Path(r'sample')
    color_filename = path / Path(r'color_files/viewshed/sum.qlr')
    pal = ColorPalette()
    pal.read(color_filename)
    pal.write_color_file(color_filename.with_suffix('.txt'))
    color_table = pal.get_color_table()
    alpha_pattern = '1*({}>3)'

    path = Path('/home/idan/maps/comb/vs')
    outpath = path / 'comb'

    combine_all(path, outpath)
    total = compare_rasters(outpath / '*_u*') + \
        compare_rasters(outpath / '*_i*') + \
        compare_rasters(outpath / '*_c*')
    print('grand total: {}'.format(total))
