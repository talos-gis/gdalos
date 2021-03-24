# calc_type
from collections import Sequence
from enum import IntEnum

from gdalos import gdalos_base


class RadioCalcType(IntEnum):
    FOS = 0
    TerrainElev = 1
    ElevationAngleCalc = 2

    FreeSpaceLoss = 10
    PathLoss = 11
    NonFreeSpaceLoss = 12
    PowerReminder = 13
    Clearance = 14
    Mode = 15


class RadioPolarity(IntEnum):
    Horizontal = 0
    Vertical = 1


class RadioParams(object):
    __slots__ = ('frequency', 'KFactor', 'polarity', 'calc_type',
                 'refractivity', 'conductivity', 'permittivity', 'humidity',
                 'power_diff', 'fill_center', 'profile_extension')

    def __init__(self):
        self.frequency = 3333.0
        self.KFactor = 0
        self.polarity = RadioPolarity.Horizontal
        self.calc_type = RadioCalcType.PathLoss

        self.refractivity = 333.0
        self.conductivity = 3.0
        self.permittivity = 33.0
        self.humidity = 33.0

        self.power_diff = 100  # BroadcastPower - MinPower
        self.fill_center = True
        self.profile_extension = True

    def unsequence(self):
        for attr in self.__slots__:
            val = getattr(self, attr)
            if isinstance(val, Sequence):
                setattr(self, attr, val[0])

    def get_dict(self):
        d = gdalos_base.get_dict(self)
        polarity = d['polarity']
        if isinstance(polarity, str):
            polarity = polarity[0].lower()
            polarity = RadioPolarity.Vertical if polarity in ['v', int(RadioPolarity.Vertical)] else RadioPolarity.Horizontal
            d['polarity'] = polarity
        if isinstance(d['calc_type'], str):
            d['calc_type'] = RadioCalcType[d['calc_type']]
        return d

