from gdalos.talos.util import NormalizeAngleDeg
from gdalos.talos.gen_consts import M_PI_180, M_2PI


def GetFromToAngle(DirectionDeg, ApertureDeg: float) -> (float, float):
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

