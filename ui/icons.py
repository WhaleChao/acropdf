"""Small, consistent vector icons, drawn locally at the display's pixel ratio."""
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QPen, QColor, QPainterPath


def icon(name, color="#14665e", size=20):
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 24, size / 24)
    p.setPen(QPen(QColor(color), 1.65, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    def line(x1, y1, x2, y2): p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    if name in ("file", "new", "text", "save"):
        p.drawRoundedRect(QRectF(5, 3, 14, 18), 2, 2)
        if name == "new":
            line(8, 12, 16, 12); line(12, 8, 12, 16)
        elif name == "save":
            p.drawRect(QRectF(8, 3, 8, 5)); p.drawRect(QRectF(8, 14, 8, 7))
        else:
            for y in (9, 13, 17): line(8, y, 16 if y != 17 else 13, y)
    elif name == "folder":
        path = QPainterPath(QPointF(3, 7)); path.lineTo(3, 5); path.lineTo(10, 5); path.lineTo(12, 8)
        path.lineTo(21, 8); path.lineTo(21, 19); path.lineTo(3, 19); path.closeSubpath(); p.drawPath(path)
    elif name in ("search", "zoom"):
        p.drawEllipse(QRectF(4, 3, 12, 12)); line(14, 14, 21, 21)
        if name == "zoom": line(7, 9, 13, 9); line(10, 6, 10, 12)
    elif name in ("grid", "tools"):
        for x in (4, 14):
            for y in (4, 14): p.drawRoundedRect(QRectF(x, y, 6, 6), 1, 1)
    elif name == "bookmark":
        path=QPainterPath(QPointF(6, 3)); path.lineTo(18, 3); path.lineTo(18, 21)
        path.lineTo(12, 16); path.lineTo(6, 21); path.closeSubpath(); p.drawPath(path)
    elif name == "moon":
        path=QPainterPath(); path.moveTo(16, 3); path.cubicTo(3, 0, 0, 17, 11, 21)
        path.cubicTo(18, 23, 23, 17, 21, 12); path.cubicTo(14, 17, 9, 8, 16, 3); p.drawPath(path)
    elif name == "sun":
        p.drawEllipse(QRectF(8, 8, 8, 8))
        for a,b,c,d in ((12,2,12,5),(12,19,12,22),(2,12,5,12),(19,12,22,12),(4,4,6,6),(18,18,20,20),(4,20,6,18),(18,6,20,4)): line(a,b,c,d)
    elif name == "shield":
        path=QPainterPath(QPointF(12, 2)); path.lineTo(21, 6); path.cubicTo(21, 16, 16, 20, 12, 22)
        path.cubicTo(8, 20, 3, 16, 3, 6); path.closeSubpath(); p.drawPath(path)
        line(8,12,11,15); line(11,15,16,9)
    elif name in ("edit", "highlight", "pen"):
        path=QPainterPath(QPointF(4, 20)); path.lineTo(5,15); path.lineTo(17,3); path.lineTo(21,7)
        path.lineTo(9,19); path.closeSubpath(); p.drawPath(path); line(14,6,18,10)
    elif name == "image":
        p.drawRoundedRect(QRectF(3,4,18,16),2,2); p.drawEllipse(QRectF(6,7,3,3))
        line(4,18,11,12); line(11,12,15,16); line(15,16,18,12); line(18,12,21,15)
    elif name == "hand":
        path=QPainterPath(QPointF(7,13)); path.lineTo(7,6); path.cubicTo(7,3,10,3,10,6)
        path.lineTo(10,11); path.lineTo(10,4); path.cubicTo(10,1,13,1,13,4)
        path.lineTo(13,11); path.lineTo(13,5); path.cubicTo(13,2,16,2,16,5)
        path.lineTo(16,12); path.lineTo(16,8); path.cubicTo(16,5,19,5,19,8)
        path.lineTo(19,15); path.cubicTo(19,24,11,23,7,20); path.lineTo(3,15)
        path.cubicTo(1,12,4,10,7,13); p.drawPath(path)
    elif name == "arrow":
        line(4,12,20,12); line(14,6,20,12); line(20,12,14,18)
    else:
        p.drawEllipse(QRectF(4,4,16,16)); line(8,12,16,12)
    p.end()
    return QIcon(pm)
