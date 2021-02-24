import math
import os
import re
import shutil
import uuid
from collections import defaultdict
from pathlib import Path
from typing import List, Optional

from osgeo import gdal
from osgeo_utils.auxiliary.base import enum_to_str

from gdalos import gdalos_util
from gdalos.gdalos_extent import get_extent
from gdalos.gdalos_types import RasterKind, MaybeSequence
from gdalos.gdalos_util import open_ds, OpenDS, PathOrDS, do_skip_if_exists
from gdalos.rectangle import GeoRectangle, rect_contains


class AutoRepr(object):
    def __repr__(self):
        items = ("%s = %r" % (k, v) for k, v in self.__dict__.items())
        return "<%s: {%s}>" % (self.__class__.__name__, ', '.join(items))


class RasterOverview(AutoRepr):
    def __init__(self, path: Path, ovr_idx=0):
        self.path = path
        if ovr_idx is None:
            ovr_idx = 0
        self.ovr_idx = ovr_idx
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
        return open_ds(self.path, ovr_idx=self.ovr_idx)

    # def __repr__(self):
    #     return str([str(ovr) for ovr in self.o])


class RasterOverviewList(AutoRepr):
    def __init__(self, path: Path):
        self.path = path
        with OpenDS(self.path) as ds:
            bnd = ds.GetRasterBand(1)
            ovr_count = bnd.GetOverviewCount()
        self.o = []
        for ovr in range(0, ovr_count+1):
            self.o.append(RasterOverview(self.path, ovr))

    def __repr__(self):
        return '\n'.join([str(ovr) for ovr in self.o])


def print_ros(ros: List[RasterOverview]):
    x = '\n'.join([str(ovr) for ovr in ros])
    print(x)


def filter_ros(ros: List[RasterOverview]):
    ros = sorted(ros, key=lambda ro: ro.extent.area, reverse=True)
    # return ros[0]
    big_ros = []
    for ro in ros:
        rect = ro.extent
        contained = False
        for big_ro in big_ros:
            big_rect = big_ro.extent
            contained = rect_contains(big_rect, rect)
            if contained:
                break
        if not contained:
            big_ros.append(ro)
    return big_ros


def make_single_ro(ros: List[RasterOverview], vrt_filename):
    if len(ros) == 1:
        return ros[0]
    filenames = [ro.path for ro in ros]
    gdalos_make_vrt(filenames, vrt_path=vrt_filename)
    ro = RasterOverview(vrt_filename)
    return ro


def make_vrt_with_multiple_extent_overviews_from_raster_overview_list(ros: List[RasterOverview], vrt_filename, intermediate_dir=None, **kwargs):
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

    keys = list(sorted(d.keys()))
    ros1 = []
    for idx, key in enumerate(keys):
        ros = d[key]
        ros = filter_ros(ros)
        vrt_for_idx = vrt_filename.with_suffix(f'.{idx:02}.vrt')
        if intermediate_dir is not None:
            vrt_for_idx = Path(intermediate_dir) / vrt_for_idx.parts[-1]
        make_ros_vrt(ros, extent, vrt_for_idx)
        ro = RasterOverview(vrt_for_idx)
        ros1.append(ro)
    ros = ros1
    print('best ros:')
    print_ros(ros)
    return make_ros_vrt_overviews(ros, extent, vrt_filename, **kwargs)


def vrt_add_overviews(ros: List[RasterOverview], filename_in: Path, filename_out: Path):
    # <SourceFilename relativeToVRT="1">0.vrt</SourceFilename>

    rsrc_bnd = re.compile(r'(\s*)<SourceBand>\d+</SourceBand>\s*')
    rSource = re.compile(r'(\s*)</(Simple|Complex)Source>\s*')

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
                        ovr_filename = os.path.relpath(ovr_path, dir_name)
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
                source_filename = m.group(2)
                #   <OpenOptions>
                #       <OOI key="OVERVIEW_LEVEL">6</OOI>
                #   </OpenOptions>
                ovr_idx = None
                for ro in ros:
                    if relative:
                        source_filename = (dir_name / source_filename).resolve()
                    if ro.path == source_filename:
                        ovr_idx = ro.ovr_idx
                        if ovr_idx > 0:
                            f2.write(
                                '\t<OpenOptions>\n\t\t<OOI key="OVERVIEW_LEVEL">{}</OOI>\n\t</OpenOptions>\n'.format(
                                    ovr_idx-1))
                        break
                if ovr_idx is None:
                    raise Exception('SourceFilename: {} not found'.format(source_filename))


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
    # dir_name = Path(os.path.dirname(str(vrt_filename)))
    # ds_list = [os.path.relpath(ro.path, dir_name) for ro in ros]
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
    return make_vrt_with_multiple_extent_overviews_from_raster_overview_list(
        o, vrt_filename=vrt_filename, **kwargs)


