import argparse

import fidget


def gdalos_qt_main():
    from fidget.backend.QtWidgets import QApplication
    from fidget.backend.QtWidgets import QVBoxLayout
    from fidget.core import Fidget
    from fidget.widgets import FidgetMatrix, FidgetMinimal, FidgetQuestion
    from fidget.widgets.__util__ import CountBounds
    from gdalos.gdalos_trans import gdalos_trans
    from gdalos_qt.gdalos_widget import GdalosWidget

    app = QApplication(
        []
    )  # this app variable is needed, because otherwise python will delete the QApplication
    q = FidgetQuestion(
        FidgetMatrix(
            FidgetMinimal(
                GdalosWidget(make_title=True, make_plaintext=True, make_indicator=True),
                make_title=False,
                make_plaintext=False,
                make_indicator=False,
                initial_value={},
            ),
            rows=CountBounds(1, 1, None),
            columns=1,
            make_plaintext=True,
            make_title=True,
            make_indicator=False,
            layout_cls=QVBoxLayout,
            scrollable=True,
        ),
        flags=Fidget.FLAGS,
    )
    q.show()
    result = q.exec()
    print(result)

    if result.is_ok() and result.value is not None:
        for v in result.value:
            d = dict(v[0])
            d2 = dict()
            for k, v in d.items():
                new_k = k.replace(" ", "_")
                d2[new_k] = d[k]

            print(gdalos_trans(**d2))
    # app.exec_()


if __name__ == "__main__":
    from fidget.backend import prefer

    # the prefer command must be called before importing fidget.backend.QtWidgets
    # prefer("PyQt5", True)

    parser = argparse.ArgumentParser(description='gdalos qt.')
    backend_names = list(fidget.backend.preference.backends.keys())
    parser.add_argument('-b', '--backend', type=str, nargs='?', choices=backend_names, default=None, help='prefered qt backend')
    parser.add_argument('-o', '--only', action='store_true', default=False, help='try only preferred backend')
    args = parser.parse_args()
    if args.backend:
        prefer(args.backend, try_all=not args.only)

    gdalos_qt_main()
