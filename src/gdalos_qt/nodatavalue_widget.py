from typing import Union, Optional

from fidget.backend.QtWidgets import QHBoxLayout
from fidget.widgets import FidgetConst, FidgetInt, FidgetStacked


class NodatavalueWidgetSrc(FidgetStacked[Optional[Union[float, type(...)]]]):
    INNER_TEMPLATES = [
        FidgetConst.template("get original value", option=("...", ...)),
        FidgetConst.template("raster minimum (might take time)", option=("None", None)),
        FidgetInt.template("given value"),
    ]
    SELECTOR_CLS = "radio"
    MAKE_TITLE = True
    MAKE_INDICATOR = False
    MAKE_PLAINTEXT = False
    LAYOUT_CLS = QHBoxLayout


class NodatavalueWidgetDst(FidgetStacked[Optional[Union[float, type(...)]]]):
    INNER_TEMPLATES = [
        FidgetConst.template("don't change", option=("None", None)),
        FidgetConst.template("change to default value (for DTM)", option=("...", ...)),
        FidgetInt.template("change to a set value"),
    ]
    SELECTOR_CLS = "radio"
    MAKE_TITLE = True
    MAKE_INDICATOR = False
    MAKE_PLAINTEXT = False
    LAYOUT_CLS = QHBoxLayout


if __name__ == "__main__":
    from fidget.backend.QtWidgets import QApplication
    from fidget.widgets import FidgetOptional

    app = QApplication([])
    # w = FidgetOptional(NodatavalueWidget("sample nodatavalue"))
    # w = NodatavalueWidgetSrc("sample nodatavalue", initial_value=None)  # todo: setting initial_value doesn't work
    w = NodatavalueWidgetSrc("sample nodatavalue")
    w.show()
    app.exec_()
    print(w.value())
