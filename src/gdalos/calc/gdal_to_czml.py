from czml3 import Document, Packet, Preamble
from czml3.properties import (
    Material,
    RectangleCoordinates,
    Rectangle,
    ImageMaterial, Polyline, PositionList, PolylineMaterial, SolidColorMaterial,
)

from osgeo import gdal
from gdalos.gdalos_trans import gdalos_trans, projdef
from gdalos.gdalos_color import ColorPalette
import base64

from gdalos.gdalos_types import OvrType

czml_metadata_name = 'colors'


def gdal_to_czml(ds:gdal.Dataset, name=None, out_filename=None, description=None):
    if description is None:
        description = ds.GetMetadataItem(czml_metadata_name)
    pjstr_src_srs = projdef.get_srs_pj(ds)
    pjstr_tgt_srs = projdef.get_srs_pj(4326)
    if not projdef.are_srs_equivalent(pjstr_src_srs, pjstr_tgt_srs):
        ds = gdalos_trans(ds, warp_srs=pjstr_tgt_srs, of='MEM', ovr_type=OvrType.no_overviews, write_spec=False)

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
    if out_filename:
        with open(str(out_filename), 'w') as f:
            print(czml_doc, file=f)
    return ds, czml_doc


def make_czml_description(pal: ColorPalette, process_palette=2):
    if pal:
        if process_palette >= 2:
            # number:color
            return ' '.join(['{}:{}'.format(
                ColorPalette.format_number(key),
                ColorPalette.format_color(pal.get_color(key))) for key in pal.get_all_keys()])
        else:
            # numbers
            return ' '.join([ColorPalette.format_number(x) for x in pal.pal.keys()])
    else:
        return None


def polyline_to_czml(polys, colors, name=None, out_filename=None) -> Document:
    czml_doc = Document(
        [
            Preamble(
                name=name,
            ),
            *[Packet(
                id=f"Line{i}",
                name=f"polyline{i}",
                polyline=Polyline(
                    positions=PositionList(
                        cartographicDegrees=poly
                    ),
                    material=PolylineMaterial(
                        solidColor=SolidColorMaterial.from_list(list(ColorPalette.color_to_color_entry(color)))
                    ),
                ),
            ) for i, (poly, color) in enumerate(zip(polys, colors))]
        ]
    )
    if out_filename:
        with open(str(out_filename), 'w') as f:
            print(czml_doc, file=f)
    return czml_doc
