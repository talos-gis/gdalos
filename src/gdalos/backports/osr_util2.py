from osgeo_utils.auxiliary.osr_util import AnySRS
from gdalos.projdef import get_srs


def get_srs_pj(srs: AnySRS) -> str:
    srs = get_srs(srs)
    srs_pj4 = srs.ExportToProj4()
    return srs_pj4


def are_srs_equivalent(srs1: AnySRS, srs2: AnySRS) -> bool:
    if srs1 == srs2:
        return True
    srs1 = get_srs(srs1)
    srs2 = get_srs(srs2)
    return srs1.IsSame(srs2)
