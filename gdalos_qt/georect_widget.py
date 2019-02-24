from typing import List, Optional

from PyQt5.QtWidgets import QHBoxLayout, QLineEdit, QCheckBox

from gdalos import GeoRectangle

from qtalos import ValueWidget


class GeoRectWidget(ValueWidget[Optional[GeoRectangle]]):
    def __init__(self, title: str, default_any=False, **kwargs):
        super().__init__(title, **kwargs)
        self.any_checkbox: QCheckBox = None
        self.component_edits: List[QLineEdit] = None  # the elements will be stored in lrud

        self.init_ui()

        self.any_checkbox.stateChanged.emit(default_any)

    def init_ui(self):
        super().init_ui()
        layout = QHBoxLayout(self)

        self.any_checkbox = QCheckBox(self.title+':')
        self.any_checkbox.stateChanged.connect(self.update_any)
        self.any_checkbox.stateChanged.connect(self.change_value)
        layout.addWidget(self.any_checkbox)

        self.component_edits = []
        for letter in 'WENS':  # lrud
            edit = QLineEdit()
            edit.setPlaceholderText(letter)
            edit.setToolTip(letter)
            edit.textChanged.connect(self.change_value)
            layout.addWidget(edit)

            self.component_edits.append(edit)

        if self.validation_label:
            layout.addWidget(self.validation_label)
        if self.plaintext_button:
            layout.addWidget(self.plaintext_button)

    def update_any(self, new_state):
        enable = new_state != 0
        for ce in self.component_edits:
            ce.setEnabled(enable)

    def parse(self):
        if not self.any_checkbox.isChecked():
            return None
        lrud = []
        for edit in self.component_edits:
            text = edit.text()
            try:
                num = float(text)
            except ValueError as e:
                raise self.parse_exception(f'{edit.placeholderText()}: could not parse float') from e
            lrud.append(num)
        return GeoRectangle.from_lrud(*lrud)


if __name__ == '__main__':
    from PyQt5.QtWidgets import QApplication

    app = QApplication([])
    w = GeoRectWidget('sample')
    w.show()
    exit(app.exec_())
