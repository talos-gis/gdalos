from gdalos import gdal_version, version_tuple, gdalos_version

gdal_cog_support = gdal_version >= (3, 1)
gdal_multi_thread_support = gdal_version >= (3, 2)
gdal_workaround_warp_scale_bug = gdal_version < (3, 3)  # workaround https://github.com/OSGeo/gdal/issues/3232
