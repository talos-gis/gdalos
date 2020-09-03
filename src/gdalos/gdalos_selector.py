import re
from numbers import Real
from typing import List, Tuple

from gdalos import projdef, gdalos_util
from gdalos.gdalos_util import OpenDS

SequanceNotString = [List, Tuple]
class DataSetSelector:
    # assuming all files are utm.
    # todo: support geo and utm inputs
    ds_list: List[OpenDS] = []
    centers = []
    re = None

    def __init__(self, lst):
        self.regex = re.compile(r'w84u([\d\.]*)')

        if not isinstance(lst, SequanceNotString):
            lst = [lst]
        lst = gdalos_util.flatten_and_expand_file_list(lst, do_expand_glob=True)
        for filename_or_ds in lst:
            self.ds_list.append(filename_or_ds)
        self.update_centers()

    def update_centers(self):
        self.centers = list(self.get_center(item.filename) for item in self.ds_list)

    def get_center(self, filename: str):
        filename = str(filename)
        result = self.find(filename)
        float_zone = float(result.group(1))
        return projdef.get_zone_center(float_zone)

    def get_item_geo(self, x, y):
        return None

    def get_item_projected(self, x, y):
        # todo: improve this naive selection that assuming the zone number is in the filename.
        if len(self.ds_list) == 1:
            return self.ds_list[0]
        best = None
        best_dist = 360
        for i, item in enumerate(self.ds_list):
            center = self.centers[i]
            dist = abs(x - center)
            if dist < best_dist:
                best = item
                best_dist = dist
        return best

def get_projected_pj(geo_x: Real, geo_y: Real) -> str:
    return '+proj={} +ellps={} +datum={} +lat_0={} +lon_0={}'.format('aeqd', 'WGS84', 'WGS84', geo_y, geo_x)
