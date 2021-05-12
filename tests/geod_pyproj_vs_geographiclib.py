import timeit
from typing import Union
import numpy as np
from geographiclib.geodesic import Geodesic
from pyproj import Geod

g_dict = dict()


def get_g(ellps: str) -> Geod:
    global g_dict
    ellps = ellps.upper()
    g = g_dict.get(ellps)
    if g is None:
        if ellps == '':
            g = Geodesic.WGS84
        else:
            g = Geod(ellps=ellps)
        g_dict[ellps] = g
    return g


def get_inv(g: Union[Geod, str], vectorize: bool):
    if isinstance(g, str):
        g = g.upper()
        g = get_g(ellps=g)

    if not vectorize:
        return g.inv
    else:
        vectorized_inv = np.vectorize(g.inv)
    return vectorized_inv


def inv(g: Union[Geod, Geodesic], lons1: np.ndarray, lats1: np.ndarray, lons2: np.ndarray, lats2: np.ndarray, method: int = 2):
    # method = abs(method)
    if isinstance(g, Geodesic):
        az12 = np.empty_like(lons1)
        az21 = np.empty_like(lons1)
        s12 = np.empty_like(lons1)

        for idx, lonlatlonlat in enumerate(zip(lons1, lats1, lons2, lats2)):
            res = g.Inverse(lonlatlonlat[1], lonlatlonlat[0], lonlatlonlat[3], lonlatlonlat[2])
            # https://www.nwcg.gov/course/ffm/location/63-back-azimuth-and-backsighting#:~:text=A%20back%20azimuth%20is%20calculated,%2B%2030%C2%B0%20%3D%20210%C2%B0.
            # A back azimuth is calculated by adding 180° to the azimuth when the azimuth is less than 180°,
            # or by subtracting 180° from the azimuth if it is more than 180°.
            # For example, if an azimuth is 320°, the back azimuth would be 320° - 180° = 140°.
            # If the azimuth is 30°, the back azimuth would be 180° + 30° = 210°.
            _az21 = res['azi2']
            _az21 = _az21 + 180 if _az21 < 0 else _az21 - 180  # calc azi12 (back azimuth)
            az12[idx], az21[idx], s12[idx] = res['azi1'], _az21, res['s12']
    elif method == 0:
        az12, az21, s12 = g.inv(lons1, lats1, lons2, lats2)
    elif method == 1:
        vectorized_inv = np.vectorize(g.inv)
        az12, az21, s12 = vectorized_inv(lons1, lats1, lons2, lats2)
    else:
        az12 = np.empty_like(lons1)
        az21 = np.empty_like(lons1)
        s12 = np.empty_like(lons1)

        for idx, lonlatlonlat in enumerate(zip(lons1, lats1, lons2, lats2)):
            az12[idx], az21[idx], s12[idx] = g.inv(*lonlatlonlat)

    return az12, az21, s12


def tests_setup(g: Union[Geod, str], bench_count=1):
    boston_lat = 42. + (15. / 60.)
    boston_lon = -71. - (7. / 60.)
    portland_lat = 45. + (31. / 60.)
    portland_lon = -123. - (41. / 60.)
    newyork_lat = 40. + (47. / 60.)
    newyork_lon = -73. - (58. / 60.)
    # 40.712740°N 74.005974°W
    newyork2_lat = 40.712740
    newyork2_lon = -74.005974
    london_lat = 51. + (32. / 60.)
    london_lon = -(5. / 60.)

    lons1 = 4 * [newyork_lon]
    lats1 = 4 * [newyork_lat]
    lons2 = [newyork2_lon, boston_lon, portland_lon, london_lon]
    lats2 = [newyork2_lat, boston_lat, portland_lat, london_lat]

    p1_lat = -41.32
    p1_lon = 174.81
    p2_lat = 40.96
    p2_lon = -5.50

    lons1.append(p1_lon)
    lats1.append(p1_lat)
    lons2.append(p2_lon)
    lats2.append(p2_lat)

    lons1 = np.array(lons1 * bench_count)
    lats1 = np.array(lats1 * bench_count)
    lons2 = np.array(lons2 * bench_count)
    lats2 = np.array(lats2 * bench_count)

    # inv_func = get_inv(g, vectorize)
    if isinstance(g, str):
        g = get_g(ellps=g)

    return g, lons1, lats1, lons2, lats2


def test(method, *args):
    return inv(*args, method=method)


if __name__ == '__main__':
    do_time = False
    bench_count = 1
    repeat_count = 10
    ellps = 'WGS84'
    method = 0
    if method is None:
        ellps = ''
    if do_time:
        t = timeit.timeit(
            'test(method, *args)',
            setup='from __main__ import test, tests_setup, ellps, method, bench_count; args = tests_setup(ellps, bench_count)',
            number=repeat_count)
        print(t)
    else:
        print('az12, az21, s12')
        args = tests_setup('WGS84', bench_count)
        res1 = test(method, *args)
        print('proj')
        print(*res1)

        args = tests_setup('', bench_count)
        res2 = test(method, *args)
        print('geoglib')
        print(*res2)

        d = []
        for r0, r1 in zip (res1, res2):
            d.append(r0-r1)
        print('diff')
        print(d)

