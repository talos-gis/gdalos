:Name: The Way We Like Our Map Files
:Authors: Idan Miara

Raster Data:
============

* Coordinates Reference System
    * Any raster: WGS84 Geo (EPSG:4326)
    * DEM only: WGS84 Geo (EPSG:4326) or WGS84 UTM (EPSG: 32601-32660, 32701-32760)

* Preferred format
    * Cloud Optimized Geotiff (COG) - highly recommended
    * Tools for creating a COG
        * gdalos: https://github.com/talos-gis/gdalos
        * more tools are listed on: https://www.cogeo.org/
    * or otherwise any other format that can be safely converted to GeoTiff with gdal_translate

* Overviews:
    * We highly recommend that the dataset will include overviews (as a series of powers of 2 of the base resolution).
    * The number of overviews should be determined by the base resolution so that the resolution of the highest overview will be about 1000 meters or 0.01 degree.
    * Overviews are often created with the gdaladdo command.

* Data Type
    * Raster for visualization
        * RGBA (4 byte bands)
        * RGB (3 byte bands)
    * DEM Raster
        * Int16
        * Float32
    * NoData
        * Alpha Channel (as in RGBA) or NoData Value should be correctly set if NoData values exist in the dataset.

Vector Data:
============
* Coordinates Reference System
    * WGS84 Geo (EPSG:4326)

* Preferred formats
    * GeoPackage (GPKG)
    * ESRI Shape File
    * or otherwise any other format that can be safely converted to ESRI Shape File with ogr2ogr

* Geometry Types
    * Any entity type that accepted by the ESRI Shape file format is accepted.

