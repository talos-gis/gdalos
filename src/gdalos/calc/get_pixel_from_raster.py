#http://geoinformaticstutorial.blogspot.it/2012/09/reading-raster-data-with-python-and-gdal.html
#http://www.gis.usu.edu/~chrisg/python/2009/lectures/ospy_slides4.pdf
import math
from numbers import Number

from osgeo import gdal, osr, gdalconst
from osgeo.gdalconst import *
import numpy as np


def pt2fmt(pt):
    fmttypes = {
        GDT_Byte: 'B',
        GDT_Int16: 'h',
        GDT_UInt16: 'H',
        GDT_Int32: 'i',
        GDT_UInt32: 'I',
        GDT_Float32: 'f',
        GDT_Float64: 'f'
    }
    return fmttypes.get(pt, 'x')


# points_srs == None : pixel/line
# points_srs == False : same as ds
# points_srs == True : EPSG:4326
# points_srs == ... : CloneGeogCS
# points_srs == other srs - transform from given srs
def get_pixel_from_raster(ds, x_arr, y_arr, points_srs=..., ct=None):
    if ds is None:
        raise Exception('Cannot open %s' % raster_filename)

    if not isinstance(x_arr, np.ndarray):
        x_arr = np.array(x_arr)
    if not isinstance(y_arr, np.ndarray):
        y_arr = np.array(y_arr)

    # Build Spatial Reference object based on coordinate system, fetched from the opened dataset
    if points_srs is not None:
        if points_srs is False:
            # input coords are not in same SRS as ds
            if ct is not None:
                srs = osr.SpatialReference()
                srs.ImportFromWkt(ds.GetProjection())
                if points_srs is True:
                    srs = osr.SpatialReference()
                    srs.ImportFromEPSG(4326)  # WGS84 Geo
                elif points_srs is ...:
                    points_srs = srs.CloneGeogCS()  # geographic srs of the same ellipsoid
                if srs.IsSame(points_srs):
                    ct = None
                else:
                    # Transform coordinates from points_srs to raster srs
                    ct = osr.CoordinateTransformation(points_srs, srs)
            if ct is not None:
                # todo - fix this
                (x_arr, y_arr, height) = ct.TransformPoint(x_arr, y_arr)
                # ct.TransformPoints(points)

        # Read geotransform matrix and calculate corresponding pixel coordinates
        geomatrix = ds.GetGeoTransform()
        inv_geometrix = gdal.InvGeoTransform(geomatrix)
        if inv_geometrix is None:
            raise Exception("Failed InvGeoTransform()")

        x_arr, y_arr = \
            (inv_geometrix[0] + inv_geometrix[1] * x_arr + inv_geometrix[2] * y_arr), \
            (inv_geometrix[3] + inv_geometrix[4] * x_arr + inv_geometrix[5] * y_arr)

    resample_alg = gdalconst.GRIORA_NearestNeighbour
    results = np.empty_like(x_arr)

    for i, (x, y) in enumerate(zip(x_arr, y_arr)):
        if x < 0 or x >= ds.RasterXSize or y < 0 or y >= ds.RasterYSize:
            # raise Exception('Passed coordinates are not in dataset extent')
            results[i] = np.nan
        else:
            res = ds.ReadAsArray(x, y, 1, 1, resample_alg=resample_alg)
            results[i] = res[0][0]

    return results



if __name__ == "__main__":
    raster_filename = r'./data/maps/srtm1_x35_y32.tif'
    lon = (35.01, 35.02, 35.03)
    lat = (32.01, 32.02, 32.03)
    ds = gdal.Open(raster_filename, gdal.GA_ReadOnly)
    result = get_pixel_from_raster(ds, lon, lat)
    print(result)
