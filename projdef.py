def get_floats(s):
    # get all floats from a string
    l = []
    for t in s.split():
        try:
            l.append(float(t))
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


def get_zone_from_name(s):
    split_string = s.lower().rsplit('u', 1)
    if len(split_string) != 2:
        return 0
    f = float(split_string[1])
    if f.is_integer():
        return int(f)
    else:
        return f


def get_zone_center(float_zone):
    zone_center = (float_zone - 30.5) * 6  # == (i-30.5)*6*pi/180
    if zone_center <= -180:
        zone_center += 360
    elif zone_center > 180:
        zone_center -= 360
    return zone_center


def get_canonic_name(datum, zone):
    if datum[0].lower() != 'e':
        res = 'w84'
    else:
        res = 'e50'
    if zone != 0:
        res = res + 'u' + str(zone)
    else:
        res = res + 'geo'
    return res


def get_utm_zone_extent_points(float_zone, width=8):
    zone_center = get_zone_center(float_zone)
    x_arr = [zone_center - width / 2.0, zone_center + width / 2.0]
    y_arr = [-90, 90]

    extent_points = []
    for x in x_arr:
        for y in y_arr:
            extent_points.append([x, y])
        y_arr.reverse()
    return extent_points


ED50_towgs84 = '-87,-98,-121'


def get_proj4_string(datum, zone=None):
    # r'+proj=tmerc +k=0.9996 +lon_0={} +x_0=500000 +datum=WGS84 +units=m +no_defs'
    # r'+proj=tmerc +k=0.9996 +lon_0={} +x_0=500000 +ellps=intl +towgs84=x,y,z +units=m +no_defs'
    #
    # r'+proj=utm +zone={} +datum=WGS84 +units=m +no_defs'
    # r'+proj=utm +zone={} +ellps=intl +towgs84=x,y,z +units=m +no_defs'
    #
    # r'+proj=latlong +datum=WGS84 +no_defs'
    # r'+proj=latlong +ellps=intl +towgs84=x,y,z +no_defs'

    isGeo = zone is None or (zone <= 0)
    if isGeo:
        result = r'+proj=latlong'
    elif float(zone).is_integer():
        result = r'+proj=utm +zone={}'.format(zone)
    else:
        result = r'+proj=tmerc +k=0.9996 +lon_0={} +x_0=500000'.format(get_zone_center(zone))
    if datum[0].lower() != 'e':
        result = result + ' +datum=WGS84'
    else:
        result = result + ' +ellps=intl +towgs84=' + ED50_towgs84
    if not isGeo:
        result = result + ' +units=m'
    result = result + ' +no_defs'
    return result