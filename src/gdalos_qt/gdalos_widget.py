from itertools import chain

from fidget.backend.QtWidgets import QFrame, QHBoxLayout
from fidget.widgets import (
    FidgetCheckBox,
    FidgetCombo,
    FidgetConverter,
    FidgetDict,
    FidgetEditCombo,
    FidgetFilePath,
    FidgetFloat,
    FidgetInt,
    FidgetMinimal,
    FidgetOptional,
    FidgetSpin,
    FidgetTabs,
    FidgetTuple,
    inner_fidget,
)
from gdalos.gdalos_trans import GeoRectangle, OvrType, RasterKind, GdalResamplingAlg, GdalOutputFormat
from gdalos_qt.crs_widget import CrsWidget
from gdalos_qt.nodatavalue_widget import NodatavalueWidgetSrc, NodatavalueWidgetDst

raster_fidget = FidgetFilePath.template(
    dialog={
        "filter": "raster files (*.tif *.tiff *.vrt *.xml *.img *.dt1 *.dt2);;all files (*.*)"
    },
    make_title=True,
)

FidgetCheckBox.MAKE_TITLE = True
FidgetEditCombo.MAKE_INDICATOR = FidgetEditCombo.MAKE_PLAINTEXT = False


class GdalosWidget(FidgetConverter):
    @inner_fidget("gdalos")
    class GdalosWidget(FidgetTabs):
        INNER_TEMPLATES = [
            FidgetDict.template(
                "basic",
                [
                    (
                        "filename",
                        raster_fidget.template("source file", exist_cond=True),
                    ),
                    (
                        "cog",
                        FidgetCheckBox.template(
                            "make cog (cloud optimized geotiff)", initial_value=True
                        ),

                    ),
                    FidgetCheckBox.template("prefer_2_step_cog", initial_value=True),
                    FidgetCheckBox.template("delete_temp_files", initial_value=True),
                    FidgetCheckBox.template("overwrite", initial_value=False),
                    (
                        "multi_file_as_vrt",
                        FidgetCheckBox.template(
                            "treat multi file as vrt", initial_value=False
                        ),
                    ),
                    FidgetCheckBox.template("sparse_ok", initial_value=True),
                    FidgetCheckBox.template("write_info", initial_value=True),
                    FidgetCheckBox.template("write_spec", initial_value=True),
                ],
                make_plaintext=False,
            ),
            FidgetDict.template(
                "overviews",
                [
                    (
                        "ovr_idx",
                        FidgetOptional.template(
                            FidgetInt.template("source overview index", placeholder=False),
                            make_title=True,
                        ),
                    ),
                    FidgetOptional.template(
                        FidgetInt.template("dst_ovr_count", placeholder=False),
                        make_title=True,
                    ),
                    FidgetCombo.template(
                        "ovr_type",
                        options=list(
                            chain((("AUTO", ...), ("None", None)), OvrType.__members__)
                        ),
                        initial_index=0,
                        make_title=True,
                    ),
                    FidgetCheckBox.template(
                        "keep_src_ovr_suffixes", initial_value=True
                    ),
                ],
                make_plaintext=False,
            ),
            FidgetDict.template(
                "format",
                [
                    # todo validate drivers?
                    (
                        "of",
                        FidgetCombo.template(
                            "output format",
                            options=list(
                                chain((("AUTO", ...),), GdalOutputFormat.__members__)
                            ),
                            initial_index=0,
                            make_title=True,
                        ),
                    ),
                    (
                        "outext",
                        FidgetEditCombo.template(
                            "output extension", options=("tif",), make_title=True
                        ),
                    ),
                    FidgetCheckBox.template("tiled", options=("NO", "YES")),
                    FidgetCombo.template(
                        "big_tiff",
                        options=["YES", "NO", "IF_NEEDED", "IF_SAFER"],
                        initial_value="IF_SAFER",
                        make_title=True,
                    ),
                ],
                make_plaintext=False,
            ),
            FidgetDict.template(
                "conversion",
                [
                    FidgetCombo.template(
                        "lossy",
                        options=[("AUTO", None), False, True],
                        initial_index=0,
                        make_title=True,
                    ),
                    FidgetCombo.template(
                        "kind",
                        options=list(
                            chain((("AUTO", ...),), RasterKind.__members__.items())
                        ),
                        initial_index=0,
                        make_title=True,
                    ),
                    FidgetCheckBox.template("expand_rgb", initial_value=False),
                    FidgetMinimal.template(
                        FidgetOptional.template(
                            CrsWidget.template(
                                "warp_srs",
                                make_plaintext=True,
                                make_indicator=True,
                                frame_style=QFrame.Box | QFrame.Plain,
                            )
                        ),
                        make_title=True,
                        make_plaintext=False,
                        make_indicator=False,
                        initial_value=None,
                    ),
                    (
                        "out_res",
                        FidgetOptional.template(
                            FidgetTuple.template(
                                "resolution",
                                inner_templates=(
                                    FidgetInt.template(
                                        "X", make_indicator=False, make_title=False
                                    ),
                                    FidgetInt.template(
                                        "Y", make_indicator=False, make_title=False
                                    ),
                                ),
                                layout_cls=QHBoxLayout,
                            ),
                            make_indicator=False,
                            make_title=True,
                            make_plaintext=True,
                        ),
                    ),
                ],
                make_plaintext=False,
            ),
            FidgetDict.template(
                "extent",
                [
                    FidgetOptional.template(
                        FidgetConverter.template(
                            FidgetTuple.template(
                                "extent",
                                inner_templates=[
                                    FidgetFloat.template(letter) for letter in "WESN"
                                ],
                                layout_cls=QHBoxLayout,
                                make_title=False,
                            ),
                            converter_func=lambda x: GeoRectangle.from_lrdu(*x),
                            back_converter_func=GeoRectangle.lrdu.fget,
                        ),
                        make_title=True,
                        make_indicator=False,
                        make_plaintext=True,
                    ),
                    (
                        "extent_in_4326",
                        FidgetCheckBox.template(
                            "extent is in EPSG:4326 (WGS84Geo), otherwise it should be in target srs",
                            initial_value=True
                        ),
                    ),
                    (
                        "srcwin",
                        FidgetOptional.template(
                            FidgetConverter.template(
                                FidgetTuple.template(
                                    "source window",
                                    inner_templates=[
                                        FidgetFloat.template(letter)
                                        for letter in "XYWH"
                                    ],
                                    layout_cls=QHBoxLayout,
                                    make_title=False,
                                ),
                                converter_func=lambda x: GeoRectangle(*x),
                                back_converter_func=GeoRectangle.xywh.fget,
                            ),
                            make_title=True,
                            make_indicator=False,
                            make_plaintext=True,
                        ),
                    ),
                    FidgetOptional.template(
                        FidgetInt.template("partition", placeholder=False),
                        make_title=True,
                    ),
                ],
                make_plaintext=False,
            ),
            FidgetDict.template(
                'NoData value',
                [
                    FidgetCheckBox.template("hide nodatavalue", initial_value=False),
                    (
                        "dst_nodatavalue",
                        NodatavalueWidgetDst.template("dst_nodatavalue"),
                    ),
                    (
                        "src_nodatavalue",
                        NodatavalueWidgetSrc.template("src_nodatavalue"),
                    ),
                ],
                make_plaintext=False,
            ),
            FidgetDict.template(
                "output",
                [
                    (
                        "out_path",
                        FidgetOptional.template(
                            raster_fidget.template(
                                "output path: folder", exist_cond=None
                            ),
                            make_indicator=False,
                        ),
                    ),
                    (
                        "out_path_with_src_folders",
                        FidgetCheckBox.template(
                            "output path: keep source folder structure",
                            initial_value=True,
                        ),
                    ),
                    (
                        "out_filename",
                        FidgetOptional.template(
                            raster_fidget.template(
                                "output path: set destination file", exist_cond=None
                            ),
                            make_indicator=False,
                        ),
                    ),
                ],
                make_plaintext=False,
            ),
            FidgetDict.template(
                "advanced",
                [
                    FidgetCombo.template(
                        "resampling_alg",
                        options=list(
                            chain((("None", None), ("AUTO", ...)), GdalResamplingAlg.__members__)
                        ),
                        initial_index=0,
                        make_title=True,
                    ),
                    FidgetCheckBox.template("keep_alpha"),
                    FidgetSpin.template(
                        "quality", 1, 100, initial_value=75, make_title=True
                    ),
                ],
                make_plaintext=False,
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


if __name__ == "__main__":
    from fidget.backend.QtWidgets import QApplication

    app = QApplication([])
    w = GdalosWidget(make_title=True, make_plaintext=True, make_indicator=True)
    print(w.fill)
    w.show()
    res = app.exec_()
    print(w.value())
    exit(res)
