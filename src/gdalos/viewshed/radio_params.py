# calc_type
from enum import IntEnum

from gdalos.calc import dict_util


class RadioCalcType(IntEnum):
    PathLoss = 0
    PowerReminder = 1
    PowerReminderBinary = 2
    LOS = 3
    FreeSpaceLoss = 4
    NonFreeSpaceLoss = 5
    Clearance = 6
    Mode = 7


class RadioPolarity(IntEnum):
    Horizontal = 0
    Vertical = 1


class RadioParams(object):
    __slots__ = ['frequency', 'KFactor', 'polarity', 'calc_type',
                 'refractivity', 'conductivity', 'permittivity', 'humidity',
                 'power_diff', 'fill_center', 'profile_extension']

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

    def get_dict(self):
        d = dict_util.get_dict(self)
        polarity = d['polarity']
        if isinstance(polarity, str):
            polarity = polarity[0].lower()
            polarity = RadioPolarity.Vertical if polarity in ['v', int(RadioPolarity.Vertical)] else RadioPolarity.Horizontal
            d['polarity'] = polarity
        if isinstance(d['calc_type'], str):
            d['calc_type'] = RadioCalcType[d['calc_type']]
        return d
