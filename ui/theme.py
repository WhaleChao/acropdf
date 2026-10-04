"""Application-wide theme: one palette, one stylesheet, live OS following."""
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication
from app.config import Config

COLORS = {
    "light": dict(bg="#f4f3ef", surface="#ffffff", raised="#faf9f6", text="#202c32",
                  muted="#606d72", border="#d8ddda", accent="#14665e", tint="#e3eeea",
                  canvas="#e5e8e4", disabled="#7a8485", gold="#a06124"),
    "dark": dict(bg="#151e23", surface="#1b282f", raised="#22323a", text="#ecf1ed",
                 muted="#afbfbe", border="#3c4c53", accent="#8ad6c2", tint="#293f3e",
                 canvas="#10181d", disabled="#89989b", gold="#e3b878"),
}


class ThemeManager(QObject):
    changed = pyqtSignal(str)

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.mode = Config().theme
        self.resolved = "light"
        app.styleHints().colorSchemeChanged.connect(self._system_changed)
        family = "Helvetica Neue" if __import__("sys").platform == "darwin" else "Segoe UI"
        app.setFont(QFont(family, 12))
        self.apply()

    def _system_changed(self, _scheme):
        if self.mode == "system":
            self.apply()

    def set_mode(self, mode):
        Config().theme = mode
        self.mode = mode
        self.apply()

    def apply(self):
        self.resolved = ("dark" if self.app.styleHints().colorScheme() == Qt.ColorScheme.Dark
                         else "light") if self.mode == "system" else self.mode
        colors = COLORS[self.resolved]
        palette = QPalette()
        for role, key in {
            "Window": "bg", "WindowText": "text", "Base": "surface", "AlternateBase": "raised",
            "Text": "text", "Button": "raised", "ButtonText": "text", "ToolTipBase": "surface",
            "ToolTipText": "text", "Highlight": "accent", "Link": "accent", "PlaceholderText": "muted",
        }.items():
            palette.setColor(getattr(QPalette.ColorRole, role), QColor(colors[key]))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(colors["bg"]))
        for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
            palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(colors["disabled"]))
        self.app.setPalette(palette)
        source = (Path(__file__).parent.parent / "resources/styles/workspace.qss").read_text(encoding="utf-8")
        source = source.replace("@icons", (Path(__file__).parent.parent / "resources/icons").as_posix())
        for key, value in colors.items():
            source = source.replace("@" + key, value)
        self.app.setStyleSheet(source)
        self.changed.emit(self.resolved)


def theme_manager():
    app = QApplication.instance()
    if not hasattr(app, "_acro_theme"):
        app._acro_theme = ThemeManager(app)
    return app._acro_theme
