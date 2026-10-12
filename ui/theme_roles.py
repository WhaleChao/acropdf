"""Semantic colors for live widgets, rich text and non-QObject item cells.

PDF ink and paper are document data and must never be recolored by a theme.
Overlay tokens remain legible over unchanged white PDF pages in both themes.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QTreeWidget, QTableWidget, QListWidget, QTreeWidgetItem, QLineEdit

ITEM_COLORS_ROLE = int(Qt.ItemDataRole.UserRole) + 0x4143


def color(role, alpha=None):
    from ui.theme import COLORS, theme_manager
    theme = theme_manager().resolved if QApplication.instance() else "light"
    result = QColor(COLORS[theme][role])
    if alpha is not None:
        result.setAlpha(alpha)
    return result


def set_role(widget, role):
    """QSS supplies the actual colors; changing a status also repolishes it."""
    widget.setProperty("role", role)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def set_themed_clear_button(edit):
    edit.setClearButtonEnabled(True)
    _refresh_clear_icon(edit)


def _refresh_clear_icon(edit):
    from ui.icons import icon
    action = edit.findChild(QAction, "_q_qlineeditclearaction")
    if action is not None:
        action.setIcon(icon("close", color("muted")))


def refresh_clear_icons(app):
    for edit in app.allWidgets():
        if isinstance(edit, QLineEdit) and edit.isClearButtonEnabled():
            _refresh_clear_icon(edit)


def set_item_colors(item, foreground=None, background=None, column=0):
    roles = {"foreground": foreground, "background": background}
    if isinstance(item, QTreeWidgetItem):
        item.setData(column, ITEM_COLORS_ROLE, roles)
        if foreground:
            item.setForeground(column, QBrush(color(foreground)))
        if background:
            item.setBackground(column, QBrush(color(background)))
    else:
        item.setData(ITEM_COLORS_ROLE, roles)
        if foreground:
            item.setForeground(QBrush(color(foreground)))
        if background:
            item.setBackground(QBrush(color(background)))


def refresh_item_colors(app):
    """Item brushes are cached data, so palette changes alone cannot fix them."""
    def update(item, column=0):
        if item is None:
            return
        roles = item.data(column, ITEM_COLORS_ROLE) if isinstance(item, QTreeWidgetItem) else item.data(ITEM_COLORS_ROLE)
        if isinstance(roles, dict):
            set_item_colors(item, roles.get("foreground"), roles.get("background"), column)

    def visit_tree(item, columns):
        for column in range(columns):
            update(item, column)
        for i in range(item.childCount()):
            visit_tree(item.child(i), columns)

    for view in app.allWidgets():
        if isinstance(view, QTreeWidget):
            for i in range(view.topLevelItemCount()):
                visit_tree(view.topLevelItem(i), view.columnCount())
        elif isinstance(view, QTableWidget):
            for row in range(view.rowCount()):
                for column in range(view.columnCount()):
                    update(view.item(row, column))
        elif isinstance(view, QListWidget):
            for i in range(view.count()):
                update(view.item(i))
