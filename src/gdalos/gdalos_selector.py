import math
import re
from numbers import Real
from pathlib import Path
from typing import List, Tuple, Union

from gdalos import projdef, gdalos_util
from gdalos.gdalos_types import SequanceNotString, FileName
from gdalos.gdalos_util import OpenDS


class DataSetSelector:
    # assuming all files are utm.
    # todo: support geo and utm inputs
    __slots__ = ['ds_list', 'centers']
    regex = re.compile(r'w84u([-+]?[0-9]*\.?[0-9]+)')

    def __init__(self, lst: Union[FileName, SequanceNotString]):
        self.ds_list: List[OpenDS] = []
        lst = gdalos_util.flatten_and_expand_file_list(lst, do_expand_glob=True, always_return_list=True)

        for filename_or_ds in lst:
            self.ds_list.append(OpenDS(filename_or_ds))
        if len(self.ds_list) > 1:
            self.centers = self.get_centers()

    def get_map(self, idx):
        return self.ds_list[idx].filename

    def get_map_count(self):
        return len(self.ds_list)

    def get_centers(self) -> List[Real]:
        return list(self.get_center(item.filename) for item in self.ds_list)

    def get_center(self, filename: FileName) -> Real:
        filename = str(filename)
        result = self.regex.search(filename)
        float_zone = float(result.group(1))
        return projdef.get_zone_center(float_zone)

    def get_item_geo(self, x, y):
        return None

    def get_item_projected(self, x, y):
        # todo: improve this naive selection that assuming the zone number is in the filename.
        if len(self.ds_list) == 1:
            best = self.ds_list[0]
        else:
            if x < -180 or x > 180:
                raise Exception(f'x: {x} outside range')
            best = None
            best_dist = math.inf
            best_center = None
            for i, item in enumerate(self.ds_list):
                center = self.centers[i]
                dist = abs(x - center)
                if dist < best_dist:
                    best = item
                    best_dist = dist
                    best_center = center
            if best is None:
                raise Exception(f'could not find appropriate input file for x: {x}')
            print(
                f'x: {x} selected center: {best_center} best_zone: {projdef.get_zone_by_lon(x, True)} filename: {best.filename}')
        return best.filename, best.__enter__()


def get_projected_pj(geo_x: Real, geo_y: Real) -> str:
    return '+proj={} +ellps={} +datum={} +lat_0={} +lon_0={}'.format('aeqd', 'WGS84', 'WGS84', geo_y, geo_x)
