import re

from fidget.backend.QtWidgets import QHBoxLayout

from fidget.core import validator, inner_plaintext_parser, PlaintextParseError

from fidget.widgets import FidgetCombo, FidgetFloat, FidgetEditCombo, FidgetStacked, FidgetLine, FidgetConverter, \
    FidgetDict, inner_fidget


@validator('zone must be between 1 and 60')
def zone_validator(v: float):
    return 1 <= v <= 60


class CrsWidget(FidgetStacked[str]):
    @inner_fidget()
    class CrsWidgetUtm(FidgetConverter[dict, str]):
        @inner_fidget('utm', make_indicator=False, make_title=False)
        class _CrsWidgetUtmMulti(FidgetDict):
            INNER_TEMPLATES = [
                FidgetEditCombo.template('datum', ('w84', 'e50'), make_title=False,
                                         make_indicator=False, make_plaintext=False),
                FidgetFloat.template('zone', make_title=False, validation_func=zone_validator,
                                     make_indicator=False)
            ]

            LAYOUT_CLS = QHBoxLayout

        def convert(self, d: dict):
            return f'{d["datum"]}u{d["zone"]:n}'

        @inner_plaintext_parser
        @staticmethod
        def shorthand(s: str):
            split = s.rsplit('u', 2)
            if len(split) == 1:
                raise PlaintextParseError('string must contain a "u" separator')
            return s

        def back_convert(self, s: str):
            split = s.rsplit('u', 2)
            if len(split) == 1:
                datum, zone = s, ''
            else:
                datum, zone = split

            try:
                zone = float(zone)
            except ValueError:
                zone = 0

            return {'datum': datum, 'zone': zone}

    @inner_fidget('proj4')
    class CrsWidgetProj(FidgetLine):
        PATTERN = re.compile(r'\+proj=[a-zA-Z0-9_.]+(\s+\+[a-zA-Z_][a-zA-Z0-9_]*=[-a-zA-Z0-9_.]+)*')

    @inner_fidget('builtin', options=('w84geo',), initial_value='w84geo', make_title=False)
    class CrsWidgetBuiltin(FidgetCombo):
        pass

    MAKE_TITLE = True
    MAKE_INDICATOR = True
    LAYOUT_CLS = QHBoxLayout
    SELECTOR_CLS = 'radio'


if __name__ == '__main__':
    from fidget.backend.QtWidgets import QApplication
    from fidget.widgets import FidgetOptional

    app = QApplication([])
    w = FidgetOptional(CrsWidget('sample', make_plaintext=True))
    w.show()
    app.exec_()
    print(w.value())
