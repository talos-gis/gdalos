import math
from typing import Tuple


def c_mod(a: int, n: int) -> int:
    return a % n if a >= 0 else a % n - n


def Frac(x: float) -> float:
    return x - math.trunc(x)


def NormalizeAngleI(Angle: float, FullCircle: int) -> float:
    if (Angle >= 0) and (Angle < FullCircle):
        ang = Angle
    else:
        TruncAng = math.trunc(Angle)
        ang = (TruncAng % FullCircle) + Angle - TruncAng
        # mod function is different between python and C. thus the following C code is redundant in python
        # if Angle < 0:
        #     ang = FullCircle + ang
    return ang


def NormalizeAngle(Angle: float, FullCircle: float = 360) -> float:
    Result = Angle
    if Result < 0:
        Result = (Frac(Result / FullCircle) + 1) * FullCircle
    if Result >= FullCircle:
        Result = (Frac(Result / FullCircle)) * FullCircle
    return Result


def NormalizeAngleDeg(Angle: float) -> float:
    return NormalizeAngle(Angle, 360)


def NormalizeAngles(startAz: float, endAz: float, FullCircle: float = 360) -> Tuple[float, float]:
    s = NormalizeAngle(startAz, FullCircle)
    e = NormalizeAngle(endAz, FullCircle)
    if e < s:
        e = e + FullCircle
    return s, e


if __name__ == '__main__':
    c = 360
    for x in (-1.5*c, -1*c, -0.5*c, 0, 0.5*c, 1*c, 1.5*c, 2*c, 2.5*c):
        x = NormalizeAngle(x, c)
        y = NormalizeAngleI(x, c)
        assert abs(x-y) < 0.01*c
    print('success')
