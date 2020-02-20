from typing import Union

from fidget.backend.QtWidgets import QHBoxLayout
from fidget.widgets import FidgetConst, FidgetInt, FidgetStacked


class NodatavalueWidget(FidgetStacked[Union[float, type(...)]]):
    INNER_TEMPLATES = [
        FidgetConst.template("auto", option=("auto", ...)),
        FidgetInt.template("number"),
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
    w = FidgetOptional(NodatavalueWidget("sample nodatavalue"))
    w.show()
    app.exec_()
    print(w.value())
