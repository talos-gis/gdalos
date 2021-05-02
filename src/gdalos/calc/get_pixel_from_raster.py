#http://geoinformaticstutorial.blogspot.it/2012/09/reading-raster-data-with-python-and-gdal.html
#http://www.gis.usu.edu/~chrisg/python/2009/lectures/ospy_slides4.pdf

import numpy as np
from osgeo import gdal, osr, gdalconst
from osgeo_utils.samples.gdallocationinfo import gdallocationinfo_util as get_pixel_from_raster


if __name__ == "__main__":
    raster_filename = r'./data/maps/srtm1_x35_y32.tif'
    lon = (35.01, 35.02, 35.03)
    lat = (32.01, 32.02, 32.03)
    ds = gdal.Open(raster_filename, gdal.GA_ReadOnly)
    result = get_pixel_from_raster(filename_or_ds=ds, x=lon, y=lat)
    print(result)
