from typing import Sequence

import numpy as np
from osgeo import gdal

from gdalos import gdalos_base
from gdalos.gdalos_base import make_points_list, make_xy_list, FillMode
from gdalos.viewshed.radio_params import RadioParams, RadioCalcType

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


class LOSParams(object):
    __slots__ = ['ox', 'oy', 'oz', 'tz', 'omsl', 'tmsl',
                 'refraction_coeff', 'mode', 'radio_parameters', 'xy_fill', 'ot_fill']

    def __init__(self):
        self.ox = None
        self.oy = None
        self.oz = None
        self.tz = None
        self.omsl = False  # observer MSL
        self.tmsl = False  # target MSL

        self.refraction_coeff = atmospheric_refraction_coeff
        self.mode = None
        self.radio_parameters = None
        self.xy_fill = FillMode.zip_cycle
        self.ot_fill = FillMode.zip_cycle

    def is_calc_oz(self):
        return self.oz is None

    def is_calc_tz(self):
        return self.tz is None

    @property
    def oxy(self):
        return make_points_list(self.ox, self.oy, self.xy_fill)

    @oxy.setter
    def oxy(self, oxy):
        self.ox, self.oy, *_ = make_xy_list(oxy)

    def update(self, d: dict):
        for k, v in d.items():
            setattr(self, k, v)

    def make_xy_lists(self):
        if not isinstance(self.ox, Sequence):
            self.ox = [self.ox]
        if not isinstance(self.oy, Sequence):
            self.oy = [self.oy]

    @classmethod
    def get_list_from_lists_dict(cls, d: dict, key_map=None) -> Sequence['LOSParams']:
        radio_d = d['radio_parameters']
        d['radio_parameters'] = None
        vp_array = gdalos_base.get_list_from_lists_dict(d, cls(), key_map=key_map)
        if radio_d is not None:
            radio_array = gdalos_base.get_list_from_lists_dict(radio_d, RadioParams(), key_map=key_map)
            r = None
            for i, v in enumerate(vp_array):
                if i < len(radio_array):
                    r = radio_array[i]
                v.radio_parameters = r
        return vp_array

    @classmethod
    def get_object_from_lists_dict(cls, d: dict, key_map=None) -> Sequence['LOSParams']:
        radio_d = d['radio_parameters']
        d['radio_parameters'] = None
        vp_obj = gdalos_base.get_object_from_lists_dict(d, cls(), key_map=key_map)
        if radio_d is not None:
            radio_obj = gdalos_base.get_object_from_lists_dict(radio_d, RadioParams(), key_map=key_map)
            radio_obj.unsequence()
            vp_obj.radio_parameters = radio_obj
        return vp_obj

    def get_calc_module(self):
        return -1 if not self.is_radio() else -2

    def is_radio(self):
        return self.radio_parameters is not None

    def get_radio_as_talos_params(self):
        return self.radio_parameters.get_dict()


