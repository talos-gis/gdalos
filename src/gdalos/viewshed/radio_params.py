# calc_type
ctPathLoss = 0
ctPowerReminder = 1
ctPowerReminderBinary = 2
ctLOS = 3
ctFreeSpaceLoss = 4
ctNonFreeSpaceLoss = 5
ctClearance = 6
ctMode = 7

# polarity
polarityHorizontal = 0
polarityVertical = 1


class RadioParams(object):
    __slots__ = ['frequency', 'KFactor', 'polarity', 'calc_type',
                 'refractivity', 'conductivity', 'permittivity', 'humidity',
                 'power_diff', 'sampling_interval', 'fill_center', 'profile_extension']

    def __init__(self):
        self.frequency = 3333.0
        self.KFactor = 0
        self.polarity = polarityHorizontal
        self.calc_type = ctPathLoss

        self.refractivity = 333.0
        self.conductivity = 3.0
        self.permittivity = 33.0
        self.humidity = 33.0

        self.power_diff = 100  # BroadcastPower - MinPower
        self.sampling_interval = -1  # auto
        self.fill_center = True
        self.profile_extension = True
