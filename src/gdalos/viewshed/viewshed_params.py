import math
from itertools import cycle
from typing import Sequence, Optional

import numpy as np
from osgeo import gdal, osr

from gdalos import gdalos_base, projdef
from gdalos.backports.osr_utm_util import utm_convergence
from gdalos.gdalos_base import make_points_list, make_xy_list, FillMode
from gdalos.talos.gen_consts import M_PI_180
from gdalos.viewshed.radio_params import RadioParams, RadioCalcType
from osgeo_utils.auxiliary.util import open_ds
from osgeo_utils.samples.gdallocationinfo import gdallocationinfo, LocationInfoSRS

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
                 'refraction_coeff', 'calc_mode', 'radio_parameters', 'xy_fill', 'ot_fill']

    _scalar_slots = ['omsl', 'tmsl', 'refraction_coeff']
    _vector_slots = ['ox', 'oy', 'tx', 'ty', 'azimuth', 'elevation', 'max_r']

    def __init__(self):
        self.ox = None
        self.oy = None
        self.oz = None
        self.tz = None
        self.omsl = False  # observer MSL
        self.tmsl = False  # target MSL

        self.refraction_coeff = atmospheric_refraction_coeff
        self.calc_mode = None
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

    def fix_scalars_and_vectors(self):
        for attr in self._scalar_slots:
            a = getattr(self, attr)
            if a is not None and isinstance(a, Sequence):
                setattr(self, attr, a[0])
        for attr in self._vector_slots:
            a = getattr(self, attr)
            if a is not None and not isinstance(a, Sequence):
                setattr(self, attr, [a])

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

    def get_radio_as_talos_params(self, index: Optional[int] = None):
        if self.radio_parameters is None:
            return None
        d = self.radio_parameters.get_dict()
        calc_mode = self.calc_mode
        if isinstance(calc_mode, str):
            calc_mode = RadioCalcType[calc_mode]
        d['calc_type'] = calc_mode
        dict_of_selected_items(d, index)
        return d


def all_same(items):
    return all(x == items[0] for x in items)


def dict_of_reduce_if_same(d: dict):
    if d is None:
        return None
    is_multi = False
    for k, v in d.items():
        if isinstance(d[k], Sequence):
            if all_same(d[k]):
                d[k] = d[k][0]
            else:
                is_multi = True
    return is_multi


def dict_of_selected_items(d: dict, index: Optional[int] = None, check_only: bool = False):
    if d is None or (index is None and not check_only):
        return None
    is_multi = False
    for k, v in d.items():
        if isinstance(d[k], Sequence):
            is_multi = True
            if check_only:
                return is_multi
            else:
                d[k] = d[k][index]
    return is_multi


class LOSParams_with_angles(LOSParams):
    __slots__ = ('azimuth', 'elevation', 'max_r', 'convergence')

    _vector_slots = LOSParams._vector_slots + ['azimuth', 'elevation', 'max_r']

    def __init__(self):
        super(LOSParams_with_angles, self).__init__()
        self.azimuth = None
        self.elevation = None
        self.max_r = None
        self.convergence = 0

    def get_grid_azimuth(self):
        return self.azimuth - self.convergence