class MultiPointParams(LOSParams):
    __slots__ = ('tx', 'ty', 'results')

    def __init__(self):
        super(MultiPointParams, self).__init__()
        self.tx = None
        self.ty = None
        self.mode = None
        self.results = None

    def make_xy_lists(self):
        super(MultiPointParams, self).make_xy_lists()
        if not isinstance(self.tx, Sequence):
            self.tx = [self.tx]
        if not isinstance(self.ty, Sequence):
            self.ty = [self.ty]

    @property
    def txy(self):
        return make_points_list(self.tx, self.ty, self.xy_fill)

    @txy.setter
    def txy(self, txy):
        self.tx, self.ty = make_xy_list(txy)

    def get_as_talos_params(self):
        input_names = ['ox', 'oy', 'oz', 'tx', 'ty', 'tz']
        vp_params = \
            ['omsl', 'tmsl'] + \
            ['mode'] + \
            input_names + \
            ['results']
        vector_dtype = np.float32
        mode_data_type = np.int32
        scalar_names = ['ObsMSL', 'TarMSL']
        mode_vector_name = 'A_mode'
        result_vector_name = 'AIO_re'
        input_vector_names = [f'AIO_{x}' for x in input_names]
        io_vector_names = input_vector_names + [result_vector_name]
        vector_names = {
            mode_data_type: [mode_vector_name],
            vector_dtype: io_vector_names,
        }

        talos_params = \
            scalar_names + \
            vector_names[mode_data_type] + \
            vector_names[vector_dtype]

        d = {k1: getattr(self, k0) for k0, k1 in
             zip(vp_params, talos_params)}

        for name in scalar_names:
            if isinstance(d[name], Sequence):
                d[name] = d[name][0]

        if d[mode_vector_name] is None:
            d[mode_vector_name] = np.array([RadioCalcType.PathLoss], dtype=mode_data_type)
        elif not isinstance(d[mode_vector_name], np.ndarray):
            if isinstance(d[mode_vector_name], (tuple, list)):
                d[mode_vector_name] = [RadioCalcType[x] for x in d[mode_vector_name]]

        for data_type, names in vector_names.items():
            for x in names:
                arr = d[x]
                if arr is not None and not isinstance(arr, np.ndarray):
                    d[x] = np.array(list(arr), dtype=data_type)

        mode_len = len(d[mode_vector_name])
        input_dim = len(input_vector_names)
        res_len = max(len(d[x]) for x in input_vector_names)
        min_res_shape = (mode_len, res_len)

        res_vec = d[result_vector_name]
        res_shape = None if res_vec is None else res_vec.shape
        if res_shape is None or res_shape[0] < min_res_shape[0] or res_shape[1] < min_res_shape[1]:
            res_vec = np.zeros(min_res_shape, dtype=vector_dtype)
            assert min_res_shape == res_vec.shape
        d[result_vector_name] = res_vec

        io_vector_prefixes = input_names + ['re']
        for idx, x in enumerate(io_vector_prefixes):
            d[f'count_{x}'] = len(d[f'AIO_{x}'])
            d[f'offset_{x}'] = 0
            d[f'scanline_{x}'] = 1
        d['results_stride'] = d[f'count_re'] = res_vec.shape[1]

        return d


class ViewshedParams(LOSParams):
    __slots__ = ('max_r', 'min_r', 'min_r_shave', 'max_r_slant',
                 'azimuth', 'h_aperture', 'elevation', 'v_aperture',
                 'vv', 'iv', 'ov', 'ndv', 'out_res')

    def __init__(self):
        super().__init__()

        self.min_r = 0
        self.max_r = None

        self.min_r_shave = False
        self.max_r_slant = True

        self.azimuth = 0
        self.h_aperture = 360
        self.elevation = 0
        self.v_aperture = 180

        self.vv = viewshed_visible
        self.iv = viewshed_invisible
        self.ov = viewshed_out_of_range
        self.ndv = viewshed_ndv

        self.out_res = None

    def is_omni_h(self):
        return not self.h_aperture or abs(self.h_aperture - 360) < 0.0001

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

        if d['mode'] is None:
            d['mode'] = 2
        elif isinstance(d['mode'], str):
            d['mode'] = int(d['mode'])

        return d

    def get_result_dt(self):
        return gdal.GDT_Int16 if self.is_radio() or self.is_calc_oz() or self.is_calc_tz() else gdal.GDT_Byte

    def get_as_talos_params(self) -> dict:
        vp_params = \
            'ox', 'oy', 'oz', 'max_r', 'min_r', 'min_r_shave', 'max_r_slant', 'tz', \
            'omsl', 'tmsl', 'azimuth', 'h_aperture', 'elevation', 'v_aperture', 'out_res'

        talos_params = \
            'ox', 'oy', 'oz', 'MaxRange', 'MinRange', 'MinRangeShave', 'SlantRange', 'tz', \
            'ObsMSL', 'TarMSL', 'Direction', 'Aperture', 'Elevation', 'ElevationAperture', 'out_res'
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
