from czml3 import Document, Packet, Preamble
from czml3.properties import (
    Material,
    RectangleCoordinates,
    Rectangle,
    ImageMaterial,
)

from osgeo import gdal
from gdalos import gdalos_trans, projdef
import base64


def gdal_to_czml(ds, name=None, out_filename=None, description=None):
    pjstr_src_srs = projdef.get_srs_pj_from_ds(ds)
    pjstr_tgt_srs = projdef.get_srs_pj_from_epsg()
    if not projdef.proj_is_equivalent(pjstr_src_srs, pjstr_tgt_srs):
        ds = gdalos_trans(ds, warp_CRS=pjstr_tgt_srs, of='MEM', ovr_type=None)

    # calculate the extent
    ulx, xres, xskew, uly, yskew, yres = ds.GetGeoTransform()
    lrx = ulx + (ds.RasterXSize * xres)
    lry = uly + (ds.RasterYSize * yres)
    wsen = [ulx, lry, lrx, uly]

    # http://osgeo-org.1560.x6.nabble.com/GDAL-Python-Save-a-dataset-to-an-in-memory-Python-Bytes-object-td5280254.html
    # reading the gdal raster data into a PNG memory buffer
    gdal.GetDriverByName('PNG').CreateCopy('/vsimem/output.png', ds)

    # Read /vsimem/output.png
    f = gdal.VSIFOpenL('/vsimem/output.png', 'rb')
    gdal.VSIFSeekL(f, 0, 2)  # seek to end
    size = gdal.VSIFTellL(f)
    gdal.VSIFSeekL(f, 0, 0)  # seek to beginning
    png_data = gdal.VSIFReadL(1, size, f)
    gdal.VSIFCloseL(f)

    # Cleanup
    gdal.Unlink('/vsimem/output.png')

    # encoding the png into base64
    base64_data = base64.b64encode(png_data)

    czml_doc = Document(
        [
            Preamble(
                name="czml",
                description=description,
            ),
            Packet(
                id="rect",
                name=name,
                rectangle=Rectangle(
                    coordinates=RectangleCoordinates(wsenDegrees=wsen),
                    fill=True,
                    material=Material(
                        image=ImageMaterial(
                            transparent=True,
                            repeat=None,
                            image=
                                "data:image/png;base64,"+base64_data.decode("utf-8")
                        ),
                    ),
                ),
            ),
        ]
    )
    ds = None  # close the ds in case it was transformed
    if out_filename:
        with open(out_filename, 'w') as f:
            print(czml_doc, file=f)
    return czml_doc
