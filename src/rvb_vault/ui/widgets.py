from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPalette
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem, QToolButton, QWidget

from rvb_vault.ui.icons import icon


ENTRY_TITLE_ROLE = Qt.ItemDataRole.UserRole + 1
ENTRY_META_ROLE = Qt.ItemDataRole.UserRole + 2
ENTRY_FAVORITE_ROLE = Qt.ItemDataRole.UserRole + 3


def configure_tool_button(
    button: QToolButton,
    icon_name: str,
    tooltip: str,
    *,
    text: str = "",
    danger: bool = False,
) -> QToolButton:
    button.setIcon(icon(icon_name, "#c65b55" if danger else "#858c96"))
    button.setIconSize(QSize(16, 16))
    button.setToolTip(tooltip)
    button.setAccessibleName(tooltip)
    button.setText(text)
    button.setToolButtonStyle(
        Qt.ToolButtonStyle.ToolButtonTextBesideIcon if text else Qt.ToolButtonStyle.ToolButtonIconOnly
    )
    button.setProperty("danger", danger)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class EntryListDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):  # noqa: N802
        return QSize(option.rect.width(), 55)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(option.rect).adjusted(2, 2, -2, -2)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hovered:
            dark = option.palette.color(QPalette.ColorRole.Window).lightness() < 128
            if selected:
                color = QColor(255, 255, 255, 18) if dark else QColor(25, 30, 37, 20)
            else:
                color = QColor(255, 255, 255, 9) if dark else QColor(25, 30, 37, 9)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(rect, 7, 7)

        title = str(index.data(ENTRY_TITLE_ROLE) or "")
        meta = str(index.data(ENTRY_META_ROLE) or "")
        favorite = bool(index.data(ENTRY_FAVORITE_ROLE))
        text_color = option.palette.color(QPalette.ColorRole.Text)
        muted = option.palette.color(QPalette.ColorRole.PlaceholderText)
        left = rect.left() + 10
        right_pad = 31 if favorite else 10
        title_rect = QRectF(left, rect.top() + 7, rect.width() - 10 - right_pad, 20)
        meta_rect = QRectF(left, rect.top() + 29, rect.width() - 10 - right_pad, 17)
        title_font = QFont(option.font)
        title_font.setWeight(QFont.Weight.DemiBold if selected else QFont.Weight.Medium)
        painter.setFont(title_font)
        painter.setPen(text_color)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
        meta_font = QFont(option.font)
        meta_font.setPointSizeF(max(9.0, option.font.pointSizeF() - 1))
        painter.setFont(meta_font)
        painter.setPen(muted)
        painter.drawText(meta_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, meta)
        if favorite:
            star = icon("star_filled", "#9097a1", 15).pixmap(15, 15)
            painter.drawPixmap(int(rect.right() - 23), int(rect.top() + 10), star)
        painter.restore()
