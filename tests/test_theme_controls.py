"""Render-level contrast, cached item brushes and document/theme separation."""
from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QLabel

from ui.theme import COLORS, theme_manager
from ui.theme_roles import set_item_colors, set_role
from ui.theme_check import verify_theme_controls, contrast


def test_sticky_note_buttons_paint_readable_colors_across_live_themes(qapp):
    result = verify_theme_controls(qapp)
    assert result["button_states"] == 40
    assert result["minimum_contrast"] >= 4.5


def test_production_page_parented_sticky_note_can_retheme_and_save(qapp, sample_pdf):
    from ui.main_window import MainWindow
    from ui.theme_check import verify_sticky_note_flow
    window = MainWindow()
    window.show()
    window.open_file(str(sample_pdf))
    qapp.processEvents()
    try:
        result = verify_sticky_note_flow(qapp, window)
        assert result["button_states"] == 16
        assert result["minimum_contrast"] >= 4.5
        assert result["annotations_saved"] == 2
    finally:
        window.close()
        qapp.processEvents()


def test_native_hover_fallback_still_rejects_wrong_foreground(qapp):
    from PyQt6.QtWidgets import QPushButton
    from ui.theme_check import check_button
    theme_manager().set_mode("light")
    button = QPushButton("Readable")
    button.setDefault(True)
    button.show()
    qapp.processEvents()
    c = COLORS["light"]
    try:
        assert check_button(button, c["bg"], c["text"], c["accent"]) >= 4.5
        with pytest.raises(AssertionError, match="foreground"):
            check_button(button, "#123456", c["text"], c["accent"])
    finally:
        button.close()


def test_cached_warning_and_error_items_follow_live_theme(qapp):
    table = QTableWidget(1, 1)
    cell = QTableWidgetItem("low confidence")
    set_item_colors(cell, foreground="warning", background="warningTint")
    table.setItem(0, 0, cell)
    tree = QTreeWidget()
    tree.setColumnCount(2)
    parent = QTreeWidgetItem(tree, ["report"])
    child = QTreeWidgetItem(parent, ["page", "error"])
    set_item_colors(child, foreground="danger", column=1)
    try:
        for theme in ("dark", "light", "dark"):
            theme_manager().set_mode(theme)
            assert cell.foreground().color() == QColor(COLORS[theme]["warning"])
            assert cell.background().color() == QColor(COLORS[theme]["warningTint"])
            assert child.foreground(1).color() == QColor(COLORS[theme]["danger"])
    finally:
        table.deleteLater()
        tree.deleteLater()
        qapp.processEvents()


def test_status_role_can_change_without_reopening_dialog(qapp):
    label = QLabel("status")
    for theme in ("light", "dark"):
        theme_manager().set_mode(theme)
        for role in ("successBadge", "dangerBadge", "warningBadge"):
            set_role(label, role)
            assert label.palette().color(QPalette.ColorRole.WindowText) == QColor(COLORS[theme][role[:-5]])
    label.deleteLater()


def test_dependency_status_updates_use_live_roles_without_installing(qapp):
    from core.dependency_manager import Dependency, DependencyManager
    from ui.dialogs.dependency_dialog import DependencyDialog
    dependency = Dependency("Example", "Testing only", required=False, install_note="test note")
    dialog = DependencyDialog([dependency], DependencyManager())
    try:
        for theme in ("dark", "light"):
            theme_manager().set_mode(theme)
            for success, role in ((False, "danger"), (True, "success")):
                dialog._on_install_finished("Example", success, "verification")
                label = dialog._dep_widgets["Example"]["result_label"]
                assert label.palette().color(QPalette.ColorRole.WindowText) == QColor(COLORS[theme][role])
            assert dialog._dep_widgets["Example"]["status_label"].property("role") == "successBadge"
        assert not dialog._install_threads
    finally:
        dialog.deleteLater()


