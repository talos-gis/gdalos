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

viewshed_atmospheric_refraction = 0.85714

viewshed_defaults = dict(vv=viewshed_visible,
                         iv=viewshed_invisible,
                         ov=viewshed_out_of_range,
                         ndv=viewshed_ndv,
                         )

viewshed_params = 'md', 'ox', 'oy', 'oz', 'tz', \
         'vv', 'iv', 'ov', 'ndv', \
         'cc', 'mode'

gdal_viewshed_keys = \
    'maxDistance', 'observerX', 'observerY', 'observerHeight', 'targetHeight', \
    'visibleVal', 'invisibleVal', 'outOfRangeVal', 'noDataVal', \
    'dfCurvCoeff', 'mode'
gdal_viewshed_keymap = dict(zip(viewshed_params, gdal_viewshed_keys))

gdal_viewshed_defaults = dict_util.replace_keys(viewshed_defaults,  gdal_viewshed_keymap)
