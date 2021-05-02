from numbers import Real
from typing import Optional, Tuple, Union

from gdalos.backports.osr_utm_util import proj_string_from_utm_zone
from osgeo_utils.auxiliary.base import num_or_none


def get_zone_from_name(s: str) -> Real:
    split_string = s.lower().rsplit('u', 1)
    c = len(split_string)
    if c == 2:
        s = split_string[1]
    elif c != 0:
        return 0
    zone = num_or_none(s)
    if zone is None:
        return 0
    return zone


def get_canonic_name(datum: str, zone: Real) -> str:
    if isinstance(datum, str) and datum[0].lower() == "e":
        res = "e50"
    else:
        res = "w84"
    if zone:
        res = res + "u" + ('0' if zone<10 else '') + str(zone)
    else:
        res = res + "geo"
    return res


def parse_proj_string_and_zone(talos_pj: Optional[Union[str, Real]], zone: Optional[Real] = None,
                               ED50_towgs84='-87,-98,-121') -> Tuple[str, Real]:
    # '+proj=tmerc +k=0.9996 +lon_0={} +x_0=500000 +datum=WGS84 +units=m +no_defs'
    # '+proj=tmerc +k=0.9996 +lon_0={} +x_0=500000 +ellps=intl +towgs84=x,y,z +units=m +no_defs'
    #
    # '+proj=utm +zone={} +datum=WGS84 +units=m +no_defs'
    # '+proj=utm +zone={} +ellps=intl +towgs84=x,y,z +units=m +no_defs'
    #
    # '+proj=latlong +datum=WGS84 +no_defs'
    # '+proj=latlong +ellps=intl +towgs84=x,y,z +no_defs'

    pj_string = None
    if zone is None:
        number = num_or_none(talos_pj)
        if number is not None:
            if isinstance(number, int) and number > 100:
                pj_string = '+init=epsg:{}'.format(number)
            else:
                zone = number
        else:
            zone = get_zone_from_name(talos_pj)

    if pj_string is None and isinstance(talos_pj, str):
        if talos_pj.startswith('+'):
            pj_string = talos_pj
        elif talos_pj.lower().startswith('epsg'):
            pj_string = '+init=' + talos_pj

    if pj_string is None:
        if isinstance(talos_pj, str) and talos_pj[0].lower() == 'e':
            datum_str = '+ellps=intl +towgs84=' + ED50_towgs84
        else:
            datum_str = '+datum=WGS84'
        pj_string = proj_string_from_utm_zone(zone=zone, datum_str=datum_str)

    return pj_string, zone


def get_proj_string(talos_pj: Optional[Union[str, Real]], zone: Optional[Real] = None, **kwargs):
    pj_string, _ = parse_proj_string_and_zone(talos_pj, zone, **kwargs)
    return pj_string
