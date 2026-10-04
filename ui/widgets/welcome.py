"""A document studio welcome screen; all artwork is crisp native vector drawing."""
import os

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QFont
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout, QLabel, QPushButton, QFrame, QGridLayout, QScrollArea
from ui.theme import theme_manager, COLORS
from ui.icons import icon


class DocumentArtwork(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(190, 182)
        self.setAccessibleName("PDF 文件工作室插畫")
        theme_manager().changed.connect(self._theme_changed)

    def _theme_changed(self, theme):
        self.update()

    def paintEvent(self, event):
        c = COLORS[theme_manager().resolved]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(c["tint"]))
        p.drawEllipse(QRectF(5, 16, 171, 155))
        p.save(); p.translate(56, 24); p.rotate(12)
        p.setBrush(QColor(c["border"])); p.drawRoundedRect(QRectF(0, 0, 101, 132), 6, 6); p.restore()
        p.save(); p.translate(36, 18); p.rotate(-7)
        p.setPen(QPen(QColor(c["border"]), 1)); p.setBrush(QColor(c["surface"]))
        p.drawRoundedRect(QRectF(0, 0, 101, 132), 6, 6)
        p.setPen(QColor(c["accent"])); p.setFont(QFont("Helvetica Neue", 19, QFont.Weight.Bold))
        p.drawText(QRectF(15, 16, 72, 30), "PDF")
        for y, width in ((57, 63), (67, 63), (77, 41), (101, 63), (111, 49)):
            p.setPen(QPen(QColor(c["border"]), 3)); p.drawLine(16, y, 16 + width, y)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(c["tint"]))
        p.drawRoundedRect(QRectF(14, 83, 65, 7), 2, 2); p.restore()
        p.setBrush(QColor(c["accent"])); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(112, 123, 63, 33), 10, 10)
        p.setPen(QColor(c["bg"])); p.setFont(QFont("Helvetica Neue", 10, QFont.Weight.Bold))
        p.drawText(QRectF(112, 123, 63, 33), Qt.AlignmentFlag.AlignCenter, "LOCAL")


class WelcomePanel(QScrollArea):
    def __init__(self, parent):
        super().__init__(parent)
        self._main = parent
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget(); body.setObjectName("welcomePanel")
        self.setWidget(body)
        outer = QVBoxLayout(body); outer.setContentsMargins(32, 28, 32, 24); outer.addStretch(1)
        content = QWidget(); content.setMaximumWidth(840)
        self._content = content
        layout = QVBoxLayout(content); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(24)
        hero = QHBoxLayout(); hero.setSpacing(18)
        copy = QVBoxLayout(); copy.setSpacing(12)
        eyebrow = QLabel("ACROPDF  /  DOCUMENT STUDIO"); eyebrow.setObjectName("welcomeEyebrow")
        copy.addWidget(eyebrow)
        title = QLabel("讓文件，\n井然有序。"); title.setObjectName("welcomeTitle")
        copy.addWidget(title)
        sub = QLabel("閱讀、編輯與整理 PDF。\n把每一份重要文件，留在自己手中。")
        sub.setObjectName("welcomeSubtitle"); sub.setWordWrap(True); copy.addWidget(sub)
        actions = QHBoxLayout(); actions.setSpacing(8)
        self._open = QPushButton("開啟 PDF"); self._open.setProperty("role", "primary")
        self._open.setMinimumHeight(32); self._open.setAccessibleName("開啟 PDF 或可轉換文件")
        self._open.clicked.connect(parent.open_file_dialog)
        new = QPushButton("新增空白 PDF"); new.setMinimumHeight(32); new.clicked.connect(parent.new_document)
        actions.addWidget(self._open); actions.addWidget(new); actions.addStretch()
        copy.addLayout(actions); hero.addLayout(copy, 1)
        self._artwork = DocumentArtwork(); hero.addWidget(self._artwork)
        layout.addLayout(hero)
        divider = QFrame(); divider.setFrameShape(QFrame.Shape.HLine); layout.addWidget(divider)
        workflows = QHBoxLayout(); workflows.setSpacing(10)
        self._workflows = workflows
        self._cards = []
        for number, text, detail, glyph, callback in (
            ("01", "整理頁面", "合併、擷取與重新排序", "grid", parent._show_thumbnails),
            ("02", "編輯與標記", "文字、圖片與重點註解", "edit", parent._show_tools_center),
            ("03", "保護與匯出", "安全分享與格式轉換", "shield", parent._show_tools_center),
        ):
            card = QPushButton(f"{number}  {text}\n{detail}   →"); card.setObjectName("workflowCard")
            card.setMinimumHeight(68); card.setAccessibleName(f"{text}：{detail}")
            card.clicked.connect(callback); workflows.addWidget(card); self._cards.append((card, glyph))
        layout.addLayout(workflows)
        self._recent_frame = QFrame(); self._recent_frame.setObjectName("welcomeRecent")
        recent = QVBoxLayout(self._recent_frame); recent.setContentsMargins(18, 16, 18, 16); recent.setSpacing(12)
        heading = QHBoxLayout(); label = QLabel("繼續工作"); label.setObjectName("welcomeSectionTitle")
        heading.addWidget(label); heading.addStretch()
        self._clear = QPushButton("清除紀錄"); self._clear.setToolTip("只清除最近開啟紀錄，檔案會保留")
        self._clear.clicked.connect(self._clear_recent); heading.addWidget(self._clear)
        recent.addLayout(heading)
        self._recent_grid = QGridLayout(); self._recent_grid.setSpacing(8); recent.addLayout(self._recent_grid)
        layout.addWidget(self._recent_frame)
        hint = QLabel("拖入 PDF、圖片或 Office 文件，即可開始。  ·  ⌘ / Ctrl + O 開啟")
        hint.setWordWrap(True); hint.setObjectName("welcomeHint"); layout.addWidget(hint)
        outer.addWidget(content, alignment=Qt.AlignmentFlag.AlignHCenter); outer.addStretch(1)
        theme_manager().changed.connect(self._update_icons); self._update_icons(theme_manager().resolved)
        self.refresh_recent()

    def _update_icons(self, theme):
        color = COLORS[theme]["accent"]
        for button, glyph in self._cards: button.setIcon(icon(glyph, color))
        self._open.setIcon(icon("folder", COLORS[theme]["bg"]))

    def _clear_recent(self):
        self._main._config.set("recent_files", [])
        self._main._update_recent_menu(); self.refresh_recent()

    def refresh_recent(self):
        while self._recent_grid.count():
            item = self._recent_grid.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        recent = [p for p in self._main._config.recent_files if os.path.isfile(p)][:6]
        self._clear.setVisible(bool(recent))
        if not recent:
            label = QLabel("準備好下一份文件了。開啟檔案後，會在這裡留下捷徑。")
            label.setObjectName("emptyRecent"); label.setWordWrap(True); self._recent_grid.addWidget(label, 0, 0, 1, 2)
        for i, path in enumerate(recent):
            button = QPushButton(os.path.basename(path)); button.setObjectName("recentFileButton")
            button.setToolTip(path); button.setAccessibleName(f"開啟 {os.path.basename(path)}")
            button.clicked.connect(lambda checked=False, p=path: self._main.open_file(p))
            self._recent_grid.addWidget(button, i // 2, i % 2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._artwork.setVisible(self.width() >= 780)
        self._content.setFixedWidth(max(260, min(840, self.viewport().width() - 64)))
        self._workflows.setDirection(QBoxLayout.Direction.LeftToRight if self.width() >= 740 else QBoxLayout.Direction.TopToBottom)
