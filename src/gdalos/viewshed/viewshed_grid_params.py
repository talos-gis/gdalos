import copy
from gdalos.viewshed.viewshed_params import ViewshedParams
from gdalos.viewshed.radio_params import RadioParams


class ViewshedGridParams(ViewshedParams):
    __slots__ = ['name', 'interval', 'grid_range', 'r_fact']

    def __init__(self, is_geo, is_radio):
        super().__init__()
        if is_geo:
            # self.ox = 35.0
            # self.oy = 32.0
            self.ox = 25.0
            self.oy = 15.0
            self.max_r = 10000
            self.r_fact = 111_111
        else:
            self.max_r = 2000
            self.ox = 700_000
            self.oy = 3550_000
            self.r_fact = 1
        self.oz = 10
        self.tz = 10

        # self.azimuth = 20
        # self.h_aperture = 30

        self.name = None
        self.interval = self.max_r / (self.r_fact * 2)
        j = 1
        self.grid_range = range(-j, j + 1)

        if is_radio:
            self.radio_parameters = RadioParams()

    def get_array(self):
        result = []
        prefix = self.name + '_' if self.name else ''
        for i in self.grid_range:
            for j in self.grid_range:
                res = copy.deepcopy(self)
                res.ox = self.ox + i * self.interval
                res.oy = self.oy + j * self.interval
                res.name = prefix+'{}_{}'.format(i, j)
                result.append(res)
        return result

    def get_as_gdal_params_array(self):
        res = copy.deepcopy(self)
        res.ox = []
        res.oy = []
        for i in self.grid_range:
            for j in self.grid_range:
                ox = self.ox + i * self.interval
                oy = self.oy + j * self.interval
                res.ox.append(ox)
                res.oy.append(oy)
        return res.get_as_gdal_params()
