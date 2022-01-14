import numpy as np
from pyproj import Proj

from gdalos.talos.gen_consts import M_PI_180


# https://en.wikipedia.org/wiki/Transverse_Mercator_projection#Convergence
# https://gis.stackexchange.com/questions/115531/calculating-grid-convergence-true-north-to-grid-north
# DeltaAzimuthGeoToUTM
# grid_azimuth = true_azimuth - convergence
# Covergency is the difference in angle between True north and Grid north
def get_zone_lon0(zone: float) -> float:
    zone_lon0 = ((zone - 31) * 6 + 3)
    return zone_lon0


def utm_convergence_old(lon, lat: float, zone_lon0: float) -> float:
    delta = ((lon - zone_lon0) * np.sin(lat * M_PI_180)) * M_PI_180
    return delta


def utm_convergence(lon, lat: float, zone_lon0: float) -> float:
    p = Proj(proj='tmerc', k=0.9996, lon_0=zone_lon0, x_0=500000, ellps='WGS84', preserve_units=False)
    factors = p.get_factors(longitude=lon, latitude=lat)
    return factors.meridian_convergence
