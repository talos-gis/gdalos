import itertools
import math
from collections import namedtuple
from enum import IntFlag
from typing import Union, List, Tuple, Sequence, Any
import numpy as np
from pyproj import Geod as OldGeod
from numpy.testing import assert_almost_equal


GeodIntermediateReturn = namedtuple(
    "GeodIntermediateReturn", ["npts", "del_s", "dist", "lons", "lats", "azis"]
)


class GeodIntermediateFlag(IntFlag):
    """
    .. versionadded:: 3.1.0

    Flags to be used in Geod.[inv|fwd]_intermediate()
    """

    DEFAULT = 0x0

    NPTS_MASK = 0xF
    NPTS_ROUND = 0x0
    NPTS_CEIL = 0x1
    NPTS_TRUNC = 0x2

    DEL_S_MASK = 0xF0
    DEL_S_RECALC = 0x00
    DEL_S_NO_RECALC = 0x10

    AZIS_MASK = 0xF00
    AZIS_DISCARD = 0x000
    AZIS_KEEP = 0x100


class Geod(OldGeod):
    def npts(
        self,
        lon1: float,
        lat1: float,
        lon2: float,
        lat2: float,
        npts: int,
        radians: bool = False,
        initial_idx: int = 1,
        terminus_idx: int = 1,
        return_points: bool = True,
    ) -> Union[List[Tuple[float, float]], Tuple[Sequence[float], Sequence[float]]]:

        include_initial = bool(not initial_idx)
        include_terminus = bool(not terminus_idx)
        lons, lats = super()._npts(lon1, lat1, lon2, lat2,
                                   npts - int(include_terminus) - int(include_initial), radians=radians)
        if include_initial:
            if include_terminus:
                lons = (lon1, *lons, lon2)
                lats = (lat1, *lats, lat2)
            else:
                lons = (lon1, *lons)
                lats = (lat1, *lats)
        elif include_terminus:
            lons = (*lons, lon2)
            lats = (*lats, lat2)

        return list(zip(lons, lats)) if return_points else (lons, lats)

    def inv_intermediate(
        self,
        lon1: float,
        lat1: float,
        lon2: float,
        lat2: float,
        npts: int = 0,
        del_s: float = 0,
        initial_idx: int = 1,
        terminus_idx: int = 1,
        radians: bool = False,
        flags: GeodIntermediateFlag = GeodIntermediateFlag.DEFAULT,
        out_lons: Any = None,
        out_lats: Any = None,
        out_azis: Any = None,
    ) -> GeodIntermediateReturn:
        flags = int(flags)
        az12, az21, s13 = self.inv(lons1=lon1, lats1=lat1, lons2=lon2, lats2=lat2, radians=radians)
        if npts == 0:
            # calc the number of required points by the distance increment
            s12 = s13 / del_s - initial_idx - terminus_idx + 1
            # using the flags:
            # 1st byte: round(0)/ceil(1)/trunc(2)
            # 2nd byte: update del_s to the new npts (0) or not (1)

            if (flags & GeodIntermediateFlag.NPTS_MASK) == \
                    GeodIntermediateFlag.NPTS_ROUND:
                s12 = round(s12)
            elif (flags & GeodIntermediateFlag.NPTS_MASK) == \
                    GeodIntermediateFlag.NPTS_CEIL:
                s12 = math.ceil(s12)
            npts = int(s12)
        if (flags & GeodIntermediateFlag.DEL_S_MASK) == GeodIntermediateFlag.DEL_S_RECALC:
            # calc the distance increment by the number of required points
            del_s = s13 / (npts + initial_idx + terminus_idx - 1)

        lons, lats = \
            self.npts(lon1=lon1, lat1=lat1, lon2=lon2, lat2=lat2, npts=npts, radians=radians,
                      initial_idx=initial_idx, terminus_idx=terminus_idx, return_points=False)
        if del_s == 0:
            _az12, _az21, del_s = self.inv(lons1=lons[0], lats1=lats[0], lons2=lons[1], lats2=lats[1], radians=radians)

        ind = list(range(npts))
        if out_lons is None:
            out_lons = np.array(lons)
        else:
            np.put(out_lons, ind=ind, v=lons)
        if out_lats is None:
            out_lats = np.array(lats)
        else:
            np.put(out_lats, ind=ind, v=lats)

        # _az12, _az21, del_s = self.inv(lons1=lons[0], lats1=lats[0], lons2=lons[1], lats2=lats[1], radians=radians)

        return GeodIntermediateReturn(len(lons), del_s, s13, out_lons, out_lats, None)

    def fwd_intermediate(
        self,
        lon1: float,
        lat1: float,
        azi1: float,
        npts: int,
        del_s: float,
        initial_idx: int = 1,
        terminus_idx: int = 1,
        radians: bool = False,
        flags: GeodIntermediateFlag = GeodIntermediateFlag.DEFAULT,
        out_lons: Any = None,
        out_lats: Any = None,
        out_azis: Any = None,
    ) -> GeodIntermediateReturn:

        s13 = del_s * (npts + initial_idx + terminus_idx - 1)
        lon2, lat2, az21 = self.fwd(lons=lon1, lats=lat1, az=azi1, dist=s13, radians=radians)

        return self.inv_intermediate(
            lon1=lon1, lat1=lat1, lon2=lon2, lat2=lat2, npts=npts, del_s=del_s,
            initial_idx=initial_idx, terminus_idx=terminus_idx, radians=radians,
            flags=flags, out_lons=out_lons, out_lats=out_lats, out_azis=out_azis)


