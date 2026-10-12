"""Opt-in native verification of the sticky-note dialog and live themes."""
from pathlib import Path

from PyQt6.QtCore import Qt, QPoint, QPointF, QEvent
from PyQt6.QtGui import QColor, QPalette, QEnterEvent, QHoverEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QInputDialog, QPushButton, QLabel, QDialog, QVBoxLayout, QProgressBar

from ui.theme import COLORS, theme_manager
from ui.theme_roles import set_role


def verify_sticky_note_flow(app, window, screenshots=None):
    """Exercise the production page-parented modal, rather than a detached mock.

    Call only with a generated verification document: this adds and saves a
    test annotation. Timer callbacks report failures after closing the modal.
    """
    import tempfile
    import fitz
    from PyQt6.QtCore import QTimer
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QDialogButtonBox, QLineEdit
    from app.constants import ToolMode
    from ui.tools.annotation_tools import StickyNoteTool

    manager = theme_manager()
    previous = manager.mode
    view = window._current_view()
    page = view._page_widgets[0]
    doc = view._doc
    results, errors = [], []
    note = "AcroPDF sticky-note verification"
    initial_count = len(list(doc.fitz_doc[0].annots() or []))
    try:
        for initial in ("light", "dark"):
            manager.set_mode(initial)
            page = view._page_widgets[0]
            tool = StickyNoteTool(ToolMode.STICKY_NOTE, view, doc)
            assert tool._pdf_point(page, QPoint(80, 80)) is not None

            def inspect():
                dialog = app.activeModalWidget()
                try:
                    assert isinstance(dialog, QInputDialog), "Production sticky-note modal was not opened"
                    edit = dialog.findChild(QLineEdit)
                    box = dialog.findChild(QDialogButtonBox)
                    for theme in (initial, "dark" if initial == "light" else "light"):
                        manager.set_mode(theme)
                        for text in ("", note):
                            edit.setText(text)
                            QTest.qWait(20)
                            c = COLORS[theme]
                            assert dialog.palette().color(QPalette.ColorRole.Window) == QColor(c["bg"])
                            assert edit.palette().color(QPalette.ColorRole.Base) == QColor(c["surface"])
                            assert edit.palette().color(QPalette.ColorRole.Text) == QColor(c["text"])
                            for standard in (QDialogButtonBox.StandardButton.Ok, QDialogButtonBox.StandardButton.Cancel):
                                button = box.button(standard)
                                primary = button.isDefault() and button.isEnabled()
                                fg = c["bg"] if primary else c["text"] if button.isEnabled() else c["disabled"]
                                bg = c["accent"] if primary else c["surface"] if button.isEnabled() else c["raised"]
                                ratio = check_button(button, fg, bg, c["text"] if primary else None)
                                results.append(dict(theme=theme, entered_text=bool(text),
                                                    button=standard.name, contrast=ratio))
                            if screenshots:
                                folder = Path(screenshots)
                                folder.mkdir(parents=True, exist_ok=True)
                                assert dialog.grab().save(str(folder / f"page-sticky-{theme}-{'text' if text else 'empty'}.png"))
                    edit.setText(note)
                    box.button(QDialogButtonBox.StandardButton.Ok).click()
                except Exception as error:
                    errors.append(str(error))
                    if dialog is not None:
                        dialog.reject()

            QTimer.singleShot(50, inspect)
            event = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(80, 80),
                                Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                                Qt.KeyboardModifier.NoModifier)
            tool.mouse_release(page, event, QPoint(80, 80))
            assert not errors, errors
        annotations = list(doc.fitz_doc[0].annots() or [])
        assert len(annotations) == initial_count + 2, (len(annotations), initial_count, results)
        assert sum(a.info.get("content") == note for a in annotations) == 2
        with tempfile.TemporaryDirectory(prefix="acropdf_sticky_save_") as folder:
            target = Path(folder) / "annotated.pdf"
            assert doc.save(str(target)), "Sticky-note PDF save failed"
            with fitz.open(target) as saved:
                assert sum(a.info.get("content") == note for a in saved[0].annots() or []) == 2
        return dict(passed=True, production_modal=True, parent_is_pdf_page=True,
                    button_states=len(results), minimum_contrast=min(r["contrast"] for r in results),
                    live_theme_switch=True, entered_text_checked=True, annotations_saved=2,
                    measurements=results)
    finally:
        manager.set_mode(previous)


