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

    parameters = dict()
    parameters['source file'] = 'filename'
    parameters['source ovr'] = 'src_ovr'
    parameters['output format'] = 'of'
    parameters['cloud optimized geotiff'] = 'cog'
    parameters['create info'] = 'create_info'
    parameters['write spec'] = 'write_spec'
    parameters['output extension'] = 'outext'
    parameters['BIGTIFF'] = 'big_tiff'
    parameters['wrap CRS'] = 'warp_CRS'
    parameters['destination file'] = 'out_filename'
    parameters['skip if exists'] = 'skip_if_exists'
    parameters['raster kind'] = 'kind'
    parameters['expand rgb'] = 'expand_rgb'
    parameters['resolution'] = 'out_res'
    parameters['destination nodatavalue'] = 'dst_nodatavalue'
    parameters['source nodatavalue'] = 'src_nodatavalue'
    parameters['hide nodatavalue'] = 'hide_nodatavalue'
    parameters['source window'] = 'src_win'
    parameters['ovr type'] = 'ovr_type'
    parameters['resampling method'] = 'resampling_alg'
    parameters['jpeg quality'] = 'jpeg_quality'
    parameters['keep alpha'] = 'keep_alpha'

    if result.is_ok() and result.value is not None:
        for v in result.value:
            d = dict(v[0])
            d2 = dict()
            for k,v in d.items():
                if k in parameters.keys():
                    new_k = parameters[k]
                else:
                    new_k = k
                d2[new_k] = d[k]

            print(gdalos_trans(**d2))
    # app.exec_()


if __name__ == '__main__':
    gdalos_qt_main()