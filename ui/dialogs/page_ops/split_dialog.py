# ~/Desktop/acropdf/ui/dialogs/page_ops/split_dialog.py
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QLineEdit, QPushButton, QFileDialog,
                              QMessageBox, QButtonGroup, QRadioButton, QFrame)


class SplitDialog(QDialog):
    def __init__(self, doc, preselected: list[int] = None, parent=None):
        super().__init__(parent)
        self._doc = doc
        self._preselected = sorted(preselected or [])
        self.setWindowTitle("分割 PDF")
        self.setFixedWidth(460)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel(f"文件共 {self._doc.page_count} 頁"))

        # ── 分割模式 ──────────────────────────────
        mode_frame = QFrame()
        mode_frame.setFrameShape(QFrame.Shape.StyledPanel)
        mode_layout = QVBoxLayout(mode_frame)
        mode_layout.setSpacing(6)

        self._mode_group = QButtonGroup(self)
        self._rb_points = QRadioButton("依分割點（輸入頁碼）")
        self._rb_each = QRadioButton("每頁獨立為一個檔案")
        self._rb_selection = QRadioButton(
            f"依選取頁面分割（{', '.join(str(p+1) for p in self._preselected)}）"
            if self._preselected else "依選取頁面分割（未選取）"
        )
        self._rb_selection.setEnabled(bool(self._preselected))

        self._mode_group.addButton(self._rb_points, 0)
        self._mode_group.addButton(self._rb_each, 1)
        self._mode_group.addButton(self._rb_selection, 2)

        mode_layout.addWidget(self._rb_points)
        mode_layout.addWidget(self._rb_each)
        mode_layout.addWidget(self._rb_selection)
        layout.addWidget(mode_frame)

        if self._preselected:
            self._rb_selection.setChecked(True)
        else:
            self._rb_points.setChecked(True)

        # ── 分割點輸入 ────────────────────────────
        self._points_label = QLabel("分割點頁碼（逗號分隔，例：5,10,15）：")
        layout.addWidget(self._points_label)
        self._split_edit = QLineEdit()
        self._split_edit.setPlaceholderText("例：5, 10, 15")
        layout.addWidget(self._split_edit)

        self._rb_points.toggled.connect(self._update_ui)
        self._rb_each.toggled.connect(self._update_ui)
        self._rb_selection.toggled.connect(self._update_ui)
        self._update_ui()

        # ── 輸出 ──────────────────────────────────
        layout.addWidget(QLabel("輸出資料夾："))
        dir_row = QHBoxLayout()
        self._dir_edit = QLineEdit()
        browse_btn = QPushButton("瀏覽...")
        browse_btn.setFixedWidth(70)
        browse_btn.clicked.connect(self._browse_dir)
        dir_row.addWidget(self._dir_edit)
        dir_row.addWidget(browse_btn)
        layout.addLayout(dir_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok = QPushButton("分割")
        ok.setDefault(True)
        ok.setFixedWidth(80)
        cancel = QPushButton("取消")
        cancel.setFixedWidth(80)
        ok.clicked.connect(self._do_split)
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(ok)
        btn_row.addWidget(cancel)
        layout.addLayout(btn_row)

    def _update_ui(self):
        is_points = self._rb_points.isChecked()
        self._points_label.setVisible(is_points)
        self._split_edit.setVisible(is_points)

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "選擇輸出資料夾")
        if d:
            self._dir_edit.setText(d)

    def _do_split(self):
        out_dir = self._dir_edit.text().strip()
        if not out_dir:
            QMessageBox.warning(self, "錯誤", "請選擇輸出資料夾")
            return
        try:
            mode = self._mode_group.checkedId()

            if mode == 1:
                # 每頁獨立
                ranges = [(i, i) for i in range(self._doc.page_count)]
            elif mode == 2:
                # 依選取頁面：在每個選取點前分割
                points = self._preselected
                boundaries = [0] + points + [self._doc.page_count]
                ranges = [(boundaries[i], boundaries[i+1] - 1)
                          for i in range(len(boundaries) - 1)
                          if boundaries[i] < boundaries[i+1]]
            else:
                # 依輸入點
                text = self._split_edit.text().strip()
                points = [int(x.strip()) for x in text.split(",") if x.strip()]
                points = sorted(set(points))
                boundaries = [0] + points + [self._doc.page_count]
                ranges = [(boundaries[i], boundaries[i+1] - 1)
                          for i in range(len(boundaries) - 1)
                          if boundaries[i] < boundaries[i+1]]

            paths = self._doc.pages.split_by_range(ranges, out_dir)
            QMessageBox.information(self, "完成", f"已分割為 {len(paths)} 個檔案")
            self.accept()
        except (ValueError, Exception) as e:
            QMessageBox.warning(self, "錯誤", str(e))
