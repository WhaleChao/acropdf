# ~/Desktop/acropdf/ui/dialogs/page_ops/page_properties_dialog.py
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLabel,
                              QDialogButtonBox, QFrame)
from PyQt6.QtCore import Qt
import fitz


class PagePropertiesDialog(QDialog):
    def __init__(self, doc, page_indices: list[int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("頁面屬性")
        self.setFixedWidth(360)
        self._setup_ui(doc, page_indices)

    def _setup_ui(self, doc, indices: list[int]):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        for idx in indices[:5]:  # 最多顯示 5 頁
            page = doc.fitz_doc[idx]
            r = page.rect
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            fl = QFormLayout(frame)
            fl.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            fl.addRow("頁碼：", QLabel(f"第 {idx + 1} 頁"))
            fl.addRow("尺寸：", QLabel(f"{r.width:.1f} × {r.height:.1f} pt"))
            mm_w = r.width * 25.4 / 72
            mm_h = r.height * 25.4 / 72
            fl.addRow("（mm）：", QLabel(f"{mm_w:.1f} × {mm_h:.1f} mm"))
            # 判斷方向
            orient = "橫向" if r.width > r.height else "直向"
            fl.addRow("方向：", QLabel(orient))
            # 旋轉角度
            rot = page.rotation
            fl.addRow("旋轉：", QLabel(f"{rot}°"))
            layout.addWidget(frame)

        if len(indices) > 5:
            layout.addWidget(QLabel(f"…共 {len(indices)} 頁，僅顯示前 5 頁"))

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.accept)
        layout.addWidget(btns)
