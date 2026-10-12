"""Keep macOS widget chrome, without SF Symbols in small Qt controls.

During live resize a toolbar extension can briefly request a 1-pixel-high
icon. QAppleIconEngine passes that geometry to AppKit's symbol provider,
which can raise an Objective-C exception and abort the process. A Python
exception handler cannot recover from that crash. Use our own pixmap engine
for these internal controls before Qt creates them.
"""
import sys

from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QProxyStyle, QStyle, QStyleFactory

from ui.icons import icon


class MacSafeWidgetStyle(QProxyStyle):
    _glyphs = {
        QStyle.StandardPixmap.SP_ToolBarHorizontalExtensionButton: "overflow-horizontal",
        QStyle.StandardPixmap.SP_ToolBarVerticalExtensionButton: "overflow-vertical",
        QStyle.StandardPixmap.SP_TabCloseButton: "close",
        QStyle.StandardPixmap.SP_LineEditClearButton: "close",
    }

    def standardIcon(self, standard_icon, option=None, widget=None):
        glyph = self._glyphs.get(standard_icon)
        if glyph is not None:
            palette = option.palette if option is not None else (
                widget.palette() if widget is not None else self.standardPalette()
            )
            return icon(glyph, palette.color(QPalette.ColorRole.ButtonText).name())
        return super().standardIcon(standard_icon, option, widget)


def install_widget_style(app):
    """Install once, before widget construction, including detached windows."""
    if sys.platform != "darwin" or hasattr(app, "_acro_widget_style"):
        return
    # Create a fresh base. Passing app.style() transfers ownership of a style
    # that QApplication will delete when setStyle replaces it.
    base = QStyleFactory.create(app.style().objectName())
    if base is None:
        base = QStyleFactory.create("Fusion")
    style = MacSafeWidgetStyle(base)
    style.setObjectName("acropdf-macos-safe")
    app._acro_widget_style = style
    app.setStyle(style)
