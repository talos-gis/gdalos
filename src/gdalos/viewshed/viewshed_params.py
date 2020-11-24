import copy
from typing import Sequence
from osgeo import gdal

from gdalos.calc import dict_util

st_seen = 5
st_seenbut = 4
st_hidbut = 3
st_hidden = 2
st_nodtm = 1
st_nodata = 0  # out of range value

viewshed_visible = st_seen
viewshed_thresh = st_hidbut
viewshed_invisible = st_hidden
viewshed_out_of_range = st_nodata
viewshed_ndv = st_nodata
viewshed_comb_ndv = 255
viewshed_comb_multi_val = 254

atmospheric_refraction_coeff = 1/7


class ViewshedParams(object):
    __slots__ = ['max_r', 'min_r', 'min_r_shave', 'max_r_slant',
                 'ox', 'oy', 'oz', 'tz', 'omsl', 'tmsl',
                 'azimuth', 'h_aperture', 'elevation', 'v_aperture',
                 'vv', 'iv', 'ov', 'ndv',
                 'refraction_coeff', 'mode', 'radio_parameters']

    def __init__(self):
        self.min_r = 0
        self.max_r = None

        self.min_r_shave = False
        self.max_r_slant = True

        self.ox = None
        self.oy = None
        self.oz = None
        self.tz = None
        self.omsl = False  # observer MSL
        self.tmsl = False  # target MSL

        self.azimuth = 0
        self.h_aperture = 360
        self.elevation = 0
        self.v_aperture = 180

        self.vv = viewshed_visible
        self.iv = viewshed_invisible
        self.ov = viewshed_out_of_range
        self.ndv = viewshed_ndv

        self.refraction_coeff = atmospheric_refraction_coeff
        self.mode = 2
        self.radio_parameters = None

    def get_calc_module(self):
        return -1 if not self.is_radio() else -2

    def is_omni_h(self):
        return not self.h_aperture or abs(self.h_aperture - 360) < 0.0001

    @property
    def oxy(self):
        return self.ox, self.oy

    @oxy.setter
    def oxy(self, oxy):
        self.ox, self.oy = oxy

    def get_as_gdal_params(self):
        vp_params = \
            'max_r', 'ox', 'oy', 'oz', 'tz', \
            'vv', 'iv', 'ov', 'ndv', 'mode'

        gdal_params = \
            'maxDistance', 'observerX', 'observerY', 'observerHeight', 'targetHeight', \
            'visibleVal', 'invisibleVal', 'outOfRangeVal', 'noDataVal', 'mode'
        d = {k1: getattr(self, k0) for k0, k1 in
             zip(vp_params, gdal_params)}
        d['dfCurvCoeff'] = 1 - self.refraction_coeff
        return d

    def is_radio(self):
        return self.radio_parameters is not None

    def is_calc_oz(self):
        return self.oz is None

    def is_calc_tz(self):
        return self.tz is None

    def get_result_dt(self):
        return gdal.GDT_Int16 if self.is_radio() or self.is_calc_oz() or self.is_calc_tz() else gdal.GDT_Byte

    def get_radio_as_talos_params(self):
        return dict_util.get_dict(self.radio_parameters)

    def get_as_talos_params(self):
        vp_params = \
            'ox', 'oy', 'oz', 'max_r', 'min_r', 'min_r_shave', 'max_r_slant', 'tz', \
            'omsl', 'tmsl', 'azimuth', 'h_aperture', 'elevation', 'v_aperture'

        talos_params = \
            'ox', 'oy', 'oz', 'MaxRange', 'MinRange', 'MinRangeShave', 'SlantRange', 'tz', \
            'ObsMSL', 'TarMSL', 'Direction', 'Aperture', 'Elevation', 'ElevationAperture'
        d = {k1: getattr(self, k0) for k0, k1 in
             zip(vp_params, talos_params)}

        slack_dummy_height = -1000
        if d['oz'] is None or d['tz'] is None:
            if self.is_radio():
                raise Exception('You have to specify oz and tz for radio calc')
            if d['oz'] is None:
                d['oz'] = slack_dummy_height
                if d['tz'] is None:
                    raise Exception('You have to specify at least one of oz or tz')
            else:
                d['tz'] = slack_dummy_height

        d['result_dt'] = self.get_result_dt()
        return d

    def update(self, d: dict):
        for k, v in d.items():
            setattr(self, k, v)

    @staticmethod
    def get_list_from_lists_dict(d: dict, key_map=None) -> Sequence['ViewshedParams']:
        max_len = max(len(v) if v else 0 for v in d.values())
        result = []
        vp = ViewshedParams()
        for i in range(max_len):
            vp = copy.deepcopy(vp)
            for k, v in d.items():
                if not v:
                    continue
                if key_map:
                    k = key_map[k]
                len_v = len(v)
                if i < len_v:
                    setattr(vp, k, v[i])
                    # vp1.k = v[i]
            result.append(vp)
        return result


# gdal_viewshed_params_short = \
#     'max_r', 'ox', 'oy', 'oz', 'tz', \
#     'vv', 'iv', 'ov', 'ndv', 'mode',
#
# gdal_viewshed_params_full = \
#     'maxDistance', 'observerX', 'observerY', 'observerHeight', 'targetHeight', \
#     'visibleVal', 'invisibleVal', 'outOfRangeVal', 'noDataVal', 'mode'
# gdal_viewshed_keymap = dict(zip(gdal_viewshed_params_short, gdal_viewshed_params_full))

viewshed_defaults = dict(vv=viewshed_visible,
                         iv=viewshed_invisible,
                         ov=viewshed_out_of_range,
                         ndv=viewshed_ndv,
                         )

# gdal_viewshed_defaults = dict_util.replace_keys(viewshed_defaults,  gdal_viewshed_keymap)