def filter_ovr(paths):
    paths = [Path(p) for p in paths]
    new = []
    for p in paths:
        if p.suffix != '.ovr':
            new.append(p)
        else:
            parent = p.with_suffix('')
            if parent not in paths:
                new.append(p)
    return new


def make_overviews_vrt_dir(path: Path, pattern=('*.tif', '*.ovr'), outside=True, inside=True, **kwargs):
    path = Path(path)
    if not isinstance(pattern, (list, tuple)):
        pattern = [pattern]
    paths = []
    for pat in pattern:
        paths.extend(path.glob(pattern=pat))
    paths = filter_ovr(paths)

    result = None
    vrt_filenames = []
    if outside:
        vrt_filenames.append(path.with_suffix('.vrt'))
    if inside:
        dir_name = Path(os.path.basename(str(path)))
        vrt_filenames.append(path / dir_name.with_suffix('.vrt'))
    for vrt_filename in vrt_filenames:
        result = make_overviews_vrt(paths=paths, vrt_filename=vrt_filename, intermediate_dir=path, **kwargs)
    return result


def make_overviews_vrt_super_dir(super_path: Path, **kwargs):
    for path in Path(super_path).glob(pattern='*'):
        if path.is_dir():
            make_overviews_vrt_dir(path, **kwargs)


def gdalos_make_vrt(
        filenames: MaybeSequence[PathOrDS],
        filenames_expand: Optional[bool] = None,
        vrt_path=None,
        kind=None,
        resampling_alg=...,
        overwrite=True,
        vrt_options: Optional[dict] = None,
        logger=None,
):
    if gdalos_util.is_list_like(filenames):
        flatten_filenames = gdalos_util.flatten_and_expand_file_list(filenames, do_expand_glob=filenames_expand)
    else:
        flatten_filenames = [filenames]
    flatten_filenames = [str(f) if isinstance(f, Path) else f for f in flatten_filenames]
    if not flatten_filenames:
        return None
    first_filename = flatten_filenames[0]
    if vrt_path is None:
        vrt_path = f'/vsimem/{uuid.uuid4()}.vrt'
    elif vrt_path is ...:
        vrt_path = first_filename + ".vrt"
    else:
        vrt_path = str(vrt_path)
    is_vsimem = vrt_path.startswith('/vsimem/')
    if not is_vsimem:
        if os.path.isdir(vrt_path):
            vrt_path = os.path.join(vrt_path, os.path.basename(first_filename) + ".vrt")
        if do_skip_if_exists(vrt_path, overwrite, logger):
            return vrt_path
        if os.path.isfile(vrt_path):
            raise Exception("could not delete vrt file: {}".format(vrt_path))
        os.makedirs(os.path.dirname(vrt_path), exist_ok=True)
    vrt_options = dict(vrt_options or dict())
    if resampling_alg is None:
        if kind in [None, ...]:
            kind = RasterKind.guess(first_filename)
        resampling_alg = kind.resampling_alg_by_kind(kind)
    if resampling_alg is not ...:
        vrt_options["resampleAlg"] = enum_to_str(resampling_alg)
    vrt_options = gdal.BuildVRTOptions(**vrt_options)
    ds = gdal.BuildVRT(vrt_path, flatten_filenames, options=vrt_options)
    return vrt_path, ds


if __name__ == '__main__':
    parent_dir = Path(r'd:\Maps.progress\osm')
    make_overviews_vrt_dir(parent_dir / 'wikimedia-3857.xml')
    # make_overviews_vrt_super_dir(parent_dir)
    print('done!')
