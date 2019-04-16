from fidget.backend import prefer

prefer('PyQt5')

from gdalos_qt.gdalos_widget import GdalosWidget
from fidget.widgets import FidgetQuestion
from gdalos import gdalos_trans

if __name__ == '__main__':
    from fidget.backend.QtWidgets import QApplication

    app = QApplication([])
    q = FidgetQuestion(
        GdalosWidget(make_title=True, make_plaintext=True, make_indicator=True),
        cancel_value=None
    )
    q.show()
    result = q.exec_()
    print(result)
    if result.is_ok() and result.value is not None:
        d: dict = result.value
        d['filename'] = str(d.pop('source file'))
        d['src_ovr'] = d.pop('source ovr')
        d['of'] = d.pop('output format')
        d['outext'] = d.pop('output extension')
        d['big_tiff'] = d.pop('BIGTIFF')
        d['warp_CRS'] = d.pop('wrap CRS')
        d['out_filename'] = d.pop('destination file')
        d['kind'] = d.pop('raster kind')
        d['expand_rgb'] = d.pop('expand rgb')
        d['out_res'] = d.pop('resolution')
        d['skip_if_exists'] = d.pop('skip if exists')
        d['create_info'] = d.pop('create info')
        d['dst_nodatavalue'] = d.pop('destination nodatavalue')
        d['src_nodatavalue'] = d.pop('source nodatavalue')
        d['hide_nodatavalue'] = d.pop('hide nodatavalue')
        d['src_win'] = d.pop('source window')
        d['ovr_type'] = d.pop('ovr type')
        d['resample_method'] = d.pop('resampling method')
        d['jpeg_quality'] = d.pop('jpeg quality')
        d['keep_alpha'] = d.pop('keep alpha')
        print(gdalos_trans(**d))
    #app.exec_()
