from numbers import Real

from osgeo import osr, ogr


def get_floats(s):
    # get all floats from a string
    lst = []
    for t in s.split():
        try:
            lst.append(float(t))
        except ValueError:
            pass


def get_float(s):
    # get first float from a string
    res = None
    for t in s.split():
        try:
            res = float(t)
            return res
        except ValueError:
            pass
    return res


def get_number(x):
    if isinstance(x, Real):
        return x
    try:
        val = int(x)
        return val
    except (ValueError, TypeError):
        try:
            val = float(x)
            return val
        except (ValueError, TypeError):
            return None
    # f = float(x)
    # if f.is_integer():
    #     return int(f)
    # else:
    #     return f


def get_zone_from_name(s):
    split_string = s.lower().rsplit("u", 1)
    c = len(split_string)
    if c == 2:
        s = split_string[1]
    elif c != 0:
        return 0
    zone = get_number(s)
    if zone is None:
        return 0
    return zone


def get_zone_center(float_zone):
    zone_center = (float_zone - 30.5) * 6  # == (i-30.5)*6*pi/180
    if zone_center <= -180:
        zone_center += 360
    elif zone_center > 180:
        zone_center -= 360
    return zone_center


def get_canonic_name(datum, zone):
    if isinstance(datum, str) and datum[0].lower() == "e":
        res = "e50"
    else:
        res = "w84"
    if zone != 0:
        res = res + "u" + str(zone)
    else:
        res = res + "geo"
    return res


def get_utm_zone_extent_points(float_zone, width=10):
    zone_center = get_zone_center(float_zone)
    x_arr = [zone_center - width / 2.0, zone_center + width / 2.0]
    y_arr = [-80, 80]

    extent_points = []
    for x in x_arr:
        for y in y_arr:
            extent_points.append([x, y])
        y_arr.reverse()
    return extent_points


def get_srs_pj_from_ds(ds):
    srs = osr.SpatialReference()
    srs.ImportFromWkt(ds.GetProjection())
    srs_pj4 = srs.ExportToProj4()
    return srs_pj4


def get_srs_pj_from_epsg(epsg=4326):
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    srs_pj4 = srs.ExportToProj4()
    return srs_pj4


def proj_is_equivalent(pj1, pj2):
    if pj1 == pj2:
        return True
    srs1 = osr.SpatialReference()
    srs1.ImportFromProj4(pj1)

    srs2 = osr.SpatialReference()
    srs2.ImportFromProj4(pj2)

    return srs1.IsSame(srs2)


def _srs(srs):
    if isinstance(srs, str):
        srs_ = osr.SpatialReference()
        if srs_.ImportFromProj4(srs) != ogr.OGRERR_NONE:
            raise Exception("ogr error when parsing srs")
        srs = srs_
    return srs


def reproject_coordinates(coords, src_srs, tgt_srs):
    src_srs = _srs(src_srs)
    tgt_srs = _srs(tgt_srs)

    transform = osr.CoordinateTransformation(src_srs, tgt_srs)
    return [transform.TransformPoint(src_x, src_y)[:2] for src_x, src_y in coords]


def get_transform(src_srs, tgt_srs):
    src_srs = _srs(src_srs)
    tgt_srs = _srs(tgt_srs)
    if src_srs.IsSame(tgt_srs):
        return None
    else:
        return osr.CoordinateTransformation(src_srs, tgt_srs)


def get_proj_string(talos_pj, zone=None, **kwargs):
    pj_string, _ = parse_proj_string_and_zone(talos_pj, zone, **kwargs)
    return pj_string


def parse_proj_string_and_zone(talos_pj, zone=None, ED50_towgs84="-87,-98,-121"):
    # r'+proj=tmerc +k=0.9996 +lon_0={} +x_0=500000 +datum=WGS84 +units=m +no_defs'
    # r'+proj=tmerc +k=0.9996 +lon_0={} +x_0=500000 +ellps=intl +towgs84=x,y,z +units=m +no_defs'
    #
    # r'+proj=utm +zone={} +datum=WGS84 +units=m +no_defs'
    # r'+proj=utm +zone={} +ellps=intl +towgs84=x,y,z +units=m +no_defs'
    #
    # r'+proj=latlong +datum=WGS84 +no_defs'
    # r'+proj=latlong +ellps=intl +towgs84=x,y,z +no_defs'

    pj_string = None
    if zone is None:
        number = get_number(talos_pj)
        if number is not None:
            if isinstance(number, int) and number > 100:
                pj_string = '+init=epsg:{}'.format(number)
            else:
                zone = number
        else:
            zone = get_zone_from_name(talos_pj)

    if not pj_string:
        if isinstance(talos_pj, str):
            if talos_pj.startswith("+"):
                pj_string = talos_pj
            elif talos_pj.lower().startswith("epsg"):
                pj_string = '+init=' + talos_pj

    if not pj_string:
        isGeo = zone is None or (zone <= 0)
        if isGeo:
            pj_string = r"+proj=latlong"
        elif float(zone).is_integer():
            pj_string = r"+proj=utm +zone={}".format(zone)
        else:
            pj_string = r"+proj=tmerc +k=0.9996 +lon_0={} +x_0=500000".format(get_zone_center(zone))
        if isinstance(talos_pj, str) and talos_pj[0].lower() == "e":
            pj_string = pj_string + " +ellps=intl +towgs84=" + ED50_towgs84
        else:
            pj_string = pj_string + " +datum=WGS84"
        if not isGeo:
            pj_string = pj_string + " +units=m"
        pj_string = pj_string + " +no_defs"

    return pj_string, zone

