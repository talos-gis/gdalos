from itertools import chain

from fidget.backend.QtWidgets import QFrame, QHBoxLayout

from fidget.widgets import FidgetEditCombo, FidgetFilePath, FidgetOptional, FidgetCheckBox, \
    FidgetCombo, FidgetDict, FidgetInt, FidgetTuple, FidgetMinimal, FidgetStacked, FidgetConst, FidgetFloat, \
    FidgetConverter, FidgetSpin, FidgetTabs, inner_fidget

from gdalos import RasterKind, GeoRectangle, OvrType
from gdalos_qt.crs_widget import CrsWidget
from gdalos_qt.nodatavalue_widget import NodatavalueWidget

raster_fidget = FidgetFilePath.template(dialog={'filter': 'raster files (*.tiff *.vrt *.tif *.xml);;all files (*.*)'},
                                        make_title=True)

FidgetCheckBox.MAKE_TITLE = True
FidgetEditCombo.MAKE_INDICATOR = FidgetEditCombo.MAKE_PLAINTEXT = False


class GdalosWidget(FidgetConverter):
    @inner_fidget('gdalos')
    class GdalosWidget(FidgetTabs):
        INNER_TEMPLATES = [
            FidgetDict.template(
                'basic',
                [
                    raster_fidget.template('source file', exist_cond=True),
                    FidgetOptional.template(FidgetInt.template('source ovr', placeholder=False),
                                            make_title=True),
                    # todo validate drivers?
                    FidgetEditCombo.template('output format', options=('GTiff',),
                                             make_title=True),
                    FidgetEditCombo.template('output extension', options=('tif',),
                                             make_title=True),
                    FidgetCheckBox.template('tiled', options=('NO', 'YES')),
                    FidgetCombo.template('BIGTIFF', options=['YES', 'NO', 'IF_NEEDED', 'IF_SAFER'],
                                         initial_value='IF_SAFER',
                                         make_title=True),
                    FidgetMinimal.template(
                        FidgetOptional.template(
                            CrsWidget.template('wrap CRS', make_plaintext=True, make_indicator=True,
                                               frame_style=QFrame.Box | QFrame.Plain)
                        ),
                        make_title=True, make_plaintext=False, make_indicator=False, initial_value=None
                    ),
                    FidgetOptional.template(
                        raster_fidget.template('destination file', exist_cond=None),
                        make_indicator=False
                    )
                ],
                make_plaintext=False
            ),
            FidgetDict.template(
                'conversion',
                [
                    FidgetCombo.template('raster kind', options=list(chain((('AUTO', ...),), RasterKind.__members__.items())),
                                         initial_index=0,
                                         make_title=True),
                    FidgetCheckBox.template('lossy', initial_value=False),
                    FidgetCheckBox.template('expand rgb', initial_value=False),
                    FidgetOptional.template(
                        FidgetTuple.template('resolution', inner_templates=(
                            FidgetInt.template('X', make_indicator=False, make_title=False),
                            FidgetInt.template('Y', make_indicator=False, make_title=False)
                        ), layout_cls=QHBoxLayout),
                        make_indicator=False, make_title=True, make_plaintext=True
                    ),
                    FidgetCheckBox.template('create info', initial_value=False),

                    NodatavalueWidget.template('destination nodatavalue'),
                    NodatavalueWidget.template('source nodatavalue'),
                    FidgetCheckBox.template('hide nodatavalue'),
                ],
                make_plaintext=False
            ),
            FidgetDict.template(
                'rectangle',
                [
                    FidgetOptional.template(
                        FidgetConverter.template(
                            FidgetTuple.template('extent', inner_templates=[
                                FidgetFloat.template(letter) for letter in 'WESN'
                            ], layout_cls=QHBoxLayout, make_title=False),
                            converter_func=lambda x: GeoRectangle.from_lrdu(*x),
                            back_converter_func=GeoRectangle.lrdu.fget
                        ),
                        make_title=True, make_indicator=False, make_plaintext=True
                    ),
                    FidgetOptional.template(
                        FidgetConverter.template(
                            FidgetTuple.template('source window', inner_templates=[
                                FidgetFloat.template(letter) for letter in 'XYWH'
                            ], layout_cls=QHBoxLayout, make_title=False),
                            converter_func=lambda x: GeoRectangle(*x), back_converter_func=GeoRectangle.xywh.fget
                        ),
                        make_title=True, make_indicator=False, make_plaintext=True
                    ),
                ],
                make_plaintext=False
            ),
            FidgetDict.template(
                'advanced',
                [
                    FidgetCombo.template('ovr type',
                                         options=list(chain((('AUTO', ...), ('None', None)), OvrType.__members__)),
                                         initial_index=0, make_title=True),
                    FidgetCombo.template('resampling method',
                                         options=(
                                             ('auto', ...), 'nearest', 'bilinear', 'cubic', 'cubicspline', 'lanczos',
                                             'average', 'mode'),
                                         initial_index=0, make_title=True),
                    FidgetSpin.template('jpeg quality', 1, 100, initial_value=75, make_title=True),
                    FidgetCheckBox.template('keep alpha'),
                ],
                make_plaintext=False
            ),
        ]

    def convert(self, v: dict):
        ret = {}
        for k, v in v.items():
            ret.update(v)
        return ret

    def back_convert(self, v: dict):
        ret = {}
        sw: FidgetDict
        for d_name, sw in self.inner.inners.items():
            ret[d_name] = {}
            for title, ssw in sw.inners.items():
                if title in v:
                    ret[d_name][title] = v[title]

        return ret


if __name__ == '__main__':
    from fidget.backend.QtWidgets import QApplication

    app = QApplication([])
    w = GdalosWidget(make_title=True, make_plaintext=True, make_indicator=True)
    print(w.fill)
    w.show()
    res = app.exec_()
    print(w.value())
    exit(res)
