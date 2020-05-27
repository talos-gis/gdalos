#http://geoinformaticstutorial.blogspot.it/2012/09/reading-raster-data-with-python-and-gdal.html
#http://www.gis.usu.edu/~chrisg/python/2009/lectures/ospy_slides4.pdf

from osgeo import gdal, osr
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
def get_pixel_from_raster(ds, x, y, points_srs=..., ct=None):
    if ds is None:
        raise Exception('Cannot open %s' % raster_filename)

    # Build Spatial Reference object based on coordinate system, fetched from the opened dataset
    if points_srs is None:
        x, y = int(x), int(y)
    else:
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
                (x, y, height) = ct.TransformPoint(x, y)

        # Read geotransform matrix and calculate corresponding pixel coordinates
        geomatrix = ds.GetGeoTransform()
        inv_geometrix = gdal.InvGeoTransform(geomatrix)
        if inv_geometrix is None:
            raise Exception("Failed InvGeoTransform()")

        x, y = int(inv_geometrix[0] + inv_geometrix[1] * x + inv_geometrix[2] * y), \
               int(inv_geometrix[3] + inv_geometrix[4] * x + inv_geometrix[5] * y)

    if x < 0 or x >= ds.RasterXSize or y < 0 or y >= ds.RasterYSize:
        raise Exception('Passed coordinates are not in dataset extent')

    res = ds.ReadAsArray(x, y, 1, 1)

    return res[0][0]


def get_pixel_from_raster_multi(ds, points, points_srs=..., ct=None):
    if len(points) == 0:
        return None
    elif len(points == 1):
        return get_pixel_from_raster(ds, *points[0], points_srs, ct)

    if ds is None:
        raise Exception('Cannot open %s' % raster_filename)

    # Build Spatial Reference object based on coordinate system, fetched from the opened dataset

    if points_srs is False:
        inv_geometrix = None
    else:
        if points_srs is not None:
            # input coords are not in same SRS as ds
            if ct is not None:
                srs = osr.SpatialReference()
                srs.ImportFromWkt(ds.GetProjection())
                if points_srs is ...:
                    points_srs = srs.CloneGeogCS()  # geographic srs of the same ellipsoid
                elif points_srs is True:
                    srs = osr.SpatialReference()
                    srs.ImportFromEPSG(4326)  # WGS84 Geo
                if srs.IsSame(points_srs):
                    ct = None
                else:
                    # Transform coordinates from points_srs to raster srs
                    ct = osr.CoordinateTransformation(points_srs, srs)
            if ct is not None:
                ct.TransformPoints(points)

        # Read geotransform matrix and calculate corresponding pixel coordinates
        geomatrix = ds.GetGeoTransform()
        inv_geometrix = gdal.InvGeoTransform(geomatrix)
        if inv_geometrix is None:
            raise Exception("Failed InvGeoTransform()")

    result = np.empty([len(points)])
    for idx, (x, y) in enumerate(points):
        if inv_geometrix is None:
            x, y = int(x), int(y)
        else:
            x, y = int(inv_geometrix[0] + inv_geometrix[1] * x + inv_geometrix[2] * y), \
                   int(inv_geometrix[3] + inv_geometrix[4] * x + inv_geometrix[5] * y)

        if x < 0 or x >= ds.RasterXSize or y < 0 or y >= ds.RasterYSize:
            raise Exception('Passed coordinates {} are not in dataset extent'.format(idx))

        res = ds.ReadAsArray(x, y, 1, 1)

        result[idx] = res[0][0]

    return result


if __name__ == "__main__":
    raster_filename = r'./data/sample/maps/srtm1_x35_y32.tif'
    lon = (35.1, 35.2, 35.3)
    lat = (32.1, 32.2, 32.3)
    points = np.dstack((lon, lat))[0]
    ds = gdal.Open(raster_filename, gdal.GA_ReadOnly)
    result = get_pixel_from_raster_multi(ds, points)
    print(result)

    result1 = np.empty([len(points)])
    for idx, p in enumerate(points):
        result1[idx] = get_pixel_from_raster(ds, p[0], p[1])
    errs = sum(abs(result1 - result))
    print(errs)