def test_theme_assets_use_system_temp_and_change_with_palette(qapp):
    from PyQt6.QtCore import QDir
    manager = theme_manager()
    folder = Path(manager._icons.path())
    assert folder.parent.resolve() == Path(QDir.tempPath()).resolve()
    for theme in ("light", "dark"):
        manager.set_mode(theme)
        assert COLORS[theme]["muted"] in (folder / f"close-{theme}.svg").read_text()
        assert f"close-{theme}.svg" in qapp.styleSheet()
        assert "@" not in qapp.styleSheet()


def test_line_edit_clear_icon_repaints_on_live_theme_switch(qapp):
    from PyQt6.QtWidgets import QLineEdit
    from PyQt6.QtGui import QAction
    from ui.theme_roles import set_themed_clear_button
    edit = QLineEdit("search")
    set_themed_clear_button(edit)
    images = []
    for theme in ("light", "dark"):
        theme_manager().set_mode(theme)
        action = edit.findChild(QAction, "_q_qlineeditclearaction")
        assert action.icon().availableSizes()
        images.append(action.icon().pixmap(20, 20).toImage())
    assert images[0] != images[1]
    edit.deleteLater()


def test_annotation_summary_screen_rethemes_export_remains_paper_readable(qapp):
    from ui.dialogs.annot_summary.annot_summary_dialog import AnnotSummaryDialog, _to_html
    with fitz.open() as pdf:
        pdf.new_page().add_text_annot((40, 40), "<review> & note")
        dialog = AnnotSummaryDialog(SimpleNamespace(fitz_doc=pdf))
        try:
            for theme in ("light", "dark", "light"):
                theme_manager().set_mode(theme)
                text = dialog._text_edit.document()
                cursor = text.find("<review> & note")
                assert not cursor.isNull()
                assert cursor.charFormat().foreground().color() == QColor(COLORS[theme]["text"])
            output = _to_html(dialog._entries)
            assert COLORS["light"]["text"] in output
            assert COLORS["light"]["surface"] in output
            assert "&lt;review&gt; &amp; note" in output
        finally:
            dialog.deleteLater()


def test_diff_text_is_escaped_and_live_theme_changes_its_brushes(qapp, sample_pdf):
    from ui.dialogs.compare.compare_result_dialog import CompareResultDialog
    diff = SimpleNamespace(page_num=0, visual_rects=[], text_added=["<b>added</b>"], text_removed=["& removed"])
    dialog = CompareResultDialog(str(sample_pdf), str(sample_pdf), dict(page_diffs=[diff], pages_with_diff=1))
    try:
        for theme in ("dark", "light"):
            theme_manager().set_mode(theme)
            doc = dialog._diff_text.document()
            assert "<b>added</b>" in doc.toPlainText()
            cursor = doc.find("added")
            assert cursor.charFormat().foreground().color() == QColor(COLORS[theme]["success"])
            assert cursor.charFormat().background().color() == QColor(COLORS[theme]["successTint"])
    finally:
        dialog.deleteLater()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_all_semantic_text_pairs_have_contrast(theme):
    c = COLORS[theme]
    for role in ("text", "muted", "disabled", "accent", "danger", "warning", "success"):
        for background in ("bg", "surface", "raised", "tint"):
            assert contrast(c[role], c[background]) >= 4.5, (theme, role, background)
    for role in ("danger", "warning", "success"):
        assert contrast(c[role], c[role + "Tint"]) >= 4.5
    for role in ("overlayAccent", "overlayDanger", "overlayWarning", "overlaySuccess"):
        assert contrast(c[role], QColor(Qt.GlobalColor.white)) >= 4.5


def test_ui_style_sources_only_use_theme_tokens():
    # Guard against reintroducing the original cross-theme inline color bug.
    import ast
    import re
    root = Path(__file__).parents[1]
    for source in (root / "ui").rglob("*.py"):
        if source.name == "theme.py":
            continue  # Palette definitions are the single source of color values.
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert not re.search(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b", node.value), source
                assert not re.search(r"(?:color|background)\s*:\s*(?:red|green|blue|white|black|orange)\b", node.value), source
    stylesheet = (root / "resources/styles/workspace.qss").read_text()
    assert not re.search(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b", stylesheet)