def test_geod_inverse_transform():
    gg = Geod(ellps="clrk66")
    lat1pt = 42.0 + (15.0 / 60.0)
    lon1pt = -71.0 - (7.0 / 60.0)
    lat2pt = 45.0 + (31.0 / 60.0)
    lon2pt = -123.0 - (41.0 / 60.0)
    """
    distance between boston and portland, clrk66:
    -66.531 75.654  4164192.708
    distance between boston and portland, WGS84:
    -66.530 75.654  4164074.239
    testing pickling of Geod instance
    distance between boston and portland, clrk66 (from pickle):
    -66.531 75.654  4164192.708
    distance between boston and portland, WGS84 (from pickle):
    -66.530 75.654  4164074.239
    inverse transform
    from proj.4 invgeod:
    b'-66.531\t75.654\t4164192.708\n'

    """
    true_az12 = -66.5305947876623
    true_az21 = 75.65363415556968
    print("from pyproj.Geod.inv:")
    az12, az21, dist = gg.inv(lon1pt, lat1pt, lon2pt, lat2pt)
    assert_almost_equal(
        (az12, az21, dist), (true_az12, true_az21, 4164192.708), decimal=3
    )

    print("forward transform")
    print("from proj.4 geod:")
    endlon, endlat, backaz = gg.fwd(lon1pt, lat1pt, az12, dist)
    assert_almost_equal(
        (endlon, endlat, backaz), (lon2pt, lat2pt, true_az21), decimal=3
    )

    inc_exc = ["excluding", "including"]
    res_az12_az21_dists_all = [
        (180.0, 0.0, 0.0),
        (-66.53059478766238, 106.79071710136431, 832838.5416198927),
        (-73.20928289863558, 99.32289055927389, 832838.5416198935),
        (-80.67710944072617, 91.36325611787134, 832838.5416198947),
        (-88.63674388212858, 83.32809401477382, 832838.5416198922),
        (-96.67190598522616, 75.65363415556973, 832838.5416198926),
    ]
    point_count = len(res_az12_az21_dists_all)
    for include_initial, include_terminus in itertools.product(
        (False, True), (False, True)
    ):
        initial_idx = int(not include_initial)
        terminus_idx = int(not include_terminus)

        npts = point_count - initial_idx - terminus_idx
        print("intermediate points:")
        print("from geod with +lat_1,+lon_1,+lat_2,+lon_2,+n_S:")
        print(f"{lat1pt:6.3f} {lon1pt:7.3f} {lat2pt:6.3f} {lon2pt:7.3f} {npts}")

        lonlats = gg.npts(
            lon1pt,
            lat1pt,
            lon2pt,
            lat2pt,
            npts,
            initial_idx=initial_idx,
            terminus_idx=terminus_idx,
        )
        assert len(lonlats) == npts

        npts1 = npts + initial_idx + terminus_idx - 1
        del_s = dist / npts1
        print(
            f"Total distnace is {dist}, "
            f"Points count: {npts}, "
            f"{inc_exc[include_initial]} initial point, "
            f"{inc_exc[include_terminus]} terminus point. "
            f"The distance between successive points is {dist}/{npts1} = {del_s}"
        )

        from_idx = initial_idx
        to_idx = point_count - terminus_idx
        res_az12_az21_dists = res_az12_az21_dists_all[from_idx:to_idx]

        lonprev = lon1pt
        latprev = lat1pt
        for (lon, lat), (res12, res21, resdist) in zip(lonlats, res_az12_az21_dists):
            o_az12, o_az21, o_dist = gg.inv(lonprev, latprev, lon, lat)
            assert_almost_equal((o_az12, o_az21, o_dist), (res12, res21, resdist))
            latprev = lat
            lonprev = lon
        if not include_terminus:
            o_az12, o_az21, o_dist = gg.inv(lonprev, latprev, lon2pt, lat2pt)
            assert_almost_equal(
                (lat2pt, lon2pt, o_dist), (45.517, -123.683, 832838.542), decimal=3
            )

        if include_initial and include_terminus:
            lons, lats, azis12, azis21, dists = np.hstack(
                (lonlats, res_az12_az21_dists)
            ).transpose()

    del_s = dist / (point_count - 1)
    lons_a = np.empty(point_count)
    lats_a = np.empty(point_count)
    azis_a = np.empty(point_count)

    print("test inv_intermediate (by npts) with azi output")
    res = gg.inv_intermediate(
        out_lons=lons_a,
        out_lats=lats_a,
        out_azis=azis_a,
        lon1=lon1pt,
        lat1=lat1pt,
        lon2=lon2pt,
        lat2=lat2pt,
        npts=point_count,
        initial_idx=0,
        terminus_idx=0,
    )
    assert res.npts == point_count
    assert_almost_equal(res.del_s, del_s)
    assert_almost_equal(res.dist, dist)
    assert_almost_equal(res.lons, lons)
    assert_almost_equal(res.lats, lats)
    # assert_almost_equal(res.azis[:-1], azis12[1:])
    assert res.lons is lons_a
    assert res.lats is lats_a
    # assert res.azis is azis_a

    for flags in (GeodIntermediateFlag.AZIS_DISCARD,):
        print("test inv_intermediate (by npts) without azi output, no buffers")
        res = gg.inv_intermediate(
            lon1=lon1pt,
            lat1=lat1pt,
            lon2=lon2pt,
            lat2=lat2pt,
            npts=point_count,
            initial_idx=0,
            terminus_idx=0,
            flags=flags,
        )
        assert res.npts == point_count
        assert_almost_equal(res.del_s, del_s)
        assert_almost_equal(res.dist, dist)
        assert_almost_equal(res.lons, lons_a)
        assert_almost_equal(res.lats, lats_a)
        if flags == GeodIntermediateFlag.AZIS_DISCARD:
            assert res.azis is None
        else:
            assert_almost_equal(res.azis, azis_a)

        lons_b = np.empty(point_count)
        lats_b = np.empty(point_count)
        azis_b = np.empty(point_count)

        print("test inv_intermediate (by npts) without azi output")
        res = gg.inv_intermediate(
            out_lons=lons_b,
            out_lats=lats_b,
            out_azis=None,
            lon1=lon1pt,
            lat1=lat1pt,
            lon2=lon2pt,
            lat2=lat2pt,
            npts=point_count,
            initial_idx=0,
            terminus_idx=0,
            flags=flags,
        )
        assert res.npts == point_count
        assert_almost_equal(res.del_s, del_s)
        assert_almost_equal(res.dist, dist)
        assert_almost_equal(res.lons, lons_a)
        assert_almost_equal(res.lats, lats_a)
        assert res.lons is lons_b
        assert res.lats is lats_b
        if flags == GeodIntermediateFlag.AZIS_DISCARD:
            assert res.azis is None
        else:
            assert_almost_equal(res.azis, azis_a)

    print("test fwd_intermediate")
    res = gg.fwd_intermediate(
        out_lons=lons_b,
        out_lats=lats_b,
        out_azis=azis_b,
        lon1=lon1pt,
        lat1=lat1pt,
        azi1=true_az12,
        npts=point_count,
        del_s=del_s,
        initial_idx=0,
        terminus_idx=0,
    )
    assert res.npts == point_count
    assert_almost_equal(res.del_s, del_s)
    assert_almost_equal(res.dist, dist)
    assert_almost_equal(res.lons, lons_a)
    assert_almost_equal(res.lats, lats_a)
    # assert_almost_equal(res.azis, azis_a)
    assert res.lons is lons_b
    assert res.lats is lats_b
    # assert res.azis is azis_b

    print("test inv_intermediate (by del_s)")
    for del_s_fact, flags in (
        (1, GeodIntermediateFlag.NPTS_ROUND),
        ((point_count - 0.5) / point_count, GeodIntermediateFlag.NPTS_TRUNC),
        ((point_count + 0.5) / point_count, GeodIntermediateFlag.NPTS_CEIL),
    ):
        res = gg.inv_intermediate(
            out_lons=lons_b,
            out_lats=lats_b,
            out_azis=azis_b,
            lon1=lon1pt,
            lat1=lat1pt,
            lon2=lon2pt,
            lat2=lat2pt,
            del_s=del_s * del_s_fact,
            initial_idx=0,
            terminus_idx=0,
            flags=flags,
        )
        assert res.npts == point_count
        assert_almost_equal(res.del_s, del_s)
        assert_almost_equal(res.dist, dist)
        assert_almost_equal(res.lons, lons_a)
        assert_almost_equal(res.lats, lats_a)
        # assert_almost_equal(res.azis, azis_a)
        assert res.lons is lons_b
        assert res.lats is lats_b
        # assert res.azis is azis_b


if __name__ == '__main__':
    test_geod_inverse_transform()