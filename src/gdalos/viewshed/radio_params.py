from collections import Sequence
from enum import IntEnum
from typing import NamedTuple

from gdalos import gdalos_base


class RadioCalcType(IntEnum):
    FOS = 0
    TerrainElev = 1
    ElevationAngleCalc = 2
    LOSRange = 3
    LOSVisRes = 4

    FreeSpaceLoss = 10
    PathLoss = 11
    NonFreeSpaceLoss = 12
    PowerReminder = 13
    Clearance = 14
    Mode = 15


class RadioPolarity(IntEnum):
    Horizontal = 0
    Vertical = 1


class RadioBaseParams(NamedTuple):
    refractivity: float
    conductivity: float
    permittivity: float
    humidity: float


DefaultRadioBaseParams = RadioBaseParams(refractivity=333.0, conductivity=3.0, permittivity=33.0, humidity=33.0)


class RadioParams(object):
    __slots__ = ('frequency', 'polarity', #'calc_mode',
                 'refractivity', 'conductivity', 'permittivity', 'humidity',
                 'power_diff', 'fill_center', 'profile_extension')

    def __init__(self):
        self.frequency = None
        self.polarity = RadioPolarity.Horizontal
        # self.calc_mode = RadioCalcType.PathLoss

        self.refractivity = None
        self.conductivity = None
        self.permittivity = None
        self.humidity = None

        self.power_diff = 100  # BroadcastPower - MinPower
        self.fill_center = True
        self.profile_extension = True

    def unsequence(self):
        for attr in self.__slots__:
            val = getattr(self, attr)
            if isinstance(val, Sequence):
                setattr(self, attr, val[0])

    def fix_polarization(self):
        if isinstance(self.polarity, str):
            p = self.polarity[0].lower()
            self.polarity = \
                RadioPolarity.Vertical if p in ['v', int(RadioPolarity.Vertical), bool(RadioPolarity.Vertical)] \
                else RadioPolarity.Horizontal
        return self.polarity

    def get_dict(self):
        self.fix_polarization()
        d = gdalos_base.get_dict(self)
        return d

    def as_rfmodel_params(self):
        self.fix_polarization()
        return dict(
            frequency=self.frequency, polarization=self.polarity,
            refractivity=self.refractivity, conductivity=self.conductivity,
            permittivity=self.permittivity, humidity=self.humidity)


