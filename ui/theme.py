"""Application-wide theme: one palette, one stylesheet, live OS following."""
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QDir, QTemporaryDir, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication
from app.config import Config

COLORS = {
    "light": dict(bg="#f4f3ef", surface="#ffffff", raised="#faf9f6", text="#202c32",
                  muted="#606d72", border="#d8ddda", accent="#14665e", tint="#e3eeea",
                  canvas="#e5e8e4", disabled="#606d72", gold="#a06124",
                  danger="#b52f3b", dangerTint="#fbe9eb", warning="#895012", warningTint="#fff0d6",
                  success="#1b704d", successTint="#e2f2e9",
                  overlayAccent="#14665e", overlayDanger="#b52f3b", overlaySuccess="#1b704d",
                  overlayWarning="#895012"),
    "dark": dict(bg="#151e23", surface="#1b282f", raised="#22323a", text="#ecf1ed",
                 muted="#afbfbe", border="#3c4c53", accent="#8ad6c2", tint="#293f3e",
                 canvas="#10181d", disabled="#afbfbe", gold="#e3b878",
                 danger="#ffacb3", dangerTint="#442c34", warning="#f3c47e", warningTint="#403526",
                 success="#93dbb4", successTint="#263e34",
                 overlayAccent="#195f57", overlayDanger="#a42f3a", overlaySuccess="#17613f",
                 overlayWarning="#90501c"),
}


class ThemeManager(QObject):
    changed = pyqtSignal(str)

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        app._acro_theme = self
        self.mode = Config().theme
        self.resolved = "light"
        # QSS caches image URLs; each theme gets a distinct locally generated
        # asset. Keep the directory alive for the lifetime of the application.
        self._icons = QTemporaryDir(QDir.tempPath() + "/acropdf_theme_XXXXXX")
        if not self._icons.isValid():
            raise RuntimeError("Unable to create theme icon directory")
        app.aboutToQuit.connect(self._icons.remove)
        template = (Path(__file__).parent.parent / "resources/icons/tab-close.svg").read_text(encoding="utf-8")
        for name, colors in COLORS.items():
            (Path(self._icons.path()) / f"close-{name}.svg").write_text(
                template.replace("@muted", colors["muted"]), encoding="utf-8")
            paths = {"down": "m3 5 5 5 5-5", "up": "m3 10 5-5 5 5", "check": "m3 8 3 3 7-7",
                     "partial": "m3 8h10"}
            for glyph, path in paths.items():
                for variant, role in (("normal", "bg" if glyph in ("check", "partial") else "muted"),
                                      ("disabled", "disabled")):
                    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
                           f'<path d="{path}" fill="none" stroke="{colors[role]}" stroke-width="2" '
                           'stroke-linecap="round" stroke-linejoin="round"/></svg>')
                    (Path(self._icons.path()) / f"{glyph}-{variant}-{name}.svg").write_text(svg, encoding="utf-8")
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
            "LinkVisited": "gold", "Accent": "accent", "BrightText": "text",
            "Light": "surface", "Midlight": "raised", "Mid": "muted", "Dark": "border", "Shadow": "canvas",
        }.items():
            palette.setColor(getattr(QPalette.ColorRole, role), QColor(colors[key]))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(colors["bg"]))
        for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText,
                     QPalette.ColorRole.PlaceholderText, QPalette.ColorRole.Link, QPalette.ColorRole.LinkVisited):
            palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(colors["disabled"]))
        self.app.setPalette(palette)
        source = (Path(__file__).parent.parent / "resources/styles/workspace.qss").read_text(encoding="utf-8")
        source = source.replace("@icons", (Path(__file__).parent.parent / "resources/icons").as_posix())
        source = source.replace("@closeIcon", (Path(self._icons.path()) / f"close-{self.resolved}.svg").as_posix())
        for glyph in ("down", "up", "check", "partial"):
            for variant in ("normal", "disabled"):
                source = source.replace(f"@{glyph}{variant.title()}Icon",
                                        (Path(self._icons.path()) / f"{glyph}-{variant}-{self.resolved}.svg").as_posix())
        # Longer names first: @danger must not consume @dangerTint.
        for key in sorted(colors, key=len, reverse=True):
            source = source.replace("@" + key, colors[key])
        self.app.setStyleSheet(source)
        from ui.theme_roles import refresh_item_colors, refresh_clear_icons
        refresh_item_colors(self.app)
        refresh_clear_icons(self.app)
        self.changed.emit(self.resolved)


def theme_manager():
    app = QApplication.instance()
    if not hasattr(app, "_acro_theme"):
        app._acro_theme = ThemeManager(app)
    return app._acro_theme
