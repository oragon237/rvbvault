from __future__ import annotations

import math
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


@lru_cache(maxsize=128)
def icon(name: str, color: str = "#818892", size: int = 18) -> QIcon:
    """Small, consistent line icons rendered locally for crisp high-DPI controls."""
    scale = 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 1.55, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    s = float(size)

    if name == "search":
        painter.drawEllipse(QRectF(s * .19, s * .16, s * .48, s * .48))
        painter.drawLine(QPointF(s * .60, s * .59), QPointF(s * .82, s * .81))
    elif name == "plus":
        painter.drawLine(QPointF(s * .5, s * .22), QPointF(s * .5, s * .78))
        painter.drawLine(QPointF(s * .22, s * .5), QPointF(s * .78, s * .5))
    elif name in {"copy", "duplicate"}:
        painter.drawRoundedRect(QRectF(s * .29, s * .20, s * .51, s * .55), 2, 2)
        painter.drawRoundedRect(QRectF(s * .17, s * .32, s * .51, s * .55), 2, 2)
    elif name == "eye":
        path = QPainterPath(QPointF(s * .13, s * .51))
        path.cubicTo(s * .31, s * .25, s * .68, s * .25, s * .87, s * .51)
        path.cubicTo(s * .68, s * .77, s * .31, s * .77, s * .13, s * .51)
        painter.drawPath(path)
        painter.drawEllipse(QRectF(s * .42, s * .42, s * .16, s * .16))
    elif name == "sparkle":
        painter.drawLine(QPointF(s * .50, s * .13), QPointF(s * .50, s * .57))
        painter.drawLine(QPointF(s * .28, s * .35), QPointF(s * .72, s * .35))
        painter.drawLine(QPointF(s * .27, s * .63), QPointF(s * .27, s * .86))
        painter.drawLine(QPointF(s * .16, s * .745), QPointF(s * .39, s * .745))
    elif name == "trash":
        painter.drawRoundedRect(QRectF(s * .28, s * .31, s * .44, s * .53), 2, 2)
        painter.drawLine(QPointF(s * .22, s * .27), QPointF(s * .78, s * .27))
        painter.drawLine(QPointF(s * .39, s * .19), QPointF(s * .61, s * .19))
        painter.drawLine(QPointF(s * .42, s * .43), QPointF(s * .42, s * .72))
        painter.drawLine(QPointF(s * .58, s * .43), QPointF(s * .58, s * .72))
    elif name in {"star", "star_filled"}:
        path = QPainterPath()
        for i in range(10):
            angle = -math.pi / 2 + i * math.pi / 5
            radius = s * (.36 if i % 2 == 0 else .16)
            point = QPointF(s * .5 + math.cos(angle) * radius, s * .5 + math.sin(angle) * radius)
            path.moveTo(point) if i == 0 else path.lineTo(point)
        path.closeSubpath()
        if name == "star_filled":
            painter.setBrush(QColor(color))
        painter.drawPath(path)
    elif name == "clock":
        painter.drawEllipse(QRectF(s * .18, s * .18, s * .64, s * .64))
        painter.drawLine(QPointF(s * .50, s * .31), QPointF(s * .50, s * .53))
        painter.drawLine(QPointF(s * .50, s * .53), QPointF(s * .65, s * .61))
    elif name == "grid":
        for x in (.20, .56):
            for y in (.20, .56):
                painter.drawRoundedRect(QRectF(s * x, s * y, s * .24, s * .24), 2, 2)
    elif name == "folder":
        path = QPainterPath(QPointF(s * .15, s * .32))
        path.lineTo(s * .38, s * .32)
        path.lineTo(s * .46, s * .23)
        path.lineTo(s * .82, s * .23)
        path.lineTo(s * .87, s * .75)
        path.lineTo(s * .15, s * .75)
        path.closeSubpath()
        painter.drawPath(path)
    elif name == "more":
        painter.setBrush(QColor(color))
        for x in (.28, .5, .72):
            painter.drawEllipse(QRectF(s * x - 1.2, s * .5 - 1.2, 2.4, 2.4))
    elif name == "save":
        painter.drawRoundedRect(QRectF(s * .18, s * .16, s * .64, s * .68), 2, 2)
        painter.drawRect(QRectF(s * .31, s * .16, s * .36, s * .24))
        painter.drawRoundedRect(QRectF(s * .31, s * .57, s * .38, s * .27), 1.5, 1.5)
    elif name == "edit":
        painter.drawLine(QPointF(s * .23, s * .76), QPointF(s * .68, s * .31))
        painter.drawLine(QPointF(s * .30, s * .82), QPointF(s * .75, s * .37))
        painter.drawLine(QPointF(s * .23, s * .76), QPointF(s * .20, s * .86))
        painter.drawLine(QPointF(s * .68, s * .31), QPointF(s * .75, s * .37))
    elif name in {"up", "down"}:
        direction = -1 if name == "up" else 1
        y = s * .5
        painter.drawLine(QPointF(s * .27, y + direction * s * .12), QPointF(s * .5, y - direction * s * .12))
        painter.drawLine(QPointF(s * .5, y - direction * s * .12), QPointF(s * .73, y + direction * s * .12))
    elif name == "lock":
        painter.drawRoundedRect(QRectF(s * .23, s * .43, s * .54, s * .40), 2, 2)
        painter.drawArc(QRectF(s * .33, s * .18, s * .34, s * .45), 0, 180 * 16)
    else:
        painter.drawEllipse(QRectF(s * .27, s * .27, s * .46, s * .46))

    painter.end()
    return QIcon(pixmap)

