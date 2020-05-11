import os
import glob
import gdal
import tempfile
from pathlib import Path
from gdalos import gdal_helper, get_extent, GeoRectangle
from gdalos_calc.gdal_calc import Calc, AlphaList
from gdalos_calc.gdalos_color import ColorPalette


def do_comb(filenames, outfile, extent, color_table, alpha_pattern):
    kwargs = dict()
    calc = None
    for filename, alpha in zip(filenames, AlphaList):
        kwargs[alpha] = filename
        alpha1 = alpha_pattern.format(alpha)
        # alpha1 = alpha
        if calc is None:
            calc = alpha1
        else:
            calc = '{}+{}'.format(calc, alpha1)
        # break
    Calc(calc, extent=extent, color_table=color_table, outfile=str(outfile), **kwargs)
    # Calc("A+B", A="input1.tif", B="input2.tif", outfile="result.tif")


def combine(dirpath, outpath, color_table, alpha_pattern):
    extents = []
    filenames = []
    dss = []
    union_extent = None
    intersect_extent = None
    for filename in glob.glob(str(dirpath)):
        ds = gdal_helper.open_ds(filename)
        org_points_extent, _ = get_extent.get_points_extent_from_ds(ds)
        extent = GeoRectangle.from_points(org_points_extent)

        filenames.append(filename)
        dss.append(ds)
        extents.append(extent)
        if union_extent is None:
            union_extent = extent
            intersect_extent = extent
        else:
            intersect_extent = intersect_extent.intersect(extent)
            union_extent = union_extent.union(extent)

    extent = None
    vrt_filenames = build_vrts(filenames, dss, union_extent, '_u.vrt')
    outfile = tempfile.mktemp(suffix='_union_combine.tif', dir=str(outpath))
    # outfile = outpath / suffix
    do_comb(vrt_filenames, outfile, extent, color_table, alpha_pattern)

    vrt_filenames = build_vrts(filenames, dss, intersect_extent, '_i.vrt')
    outfile = tempfile.mktemp(suffix='_intersect_combine.tif', dir=str(outpath))
    # outfile = outpath / suffix
    do_comb(vrt_filenames, outfile, extent, color_table, alpha_pattern)
    return filenames, extents


def build_vrts(filenames, dss, extent: GeoRectangle, suffix):
    vrt_filenames = []
    for filename, ds in zip(filenames, dss):
        options = gdal.BuildVRTOptions(outputBounds=(extent.min_x, extent.min_y, extent.max_x, extent.max_y),
                                       hideNodata=True,
                                       separate=False)
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

    # path = Path(r'd:\dev\TaLoS\data\6comb\1')
    outpath = path / 'comb'
    pattern = Path('*.tif')
    os.makedirs(str(outpath), exist_ok=True)
    dirpath = path / pattern
    filenames, extents = combine(dirpath, outpath, color_table, alpha_pattern)

    print(filenames)
    print(extents)
