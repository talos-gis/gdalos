from fidget.backend import prefer

prefer('PyQt5')

from fidget.core import Fidget
from gdalos_qt.gdalos_widget import GdalosWidget
from fidget.backend.QtWidgets import QVBoxLayout
from fidget.widgets import FidgetQuestion, FidgetMatrix, FidgetMinimal
from fidget.widgets.__util__ import CountBounds
from gdalos import gdalos_trans


def gdalos_qt_main():
    from fidget.backend.QtWidgets import QApplication

    app = QApplication([])
    q = FidgetQuestion(
        FidgetMatrix(
            FidgetMinimal(
                GdalosWidget(make_title=True, make_plaintext=True, make_indicator=True),
                make_title=False, make_plaintext=False, make_indicator=False, initial_value={}
            ),
            rows=CountBounds(1, 1, None),
            columns=1,
            make_plaintext=True, make_title=True, make_indicator=False, layout_cls=QVBoxLayout, scrollable=True
        ), flags=Fidget.FLAGS
    )
    q.show()
    result = q.exec()
    print(result)
    if result.is_ok() and result.value is not None:
        for v in result.value:
            d = dict(v[0])
            d['filename'] = str(d.pop('source file'))
            d['src_ovr'] = d.pop('source ovr')
            d['of'] = d.pop('output format')
            d['outext'] = d.pop('output extension')
            d['big_tiff'] = d.pop('BIGTIFF')
            d['warp_CRS'] = d.pop('wrap CRS')
            d['out_filename'] = d.pop('destination file')
            d['skip_if_exists'] = d.pop('skip if exists')
            d['kind'] = d.pop('raster kind')
            d['expand_rgb'] = d.pop('expand rgb')
            d['out_res'] = d.pop('resolution')
            d['create_info'] = d.pop('create info')
            d['dst_nodatavalue'] = d.pop('destination nodatavalue')
            d['src_nodatavalue'] = d.pop('source nodatavalue')
            d['hide_nodatavalue'] = d.pop('hide nodatavalue')
            d['src_win'] = d.pop('source window')
            d['ovr_type'] = d.pop('ovr type')
            d['resampling_alg'] = d.pop('resampling method')
            d['jpeg_quality'] = d.pop('jpeg quality')
            d['keep_alpha'] = d.pop('keep alpha')
            print(gdalos_trans(**d))
    # app.exec_()


if __name__ == '__main__':
    gdalos_qt_main()