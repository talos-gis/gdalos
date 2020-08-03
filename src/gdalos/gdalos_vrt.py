import math
from collections import defaultdict
from typing import List

import gdal
import re
import os
from pathlib import Path
import shutil

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
        self.srs = ds.GetSpatialRef()
        self.resx = self.geo_transform[1]
        self.resy = self.geo_transform[5]
        del ds

    def get_level(self, min_r):
        level = self.resx / min_r
        level = math.pow(2, round(math.log2(level)))
        return level

    def get_ds(self):
        return open_ds(self.path, src_ovr=self.ovr)

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


def make_vrt_with_multiple_extent_overviews_from_raster_overview_list(ros: List[RasterOverview], vrt_filename, **kwargs):
    if not ros:
        return None
    print_ros(ros)

    extent = ros[0].extent
    # r = set()
    min_r = math.inf
    max_r = -math.inf
    srs = None
    path = None
    for ro in ros:
        extent = ro.extent.union(extent)
        x = ro.resx
        # r.add(x)
        min_r = min(min_r, x)
        max_r = max(max_r, x)
        if srs is None:
            srs = ro.srs
            path = ro.path
        elif not srs.IsSame(ro.srs):
            raise Exception('srs not the same, please separate by srs:\n{}\n{}'.format(path, ro.path))

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
    ros = best_ros

    print('best ros:')
    print_ros(ros)
    for idx, ro in enumerate(ros):
        # if ro.ovr < 0:
        #     continue
        print('{}: {}'.format(idx, ro.path))
        # single_src_vrt = ro.path.with_suffix('.{}.vrt'.format(ro.ovr))
        single_src_vrt = (ro.path.with_name('vrt') / ro.path.name).with_suffix('.{}.vrt'.format(ro.ovr))
        make_ros_vrt([ro], extent, single_src_vrt)
        ro.path = single_src_vrt
        ro.ovr = -1
    return make_ros_vrt_overviews(ros, extent, vrt_filename, **kwargs)


def vrt_add_overviews(ros: List[RasterOverview], filename_in: Path, filename_out: Path):
    # <SourceFilename relativeToVRT="1">0.vrt</SourceFilename>

    rsrc_bnd = re.compile('(\s*)<SourceBand>\d+</SourceBand>\s*')
    rSource = re.compile('(\s*)</(Simple|Complex)Source>\s*')

    # <Overview>
    #   <SourceFilename relativeToVRT="1">2\2.vrt</SourceFilename>
    #   <SourceBand>1</SourceBand>
    # </Overview>
    dir_name = Path(os.path.dirname(filename_out))
    with open(filename_in) as f, open(filename_out, "w") as f2:
        for line in f:
            f2.write(line)
            m = rsrc_bnd.match(line)
            if m:
                src_bnd = '\t' + line
            else:
                m = rSource.match(line)
                if m:
                    for ro in ros:
                        ovr_filename = ro.path
                        ovr_path = (dir_name / Path(ovr_filename)).resolve()
                        if ovr_path.is_file():
                            f2.write('\t<Overview>\n')
                            f2.write('\t\t<SourceFilename relativeToVRT="1">{}</SourceFilename>\n'.format(str(ovr_filename)))
                            f2.write(src_bnd)
                            f2.write('\t</Overview>\n')


def vrt_fix_openoptions(ros: List[RasterOverview], filename_in: Path, filename_out: Path):
    # for some reason open options are not written to the vrt.
    # I'll open a bug report, in the mean time I wrote this workaround
    p = re.compile('<SourceFilename relativeToVRT="(.*)">(.*)</SourceFilename>')
    dir_name = Path(os.path.dirname(filename_out))
    with open(filename_in) as f, open(filename_out, "w") as f2:
        for line in f:
            f2.write(line)
            m = p.search(line)
            if m:
                relative = m.group(1)
                SourceFilename = m.group(2)

                #   <OpenOptions>
                #       <OOI key="OVERVIEW_LEVEL">6</OOI>
                #   </OpenOptions>
                ovr = ...
                for ro in ros:
                    if relative:
                        SourceFilename = (dir_name / SourceFilename).resolve()
                    if ro.path == SourceFilename:
                        ovr = ro.ovr
                        if ovr >= 0:
                            f2.write(
                                '\t<OpenOptions>\n\t\t<OOI key="OVERVIEW_LEVEL">{}</OOI>\n\t</OpenOptions>\n'.format(
                                    ovr))
                        break
                if ovr is ...:
                    raise Exception('SourceFilename: {} not found'.format(SourceFilename))


