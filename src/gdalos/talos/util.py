import math


def c_mod(a: int, n: int) -> int:
    return a % n if a >= 0 else a % n - n


def NormalizeAngle(Angle: float, FullCircle: int) -> float:
    if (Angle >= 0) and (Angle < FullCircle):
        ang = Angle
    else:
        TruncAng = math.trunc(Angle)
        ang = (TruncAng % FullCircle) + Angle - TruncAng
        # mod function is different between python and C. thus the following C code is redundant in python
        # if Angle < 0:
        #     ang = FullCircle + ang
    return ang


def NormalizeAngleDeg(Angle: float) -> float:
    return NormalizeAngle(Angle, 360)
