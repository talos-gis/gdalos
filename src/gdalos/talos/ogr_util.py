from osgeo import ogr
import os
from typing import Sequence


def create_layer_from_geometries(geoms: Sequence[ogr.Geometry], out_filename, is_ring_geom=True, driver_name='gpkg', layer_name='1'):
    # Remove output shapefile if it already exists
    driver = ogr.GetDriverByName(driver_name)
    if os.path.exists(out_filename):
        driver.DeleteDataSource(out_filename)

    # Create the output shapefile
    ds = driver.CreateDataSource(out_filename)
    outLayer = ds.CreateLayer(layer_name, geom_type=ogr.wkbPolygon)

    # Add an ID field
    # idField = ogr.FieldDefn("id", ogr.OFTInteger)
    # outLayer.CreateField(idField)

    # Create the feature and set values
    featureDefn = outLayer.GetLayerDefn()
    for geom in geoms:
        if is_ring_geom:
            ring = geom
            geom = ogr.Geometry(ogr.wkbPolygon)
            geom.AddGeometry(ring)
        feature = ogr.Feature(featureDefn)
        feature.SetGeometry(geom)
        # feature.SetField("id", 1)
        outLayer.CreateFeature(feature)

    # Close DataSource
    # ds.Destroy()
    del ds
