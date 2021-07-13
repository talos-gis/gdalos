import numpy as np
from typing import Tuple, Union

from gdalos.talos.gen_consts import M_PI_180, M_2PI

FloatOrArr = Union[float, np.ndarray]


def c_mod(a: int, n: int) -> int:
    return a % n if a >= 0 else a % n - n


def Frac(x: FloatOrArr) -> FloatOrArr:
    return x - np.trunc(x)


def NormalizeAngleI(Angle: float, FullCircle: int) -> float:
    if (Angle >= 0) and (Angle < FullCircle):
        ang = Angle
    else:
        TruncAng = np.trunc(Angle)
        ang = (TruncAng % FullCircle) + Angle - TruncAng
        # mod function is different between python and C. thus the following C code is redundant in python
        # if Angle < 0:
        #     ang = FullCircle + ang
    return ang


def NormalizeAngle(Angle: FloatOrArr, FullCircle: float = 360) -> FloatOrArr:
    Result = Angle
    if isinstance(Angle, np.ndarray):
        Result = Frac(Result / FullCircle)
        Result[Result < 0] += 1
        Result *= FullCircle
        # Result[Result < 0] = (Frac(Result / FullCircle) + 1) * FullCircle
        # Result[Result >= FullCircle] = (Frac(Result / FullCircle)) * FullCircle
    else:
        if Result < 0:
            Result = (Frac(Result / FullCircle) + 1) * FullCircle
        if Result >= FullCircle:
            Result = (Frac(Result / FullCircle)) * FullCircle
    return Result


def NormalizeAngleDeg(Angle: FloatOrArr) -> FloatOrArr:
    return NormalizeAngle(Angle, 360)


def NormalizeAngles(startAz: FloatOrArr, endAz: FloatOrArr, FullCircle: float = 360) -> Tuple[FloatOrArr, FloatOrArr]:
    s = NormalizeAngle(startAz, FullCircle)
    e = NormalizeAngle(endAz, FullCircle)
    if isinstance(s, np.ndarray):
        idx = e < s
        e[idx] = e[idx] + FullCircle
    elif e < s:
        e = e + FullCircle
    return s, e


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


def direction_and_aperture_from_az(
        startAz: FloatOrArr, endAz: FloatOrArr,
        FullCircle: float = 0) -> Tuple[FloatOrArr, FloatOrArr]:
    if FullCircle:
        startAz, endAz = NormalizeAngles(startAz, endAz, FullCircle)
    return (endAz + startAz) / 2, endAz - startAz


if __name__ == '__main__':
    c = 360
    for x in (-1.5*c, -1*c, -0.5*c, 0, 0.5*c, 1*c, 1.5*c, 2*c, 2.5*c):
        x = NormalizeAngle(x, c)
        y = NormalizeAngleI(x, c)
        assert abs(x-y) < 0.01*c
    print('success')
