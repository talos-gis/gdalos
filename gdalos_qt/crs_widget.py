from PyQt5.QtWidgets import QHBoxLayout

from functools import partial

from qtalos import validator, InnerPlaintextParser, PlaintextParseError
from qtalos.widgets import ValueEditCombo, FloatEdit, ValueCombo, StackedValueWidget, LineEdit, ConverterWidget, \
    DictWidget, inner_widget


@validator('zone must be between 1 and 60')
def zone_validator(v: float):
    return 1 <= v <= 60


class CrsWidget(StackedValueWidget[str]):
    @inner_widget('utm')
    class CrsWidgetUtm(ConverterWidget[dict, str]):
        @inner_widget(make_validator_label=False, make_title_label=False)
        class _CrsWidgetUtmMulti(DictWidget):
            def make_inner(self):
                yield ValueEditCombo('datum', ('w84', 'e50'), default_index=0, make_title_label=False,
                                     make_validator_label=False)
                yield FloatEdit('zone', make_title_label=False, validation_func=zone_validator,
                                make_validator_label=False)

            default_layout_cls = QHBoxLayout

        def convert(self, d: dict):
            return f'{d["datum"]}u{d["zone"]:n}'

        @InnerPlaintextParser
        def shorthand(self, s: str):
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

            return {'datum': datum, 'zone': zone}

    @inner_widget('proj4')
    class CrsWidgetProj(LineEdit):
        def make_pattern(self):
            return r'\+proj=[a-zA-Z0-9_.]+(\s+\+[a-zA-Z_][a-zA-Z0-9_]*=[-a-zA-Z0-9_.]+)*'

    @inner_widget('builtin', options=('w84geo',), default_value='w84geo', make_title_label=False)
    class CrsWidgetBuiltin(ValueCombo):
        pass


if __name__ == '__main__':
    from PyQt5.QtWidgets import QApplication
    from qtalos.widgets import OptionalValueWidget

    app = QApplication([])
    w = OptionalValueWidget(CrsWidget('sample', make_plaintext_button=True))
    w.show()
    exit(app.exec_())
