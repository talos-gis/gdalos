from typing import Tuple

from gdalos.talos.util import NormalizeAngleDeg, NormalizeAngles
from gdalos.talos.gen_consts import M_PI_180, M_2PI


def GetFromToAngle(DirectionDeg: float, ApertureDeg: float) -> Tuple[float, float]:
    if ApertureDeg >= 360 - 1e-10:
        AFromRad = 0
        AToRad = 0
    else:
        HeadDir = NormalizeAngleDeg(90 - DirectionDeg)
        AFromRad = NormalizeAngleDeg(HeadDir - ApertureDeg * 0.5) * M_PI_180
        AToRad = NormalizeAngleDeg(HeadDir + ApertureDeg * 0.5) * M_PI_180
        if AFromRad > AToRad:
            AFromRad = AFromRad - M_2PI
    return AFromRad, AToRad


def h_azimuth_and_aperture_from_az(startAz: float, endAz: float, FullCircle: float = 360) -> Tuple[float, float]:
    startAz, endAz = NormalizeAngles(startAz, endAz, FullCircle)
    return (endAz + startAz) / 2, endAz - startAz


def v_elevation_and_aperture_from_az(startAz: float, endAz: float, FullCircle: float = 360) -> Tuple[float, float]:
    startAz, endAz = NormalizeAngles(startAz, endAz, FullCircle)
    return (endAz + startAz) / 2, endAz - startAz