def make_ros_vrt_overviews(ros: List[RasterOverview], extent: GeoRectangle, vrt_filename: Path, add_overviews=True, return_ds=False):
    options = gdal.BuildVRTOptions(outputBounds=(extent.min_x, extent.min_y, extent.max_x, extent.max_y))
    vrt_ds = gdal.BuildVRT(str(vrt_filename), ros[0].get_ds(), options=options)
    if vrt_ds is None:
        raise Exception("Error! cannot create vrt. Cannot proceed")
    if add_overviews:
        vrt_ds = None
        vrt_filename_temp = vrt_filename.with_suffix('.tmp.vrt')
        shutil.move(vrt_filename, vrt_filename_temp)
        vrt_add_overviews(ros[1:], filename_in=vrt_filename_temp, filename_out=vrt_filename)
        os.remove(vrt_filename_temp)
        if return_ds:
            vrt_ds = open_ds(vrt_filename)
    if return_ds:
        return vrt_ds
    else:
        return vrt_filename


def make_ros_vrt(ros: List[RasterOverview], extent: GeoRectangle, vrt_filename: Path, fix_open_options=True):
    options = gdal.BuildVRTOptions(outputBounds=(extent.min_x, extent.min_y, extent.max_x, extent.max_y))
    ds_list = [ro.get_ds() for ro in ros]
    os.makedirs(os.path.dirname(str(vrt_filename)), exist_ok=True)
    vrt_ds = gdal.BuildVRT(str(vrt_filename), ds_list, options=options)
    if vrt_ds is None:
        raise Exception("Error! cannot create vrt. Cannot proceed")
    if fix_open_options:
        vrt_ds = None
        vrt_filename_temp = vrt_filename.with_suffix('.tmp.vrt')
        shutil.move(vrt_filename, vrt_filename_temp)
        vrt_fix_openoptions(ros, filename_in=vrt_filename_temp, filename_out=vrt_filename)
        os.remove(vrt_filename_temp)
        vrt_ds = open_ds(vrt_filename)
    return vrt_ds


def make_overviews_vrt(paths: List[Path], vrt_filename=None, **kwargs):
    if not paths:
        return None
        # raise Exception ('no files are given')
    paths = [Path(path) for path in paths]
    print(paths)
    if vrt_filename is None:
        first = paths[0]
        vrt_filename = first.with_suffix('.super.vrt')
    o = []
    for path in paths:
        r = RasterOverviewList(path)
        o.extend(r.o)
    return make_vrt_with_multiple_extent_overviews_from_raster_overview_list(o, vrt_filename=vrt_filename, **kwargs)


def make_overviews_vrt_dir(path: Path, pattern='*.tif', **kwargs):
    path = Path(path)
    paths = list(path.glob(pattern=pattern))
    vrt_filename = path.with_suffix('.vrt')
    return make_overviews_vrt(paths=paths, vrt_filename=vrt_filename, **kwargs)


if __name__ == '__main__':
    # parent_path = Path(r'd:\Maps.raw\osm')
    # parent_path = Path(r'd:\Maps\temp\x')
    # parent_path = Path(r'd:\Maps\w84geo\topo')
    parent_path = Path(r'd:\Maps.raw\osm')
    for path in parent_path.glob(pattern='*'):
        if path.is_dir():
            make_overviews_vrt_dir(path)
    print('done!')