class MultiPointParams(LOSParams_with_angles):
    __slots__ = ('fwd', 'tx', 'ty', 'azimuth', 'elevation', 'max_r', 'results')

    _scalar_slots = LOSParams_with_angles._scalar_slots + ['fwd']
    _vector_slots = LOSParams_with_angles._vector_slots + ['tx', 'ty']

    g = None

    def __init__(self):
        super(MultiPointParams, self).__init__()
        self.fwd = None  # is fwd calculation True/False/None (yes/no/auto)
        # for inv calculation
        self.tx = None
        self.ty = None
        # for fwd calculation

        self.results = None

    def is_fwd(self):
        return self.fwd if (self.fwd is not None) else (self.tx is None)

    @property
    def txy(self):
        return make_points_list(self.tx, self.ty, self.xy_fill)

    @txy.setter
    def txy(self, txy):
        self.tx, self.ty = make_xy_list(txy)

    def calc_fwd(self, filename_or_ds, ovr_idx):
        self.ox = np.array(self.ox, dtype=np.float32)
        self.oy = np.array(self.oy, dtype=np.float32)
        abs_oz = np.array(self.oz, dtype=np.float32)
        ds = open_ds(filename_or_ds)
        az = np.array(self.get_grid_azimuth(), dtype=np.float32)
        el = np.array(self.elevation, dtype=np.float32)
        r = np.array(self.max_r, dtype=np.float32) if len(self.max_r) == len(el) else np.full_like(el, self.max_r[0])

        a = (90 - az) * M_PI_180
        e = el * M_PI_180
        ground_r = r * np.cos(e)
        self.tmsl = True
        if not self.omsl:
            _pixels, _lines, alts = gdallocationinfo(
                ds, band_nums=1, x=self.ox, y=self.oy, srs=LocationInfoSRS.SameAsDS_SRS,
                inline_xy_replacement=False, ovr_idx=ovr_idx,
                axis_order=osr.OAMS_TRADITIONAL_GIS_ORDER)
            abs_oz = abs_oz + alts

        earth_d = 6378137.0 * 2
        earth_curvature = (1-self.refraction_coeff) / earth_d
        self.tz = abs_oz + r * np.sin(e) + ground_r*ground_r * earth_curvature
        self.tx = self.ox + np.cos(a) * ground_r
        self.ty = self.oy + np.sin(a) * ground_r

    def get_as_talos_params(self):
        input_names = ['ox', 'oy', 'oz', 'tx', 'ty', 'tz']
        vp_params = \
            ['omsl', 'tmsl'] + \
            ['calc_mode'] + \
            input_names + \
            ['results']
        vector_dtype = np.float32
        calc_mode_data_type = np.int32
        scalar_names = ['ObsMSL', 'TarMSL']
        calc_mode_vector_name = 'A_mode'
        result_vector_name = 'AIO_re'  # this vector holds enum values of the requested results
        input_vector_names = [f'AIO_{x}' for x in input_names]
        io_vector_names = input_vector_names + [result_vector_name]
        vector_names = {
            calc_mode_data_type: [calc_mode_vector_name],
            vector_dtype: io_vector_names,
        }

        talos_params = \
            scalar_names + \
            vector_names[calc_mode_data_type] + \
            vector_names[vector_dtype]

        # create a dict that map input param names to the respectable values in self
        d = {k1: getattr(self, k0) for k0, k1 in
             zip(vp_params, talos_params)}

        for name in scalar_names:
            if isinstance(d[name], Sequence):
                d[name] = d[name][0]

        if d[calc_mode_vector_name] is None:
            raise Exception('Calc mode is None')

        for data_type, names in vector_names.items():
            for x in names:
                arr = d[x]
                if arr is not None and not isinstance(arr, np.ndarray):
                    d[x] = np.array(list(arr), dtype=data_type)

        calc_mode_len = len(d[calc_mode_vector_name])
        input_dim = len(input_vector_names)
        res_len = max(len(d[x]) for x in input_vector_names)
        min_res_shape = (calc_mode_len, res_len)

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

    def get_as_rfmodel_params(self, del_s: float) -> dict:
        d = dict(
            count=len(self.ox),
            main_options=dict(
                tx_antenna_height=self.oz,
                rx_antenna_height=self.oz,
                tx_msl=self.omsl,
                rx_msl=self.tmsl,
            ),
            profile_options=dict(lon1=self.ox, lat1=self.oy, lon2=self.tx, lat2=self.ty, del_s=del_s),
            rfmodel_options=self.radio_parameters.as_rfmodel_params(),
        )
        return d


class ViewshedParams(LOSParams_with_angles):
    __slots__ = ('min_r', 'min_r_shave', 'max_r_slant',
                 'h_aperture', 'v_aperture',
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
            'vv', 'iv', 'ov', 'ndv', 'calc_mode'

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
        d['out_res'] = d['out_res'] or 0
        d['result_dt'] = self.get_result_dt()
        d['Direction'] = self.get_grid_azimuth()
        return d


viewshed_defaults = dict(vv=viewshed_visible,
                         iv=viewshed_invisible,
                         ov=viewshed_out_of_range,
                         ndv=viewshed_ndv,
                         )
