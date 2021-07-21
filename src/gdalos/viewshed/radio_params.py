from collections import Sequence
from enum import IntEnum
from numbers import Real
from typing import NamedTuple, Union, Tuple

from gdalos import gdalos_base
from osgeo_utils.auxiliary.base import SequenceNotString, MaybeSequence, num, num_or_none


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


DefaultRadioBaseParams = RadioBaseParams(refractivity=300.0, conductivity=0.03, permittivity=15.0, humidity=10.0)


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

    @staticmethod
    def polar_deg(polarity: MaybeSequence[Union[str, bool, Real, RadioPolarity]]):
        if isinstance(polarity, SequenceNotString.__args__):
            return [RadioParams.polar_deg(p) for p in polarity]
        if isinstance(polarity, (RadioPolarity, bool)):
            return 90 if polarity else 0
        if isinstance(polarity, str):
            p = num_or_none(polarity)
            if p is not None:
                return p
            p = polarity[0].lower()
            return 90 if p in ['v', 't'] else 0
        if not polarity:
            return 0
        return polarity

    @staticmethod
    def polar_hv(polarity: MaybeSequence[Union[str, Real, RadioPolarity]]):
        if isinstance(polarity, SequenceNotString.__args__):
            return [RadioParams.polar_hv(p) for p in polarity]
        if isinstance(polarity, RadioPolarity):
            return polarity
        polarity = RadioParams.polar_deg(polarity)
        return RadioPolarity.Vertical if polarity else RadioPolarity.Horizontal

    def get_polarization_deg(self):
        return self.polar_deg(self.polarity)

    def get_dict(self):
        d = gdalos_base.get_dict(self)
        d['polarity'] = self.polar_hv(self.polarity)
        return d

    def as_radiobase_params(self):
        return dict(
            refractivity=self.refractivity, conductivity=self.conductivity,
            permittivity=self.permittivity, humidity=self.humidity)

    def as_rfmodel_params(self):
        return dict(
            frequency=self.frequency, polarization=self.polar_hv(self.polarity),
            refractivity=self.refractivity, conductivity=self.conductivity,
            permittivity=self.permittivity, humidity=self.humidity)

