from PyQt5.QtWidgets import QHBoxLayout

import re

from qtalos import ValueWidget, validator, wrap_parser, ParseError, regex_parser
from qtalos.widgets import ValueEditCombo, ConvertedEdit


@validator('zone must be a valid number')
def zone_validator(v: float):
    return 1 <= v <= 60



class CrsWidgetUtm(ValueWidget[str]):
    pattern = re.compile(r'(?P<prefix>[a-zA-Z_][a-zA-Z0-9_]*)u(?P<zone>[0-9]{1,2}(\.[0-9]+)?)')

    @staticmethod
    @regex_parser(pattern, name='pattern')
    def pattern_parser(match):
        return match.string

    def __init__(self, title, **kwargs):
        super().__init__(title, **kwargs)

        self.prefix_combo: ValueEditCombo[str] = None
        self.zone_edit: ConvertedEdit[float] = None
        self.init_ui()

    def init_ui(self):
        super().init_ui()

        layout = QHBoxLayout(self)

        with self.setup_provided(layout):
            self.prefix_combo = ValueEditCombo('ellipsoid', ('w84', 'e50'), default_index=0, make_title_label=False,
                                               make_validator_label=False)
            self.prefix_combo.on_change.connect(self.change_value)
            layout.addWidget(self.prefix_combo)

            self.zone_edit = ConvertedEdit('zone', convert_func=wrap_parser(ValueError, float), make_title_label=False,
                                           validation_func=zone_validator, make_validator_label=False)
            self.zone_edit.on_change.connect(self.change_value)
            layout.addWidget(self.zone_edit)

    def parse(self):
        ok, prefix, _ = self.prefix_combo.value()
        if ok < 0:
            raise ParseError('could not parse prefix') from prefix
        ok, zone, _ = self.zone_edit.value()
        if ok < 0:
            raise ParseError('could not parse zone') from zone
        return prefix + 'u' + str(zone)

    def fill(self, v: str):
        split = v.rsplit('u', 2)
        if len(split) == 1:
            pref, zone = v, ''
        else:
            pref, zone = split

        self.prefix_combo.fill(pref)
        self.zone_edit.fill(zone)

    def plaintext_parsers(self):
        yield from super().plaintext_parsers()
        yield self.pattern_parser


if __name__ == '__main__':
    from PyQt5.QtWidgets import QApplication

    app = QApplication([])
    w = CrsWidgetUtm('sample', make_plaintext_button=True)
    w.show()
    exit(app.exec_())
