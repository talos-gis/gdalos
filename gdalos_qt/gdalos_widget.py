from itertools import chain

from PyQt5.QtWidgets import QFileDialog, QFrame, QHBoxLayout

from qtalos.widgets import ValueEditCombo, FilePathWidget, OptionalValueWidget, ValueCheckBox, \
    ValueCombo, DictWidget, IntEdit, TupleWidget

from gdalos import RasterKind
from gdalos_qt.crs_widget import CrsWidget


class GdalosWidget(DictWidget):
    def make_inner(self):
        yield FilePathWidget('source file', exist_cond=True,
                             dialog=QFileDialog(filter='raster files (*.tiff *.vrt *.tif *.xml);;all files (*.*)'))
        yield OptionalValueWidget(IntEdit('source ovr', placeholder=False))
        # todo validate drivers?
        yield ValueEditCombo('output format', options=('GTiff',), default_index=0, make_validator_label=False)
        yield ValueEditCombo('output extension', options=('tif',), default_index=0, make_validator_label=False)
        yield ValueCheckBox('tiled', ['NO', 'YES'])
        yield ValueCombo('BIGTIFF', options=['YES', 'NO', 'IF_NEEDED', 'IF_SAFER'], default_value='IF_SAFER')
        yield OptionalValueWidget(
            CrsWidget('wrap CRS', make_plaintext_button=True, make_validator_label=True,
                      frame_style=QFrame.Box | QFrame.Plain)
        )
        yield OptionalValueWidget(
            FilePathWidget('destination file', exist_cond=None,
                           dialog=QFileDialog(filter='raster files (*.tiff *.vrt *.tif *.xml);;all files (*.*)')),
            make_validator_label=False
        )
        yield ValueCombo('raster kind', options=chain((('AUTO', ...),), RasterKind.__members__), default_index=0)
        yield ValueCheckBox('lossy', initial=False)
        yield ValueCheckBox('expand rgb', initial=False)
        yield OptionalValueWidget(
            TupleWidget('resolution', inner=(
                IntEdit('X', make_validator_label=False, make_title_label=False),
                IntEdit('Y', make_validator_label=False, make_title_label=False)
            ), layout_cls=QHBoxLayout),
            make_validator_label=False
        )
        yield ValueCheckBox('create info', initial=False)


if __name__ == '__main__':
    from PyQt5.QtWidgets import QApplication

    app = QApplication([])
    w = GdalosWidget('gdalos', make_title_label=False, make_plaintext_button=True, scrollable=True)
    w.show()
    res = app.exec_()
    print(w.value())
    exit(res)
