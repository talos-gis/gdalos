from osgeo import gdal
from osgeo_utils.auxiliary.osr_util import get_srs


def gdal_to_json(ds: gdal.Dataset):
    gt = ds.GetGeoTransform(can_return_null=True)
    xsize = ds.RasterXSize
    ysize = ds.RasterYSize
    srs = get_srs(ds)
    srs = srs.ExportToProj4()
    minx = gt[0] + gt[1] * 0 + gt[2] * 0
    miny = gt[3] + gt[4] * 0 + gt[5] * 0
    maxx = gt[0] + gt[1] * xsize + gt[2] * ysize
    maxy = gt[3] + gt[4] * xsize + gt[5] * ysize
    bbox = miny, minx, maxy, maxx
    data = ds.ReadAsArray().ravel().tolist()
    result = dict(bbox=bbox, gt=gt, srs=srs, size=(xsize, ysize), data=data)
    return result
