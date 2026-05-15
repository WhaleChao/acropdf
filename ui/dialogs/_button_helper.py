# ~/Desktop/acropdf/ui/dialogs/_button_helper.py
"""
共用按鈕列：確定（或相同動作）在左、取消/關閉在右。
"""
from PyQt6.QtWidgets import QHBoxLayout, QPushButton


def make_ok_cancel_row(parent, ok_text: str = "確定", cancel_text: str = "取消",
                       ok_default: bool = True) -> tuple[QHBoxLayout, QPushButton, QPushButton]:
    """建立標準按鈕列：確定在左、取消在右。

    呼叫端須自行將 ok_btn.clicked 接到 accept()、cancel_btn.clicked 接到 reject()。
    回傳 (row, ok_btn, cancel_btn)；row 已是右對齊的 QHBoxLayout。
    """
    row = QHBoxLayout()
    row.addStretch()
    ok_btn = QPushButton(ok_text, parent)
    if ok_default:
        ok_btn.setDefault(True)
    cancel_btn = QPushButton(cancel_text, parent)
    row.addWidget(ok_btn)
    row.addWidget(cancel_btn)
    return row, ok_btn, cancel_btn
