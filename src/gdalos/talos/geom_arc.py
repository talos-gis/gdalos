from osgeo import ogr
from gdalos.talos.math0 import SinCos
from gdalos.talos.geom_util import GetFromToAngle
from gdalos.talos.gen_consts import M_2PI, M_DEG2RAD
from gdalos.talos.ogr_util import create_layer_from_geometries
import tempfile


def PolygonizeSector(px, py, rx, ry: float, DirectionDeg, ApertureDeg, ThetaDeg: float=0, PointCount: int=50):
    SinTheta, CosTheta = SinCos(ThetaDeg * M_DEG2RAD)
    # Create ring
    ring = ogr.Geometry(ogr.wkbLinearRing)

    if ApertureDeg == 360:
        Factor = M_2PI / PointCount
        for I in range(0, PointCount+1):
            SinT, CosT = SinCos(I * Factor)
            x = px + rx * CosT * CosTheta - ry * SinT * SinTheta
            y = py + ry * SinT * CosTheta + rx * CosT * SinTheta
            ring.AddPoint(x, y)
    else:
        ring.AddPoint(px, py)
        AFromRad, AToRad = GetFromToAngle(DirectionDeg, ApertureDeg)
        Factor = (AToRad - AFromRad) / (PointCount - 2)
        for I in range(0, PointCount - 1):
            SinT, CosT = SinCos(I * Factor + AFromRad)
            x = px + rx * CosT * CosTheta - ry * SinT * SinTheta
            y = py + ry * SinT * CosTheta + rx * CosT * SinTheta
            ring.AddPoint(x, y)
        ring.AddPoint(px, py)  # close the ring

    # Create polygon
    # poly = ogr.Geometry(ogr.wkbPolygon)
    # poly.AddGeometry(ring)
    return ring


if __name__ == '__main__':
    px, py = 680000.00, 3540000.00
    rx = ry = 1000
    DirectionDeg = 20
    ApertureDeg = 30
    ThetaDeg = 0
    PointCount = 50
    ring = PolygonizeSector(px, py, rx, ry, DirectionDeg, ApertureDeg, ThetaDeg, PointCount)
    geom = ogr.Geometry(ogr.wkbPolygon)
    geom.AddGeometry(ring)
    wkt = geom.ExportToIsoWkt()
    print(wkt)

    out_filename = tempfile.mktemp(suffix='.gpkg')
    # create_layer_from_geometries([geom], out_filename, is_ring_geom=False)
    create_layer_from_geometries([ring], out_filename)
    print(out_filename)