def contrast(foreground, background):
    def luminance(value):
        rgb = QColor(value).getRgbF()[:3]
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
        return sum(a * b for a, b in zip(linear, (.2126, .7152, .0722)))
    a, b = sorted((luminance(foreground), luminance(background)))
    return (b + .05) / (a + .05)


def check_button(button, foreground, background, inactive_background=None):
    """Inspect painted pixels; QSS can override colors outside QPalette."""
    image = button.grab().toImage()
    dpr = image.devicePixelRatio()
    actual_bg = image.pixelColor(round(12 * dpr), image.height() // 2)
    expected_backgrounds = [QColor(background)]
    if inactive_background is not None:
        expected_backgrounds.append(QColor(inactive_background))
    assert actual_bg in expected_backgrounds, (button.text(), actual_bg.name(), background)
    expected = QColor(foreground).getRgb()[:3]
    # Sample only the central interior, excluding rounded corners and border.
    hits = 0
    for y in range(round(7 * dpr), image.height() - round(7 * dpr)):
        for x in range(round(9 * dpr), image.width() - round(9 * dpr)):
            pixel = image.pixelColor(x, y).getRgb()[:3]
            if max(abs(a - b) for a, b in zip(pixel, expected)) <= 12:
                hits += 1
    assert hits >= 3, (button.text(), "Expected foreground was not painted", foreground)
    ratio = contrast(foreground, actual_bg)
    assert ratio >= 4.5, (button.text(), ratio)
    return round(ratio, 2)


def verify_theme_controls(app, screenshots=None):
    def hover(button, enabled):
        # Exercise the same widget state and events used by real pointer entry.
        # Cocoa suppresses OS entry for a background verification process.
        button.setAttribute(Qt.WidgetAttribute.WA_UnderMouse, enabled)
        center = QPointF(button.rect().center())
        app.sendEvent(button, QHoverEvent(QEvent.Type.HoverEnter if enabled else QEvent.Type.HoverLeave,
                                         center, QPointF(-2, -2)))
        button.update()

    manager = theme_manager()
    previous = manager.mode
    dialog = QInputDialog()
    dialog.setWindowTitle("新增便利貼")
    dialog.setLabelText("內容：")
    dialog.setOkButtonText("確定")
    dialog.setCancelButtonText("取消")
    dialog.setMinimumWidth(320)
    status = QDialog()
    layout = QVBoxLayout(status)
    labels = []
    for role in ("muted", "accent", "success", "warning", "danger",
                 "successBadge", "warningBadge", "dangerBadge"):
        label = QLabel(role)
        set_role(label, role)
        layout.addWidget(label)
        labels.append((role, label))
    progress = QProgressBar()
    progress.setValue(50)
    layout.addWidget(progress)
    dialog.show()
    measurements = []
    try:
        for theme in ("light", "dark", "light", "dark"):
            manager.set_mode(theme)
            c = COLORS[theme]
            app.setActiveWindow(dialog)
            QTest.qWait(30)
            assert dialog.palette().color(QPalette.ColorRole.Window) == QColor(c["bg"])
            for button in dialog.findChildren(QPushButton):
                primary = button.isDefault()
                for enabled in (True, False):
                    button.setEnabled(enabled)
                    # Moving outside the control reliably resets its hover state.
                    QTest.mouseMove(dialog, QPoint(2, 2))
                    app.sendEvent(button, QEvent(QEvent.Type.Leave))
                    hover(button, False)
                    QTest.qWait(10)
                    hover(button, False)
                    fg = c["bg"] if primary and enabled else c["text"] if enabled else c["disabled"]
                    bg = c["accent"] if primary and enabled else c["surface"] if enabled else c["raised"]
                    ratio = check_button(button, fg, bg)
                    measurements.append(dict(theme=theme, button=button.text(), enabled=enabled,
                                             state="normal", contrast=ratio))
                    QTest.mouseMove(button, button.rect().center())
                    # Cocoa may suppress enter events for a background process.
                    # Send the same Qt enter event, then inspect native painting.
                    center = button.rect().center()
                    app.sendEvent(button, QEnterEvent(QPointF(center), QPointF(center),
                                                     QPointF(button.mapToGlobal(center))))
                    hover(button, True)
                    QTest.qWait(10)
                    hover(button, True)
                    hover_bg = c["text"] if primary and enabled else c["tint"] if enabled else bg
                    native = app.platformName() in ("cocoa", "windows")
                    # Native platforms can suppress hover for automated windows
                    # independently of Qt's active-window flag. Accept only
                    # normal or hovered palette surfaces; verify actual glyphs
                    # and contrast on whichever surface the platform paints.
                    ratio = check_button(button, fg, hover_bg, bg if native else None)
                    measurements.append(dict(theme=theme, button=button.text(), enabled=enabled,
                                             state="hover", contrast=ratio))
                    if enabled:
                        QTest.mousePress(button, Qt.MouseButton.LeftButton)
                        QTest.qWait(10)
                        hover(button, True)
                        # Qt can promote the focused auto-default button during
                        # mouse press (including Cancel in QInputDialog).
                        pressed_primary = button.isDefault()
                        pressed_fg = c["bg"] if pressed_primary else c["text"]
                        pressed_bg = c["text"] if pressed_primary else c["tint"]
                        base_bg = c["accent"] if pressed_primary else c["tint"]
                        ratio = check_button(button, pressed_fg, pressed_bg, base_bg if native else None)
                        measurements.append(dict(theme=theme, button=button.text(), enabled=True,
                                                 state="pressed", contrast=ratio))
                        # Release outside to avoid accepting/rejecting the dialog.
                        QTest.mouseRelease(button, Qt.MouseButton.LeftButton, pos=QPoint(-2, -2))
            for role, label in labels:
                key = role.removesuffix("Badge")
                background = c[key + "Tint"] if role.endswith("Badge") else c["bg"]
                assert label.palette().color(QPalette.ColorRole.WindowText) == QColor(c[key])
                assert contrast(c[key], background) >= 4.5
            progress_image = progress.grab().toImage()
            dpr = progress_image.devicePixelRatio()
            for x, key in ((12, "tint"), (progress.width() - 12, "raised")):
                painted = progress_image.pixelColor(round(x * dpr), progress_image.height() // 2)
                assert painted == QColor(c[key]), (theme, key, painted.name())
                assert contrast(c["text"], painted) >= 4.5
            if screenshots:
                folder = Path(screenshots)
                folder.mkdir(parents=True, exist_ok=True)
                for button in dialog.findChildren(QPushButton):
                    button.setEnabled(not button.isDefault())
                    app.sendEvent(button, QEvent(QEvent.Type.Leave))
                    hover(button, False)
                QTest.mouseMove(dialog, QPoint(2, 2))
                QTest.qWait(10)
                assert dialog.grab().save(str(folder / f"sticky-note-{theme}.png"))
                status.show()
                app.processEvents()
                assert status.grab().save(str(folder / f"status-colors-{theme}.png"))
                status.hide()
        return dict(passed=True, live_theme_switches=4, button_states=len(measurements),
                    minimum_contrast=min(v["contrast"] for v in measurements),
                    semantic_labels=len(labels), progress_text_checked=True,
                    native_hover_surface_may_remain_normal=app.platformName() in ("cocoa", "windows"),
                    measurements=measurements)
    finally:
        dialog.close()
        status.close()
        manager.set_mode(previous)
        app.processEvents()
