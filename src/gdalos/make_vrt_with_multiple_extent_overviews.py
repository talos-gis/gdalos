import math
from collections import defaultdict
from typing import List

import gdal
from pathlib import Path

from gdalos.rectangle import GeoRectangle
from gdalos.gdalos_extent import get_extent
from gdalos.gdalos_util import open_ds, OpenDS


class AutoRepr(object):
    def __repr__(self):
        items = ("%s = %r" % (k, v) for k, v in self.__dict__.items())
        return "<%s: {%s}>" % (self.__class__.__name__, ', '.join(items))


class RasterOverview(AutoRepr):
    def __init__(self, path: Path, ovr=-1):
        self.path = path
        if ovr is None:
            ovr = -1
        self.ovr = ovr
        ds = self.get_ds()
        # self.bnd = self.ds.GetRasterBand(1)
        # self.ovr_count = self.bnd.GetOverviewCount()
        self.extent = get_extent(ds)
        self.geo_transform = ds.GetGeoTransform()
        self.resx = self.geo_transform[1]
        self.resy = self.geo_transform[5]
        del ds

    def get_level(self, min_r):
        level = self.resx/min_r
        level = math.pow(2, round(math.log2(level)))
        return level

    def get_ds(self):
        src_ovr = None if self.ovr < 0 else self.ovr
        return open_ds(self.path, src_ovr=src_ovr)

    # def __repr__(self):
    #     return str([str(ovr) for ovr in self.o])


class RasterOverviewList(AutoRepr):
    def __init__(self, path: Path):
        self.path = path
        with OpenDS(self.path) as ds:
            bnd = ds.GetRasterBand(1)
            ovr_count = bnd.GetOverviewCount()
        self.o = []
        for ovr in range(-1, ovr_count):
            self.o.append(RasterOverview(self.path, ovr))

    def __repr__(self):
        return '\n'.join([str(ovr) for ovr in self.o])


def print_ros(ros: List[RasterOverview]):
    x = '\n'.join([str(ovr) for ovr in ros])
    print(x)


def make_vrt_with_multiple_extent_overviews(ros: List[RasterOverview], vrt_filename):
    print_ros(ros)

    extent = ros[0].extent
    # r = set()
    min_r = math.inf
    max_r = -math.inf
    for ro in ros:
        extent = ro.extent.union(extent)
        x = ro.resx
        # r.add(x)
        min_r = min(min_r, x)
        max_r = max(max_r, x)
    fact = max_r / min_r

    print(extent)
    print('res ({}) - ({})'.format(min_r, max_r))

    # levels = set()
    # for ro in ros:
    #     levels.add(ro.get_level(min_r))
    # levels = sorted(levels)
    # print('levels: {}'.format(levels))

    d = defaultdict(list)
    for ro in ros:
        level = ro.get_level(min_r)
        d[level].append(ro)

    for key in sorted(d.keys()):
        ros = d[key]
        ros = sorted(ros, key=lambda ro: ro.extent.area, reverse=True)
        d[key] = ros

    best_ros = []
    for key in sorted(d.keys()):
        ros = d[key]
        best_ros.append(ros[0])
        for ro in ros:
            print('{}: {}'.format(key, ro))

    print('best ros:')
    print_ros(best_ros)
    make_ros_vrt(ros, extent, vrt_filename)


def make_ros_vrt(ros: List[RasterOverview], extent: GeoRectangle, vrt_filename: Path):
    options = gdal.BuildVRTOptions(outputBounds=(extent.min_x, extent.min_y, extent.max_x, extent.max_y))
    ds_list = [ro.get_ds() for ro in ros]
    vrt_ds = gdal.BuildVRT(str(vrt_filename), ds_list, options=options)
    if vrt_ds is None:
        raise Exception("Error! cannot create vrt. Cannot proceed")
    return vrt_ds


def make_vrt_with_multiple_extent_overviews_from_dir(path: Path, pattern='*.tif'):
    print(path)
    paths = list(path.glob(pattern=pattern))
    vrt_filename = path / Path(path.name).with_suffix('.vrt')

    o = []
    for path in paths:
        r = RasterOverviewList(path)
        o.extend(r.o)
    make_vrt_with_multiple_extent_overviews(o, vrt_filename=vrt_filename)


if __name__ == '__main__':
    parent_path = Path(r'd:\Maps.raw\osm')
    for path in parent_path.glob(pattern='*'):
        if path.is_dir():
            make_vrt_with_multiple_extent_overviews_from_dir(path)
    print('done!')
