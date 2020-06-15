import math


def NormalizeAngle(Angle: float, FullCircle: int) -> float:
    if (Angle >= 0) and (Angle < FullCircle):
        ang = Angle
    else:
        TruncAng = math.trunc(Angle)
        if Angle < 0:
            ang = FullCircle + (TruncAng % FullCircle) + Angle - TruncAng
        else:
            ang = (TruncAng % FullCircle) + Angle - TruncAng
    return ang


def NormalizeAngleDeg(Angle: float) -> float:
    return NormalizeAngle(Angle, 360)
