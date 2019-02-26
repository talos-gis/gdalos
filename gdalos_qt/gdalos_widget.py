from typing import List

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QFileDialog

from qtalos import ValueWidget, wrap_parser
from qtalos.widgets import ValueEditCombo, FilePathEditWidget, OptionalValueWidget, ConvertedEdit, ValueCheckBox, ValueCombo

from gdalos_qt.georect_widget import GeoRectWidget


class GdalosWidget(QWidget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.dependants: List[ValueWidget] = []
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        self.dependants = [
            FilePathEditWidget('source file', exist_cond=True,
                               dialog=QFileDialog(filter='raster files (*.tiff *.vrt *.tif *.xml);;all files (*.*)')),
            OptionalValueWidget(ConvertedEdit('source ovr', convert_func=wrap_parser(ValueError, int))),
            # todo validate drivers?
            ValueEditCombo('output format', options=('GTiff',), default_index=0, make_validator_label=False),
            ValueEditCombo('output extension', options=('tif',), default_index=0, make_validator_label=False),
            ValueCheckBox('tiled', ['NO', 'YES']),
            ValueCombo('BIGTIFF', options=['YES', 'NO', 'IF_NEEDED', 'IF_SAFER'], default_value='IF_SAFER')
        ]

        for d in self.dependants:
            layout.addWidget(d)


if __name__ == '__main__':
    from PyQt5.QtWidgets import QApplication

    app = QApplication([])
    w = GdalosWidget()
    w.show()
    res = app.exec_()
    exit(res)
