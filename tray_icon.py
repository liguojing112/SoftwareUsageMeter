"""
系统托盘图标模块 - 后台运行形态的主界面
功能：
1. 系统托盘图标 + 右键菜单
2. 状态窗口（小窗口显示计时信息）
3. 托盘提示气泡
"""

import logging
import os
import sys

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QIcon, QPixmap, QPainter, QColor, QBrush, QLinearGradient
from PyQt5.QtWidgets import (
    QSystemTrayIcon, QMenu, QAction, QWidget,
    QVBoxLayout, QLabel, QHBoxLayout, QApplication, QSizePolicy, QFrame,
    QGraphicsDropShadowEffect, QScrollArea
)

logger = logging.getLogger(__name__)
ENABLE_UI_SHADOWS = not getattr(sys, "frozen", False)
SAFE_STATUS_WIDGET_MODE = bool(getattr(sys, "frozen", False))


def create_default_icon() -> QIcon:
    """创建默认的托盘图标（蓝底白色时钟图标）"""
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor(0, 0, 0, 0))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # 蓝色圆形背景
    painter.setBrush(QBrush(QColor(52, 152, 219)))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(4, 4, 56, 56)

    # 白色时钟指针
    painter.setPen(Qt.white)
    pen = painter.pen()
    pen.setWidth(3)
    painter.setPen(pen)

    # 时针
    painter.drawLine(32, 32, 32, 16)
    # 分针
    pen.setWidth(2)
    painter.setPen(pen)
    painter.drawLine(32, 32, 44, 28)

    # 中心点
    painter.setBrush(QBrush(Qt.white))
    painter.drawEllipse(29, 29, 6, 6)

    painter.end()
    return QIcon(pixmap)


def create_running_icon() -> QIcon:
    """创建运行中状态的托盘图标（绿色底）"""
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor(0, 0, 0, 0))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # 绿色圆形背景
    painter.setBrush(QBrush(QColor(46, 204, 113)))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(4, 4, 56, 56)

    # 白色时钟指针
    painter.setPen(Qt.white)
    pen = painter.pen()
    pen.setWidth(3)
    painter.setPen(pen)
    painter.drawLine(32, 32, 32, 16)
    pen.setWidth(2)
    painter.setPen(pen)
    painter.drawLine(32, 32, 44, 28)
    painter.setBrush(QBrush(Qt.white))
    painter.drawEllipse(29, 29, 6, 6)

    painter.end()
    return QIcon(pixmap)


class StatusWidget(QWidget):
    """状态显示小窗口"""

    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self._config = config
        self._safe_mode = SAFE_STATUS_WIDGET_MODE
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowStaysOnTopHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowCloseButtonHint
        )
        # 门店场景需足够宽高，避免大字号「已用时」等被裁切
        self.resize(1080, 860)
        self.setMinimumSize(1020, 780)
        self.setWindowTitle("计时计费 - 状态")
        self._wallpaper_pixmap = None
        if not self._safe_mode:
            self._load_wallpaper()
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._init_ui()
        logger.info(
            "状态页初始化: safe_mode=%s, wallpaper_enabled=%s, shadows_enabled=%s",
            self._safe_mode,
            not self._safe_mode,
            ENABLE_UI_SHADOWS,
        )

    def _init_ui(self):
        self.setAutoFillBackground(self._safe_mode)
        self.setObjectName("StatusWidgetRoot")
        root_bg = "#eef3f8" if self._safe_mode else "transparent"
        shell_bg = (
            "rgba(255, 255, 255, 0.92)"
            if self._safe_mode
            else "rgba(255, 255, 255, 0.26)"
        )
        shell_border = (
            "rgba(185, 196, 210, 0.92)"
            if self._safe_mode
            else "rgba(255, 255, 255, 0.58)"
        )
        card_bg = (
            "rgba(255, 255, 255, 0.96)"
            if self._safe_mode
            else "rgba(255, 255, 255, 0.26)"
        )
        card_border = (
            "rgba(198, 208, 220, 0.88)"
            if self._safe_mode
            else "rgba(255, 255, 255, 0.44)"
        )
        self.setStyleSheet(f"""
            QWidget#StatusWidgetRoot {{ background: {root_bg}; }}
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: rgba(255, 255, 255, 0.10);
                width: 12px;
                border-radius: 6px;
                margin: 12px 0 12px 0;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 0.72);
                min-height: 42px;
                border-radius: 6px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QFrame#statusShell {{
                background-color: {shell_bg};
                border: 1px solid {shell_border};
                border-radius: 28px;
            }}
            QFrame#statusMetricCard {{
                background-color: {card_bg};
                border: 1px solid {card_border};
                border-radius: 24px;
            }}
            QLabel {{ color: #102033; background: transparent; }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(18, 18, 18, 18)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(scroll_area)

        content = QWidget()
        content.setAttribute(Qt.WA_StyledBackground, True)
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(10, 8, 10, 8)
        content_layout.setSpacing(0)
        scroll_area.setWidget(content)

        shell = QFrame(self)
        shell.setObjectName("statusShell")
        if ENABLE_UI_SHADOWS:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(40)
            shadow.setOffset(0, 18)
            shadow.setColor(QColor(0, 0, 0, 110))
            shell.setGraphicsEffect(shadow)
        content_layout.addWidget(shell)

        shell_layout = QVBoxLayout(shell)
        shell_layout.setSpacing(26)
        shell_layout.setContentsMargins(34, 30, 34, 34)

        wide_policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        wide_policy.setHorizontalStretch(1)

        header_eyebrow = QLabel("LIVE MONITOR · 终端状态")
        header_eyebrow.setFont(QFont("Microsoft YaHei", 13, QFont.Bold))
        header_eyebrow.setStyleSheet("color: #3f6fc2; letter-spacing: 1px;")
        shell_layout.addWidget(header_eyebrow)

        title = QLabel("当前计时与收费状态")
        title.setFont(QFont("Microsoft YaHei", 28, QFont.Bold))
        title.setStyleSheet("color: #102033;")
        shell_layout.addWidget(title)

        subtitle = QLabel("后台已接管导出检测，触发收费时会自动暂停导出。")
        subtitle.setFont(QFont("Microsoft YaHei", 14))
        subtitle.setStyleSheet("color: rgba(16, 32, 51, 0.72);")
        shell_layout.addWidget(subtitle)

        self._status_label = QLabel("⏸ 未检测到目标程序")
        self._status_label.setObjectName("status_label")
        self._status_label.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        self._status_label.setStyleSheet(
            """
            color: #e7fff2;
            background-color: rgba(33, 128, 86, 0.28);
            border: 1px solid rgba(33, 128, 86, 0.46);
            border-radius: 16px;
            padding: 10px 16px;
            """
        )
        self._status_label.setSizePolicy(wide_policy)
        self._status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        shell_layout.addWidget(self._status_label)

        hero_card = QFrame()
        hero_card.setObjectName("statusMetricCard")
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setContentsMargins(30, 30, 30, 34)
        hero_layout.setSpacing(12)

        hero_hint = QLabel("已用时")
        hero_hint.setFont(QFont("Microsoft YaHei", 16))
        hero_hint.setStyleSheet("color: rgba(16, 32, 51, 0.58);")
        hero_layout.addWidget(hero_hint)

        self._time_label = QLabel("00:00:00")
        self._time_label.setObjectName("time_label")
        self._time_label.setFont(QFont("Microsoft YaHei", 46, QFont.Bold))
        self._time_label.setStyleSheet("color: #102033;")
        self._time_label.setWordWrap(False)
        time_row_policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        time_row_policy.setHorizontalStretch(1)
        self._time_label.setSizePolicy(time_row_policy)
        self._time_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._time_label.setMinimumHeight(190)
        hero_layout.addWidget(self._time_label)
        hero_card.setMinimumHeight(270)
        shell_layout.addWidget(hero_card)

        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(18)

        fee_card = QFrame()
        fee_card.setObjectName("statusMetricCard")
        fee_layout = QVBoxLayout(fee_card)
        fee_layout.setContentsMargins(22, 20, 22, 20)
        fee_layout.setSpacing(10)
        fee_hint = QLabel("预计费用")
        fee_hint.setFont(QFont("Microsoft YaHei", 14))
        fee_hint.setStyleSheet("color: rgba(16, 32, 51, 0.58);")
        fee_layout.addWidget(fee_hint)

        self._cost_label = QLabel("¥ 0.00")
        self._cost_label.setObjectName("cost_label")
        self._cost_label.setFont(QFont("Microsoft YaHei", 30, QFont.Bold))
        self._cost_label.setStyleSheet("color: #f39b2f;")
        self._cost_label.setSizePolicy(wide_policy)
        self._cost_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        fee_layout.addWidget(self._cost_label)
        fee_card.setMinimumHeight(150)
        metrics_row.addWidget(fee_card, 3)

        process_card = QFrame()
        process_card.setObjectName("statusMetricCard")
        process_layout = QVBoxLayout(process_card)
        process_layout.setContentsMargins(22, 20, 22, 20)
        process_layout.setSpacing(8)
        process_hint = QLabel("监控进程")
        process_hint.setFont(QFont("Microsoft YaHei", 14))
        process_hint.setStyleSheet("color: rgba(16, 32, 51, 0.58);")
        process_layout.addWidget(process_hint)

        self._process_label = QLabel("未设置")
        self._process_label.setObjectName("process_label")
        self._process_label.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
        self._process_label.setStyleSheet("color: #1b365d;")
        self._process_label.setSizePolicy(wide_policy)
        self._process_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._process_label.setWordWrap(True)
        process_layout.addWidget(self._process_label)
        process_card.setMinimumHeight(150)
        metrics_row.addWidget(process_card, 2)
        shell_layout.addLayout(metrics_row)

        self._hint_label = QLabel("检测到导出窗口后会暂停计时，并弹出收费页面。")
        self._hint_label.setObjectName("hint_label")
        self._hint_label.setWordWrap(True)
        self._hint_label.setFont(QFont("Microsoft YaHei", 14))
        self._hint_label.setStyleSheet("color: rgba(16, 32, 51, 0.62);")
        self._hint_label.setSizePolicy(wide_policy)
        self._hint_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        shell_layout.addWidget(self._hint_label)

        shell_layout.addStretch()

    def _load_wallpaper(self):
        """加载壁纸"""
        if self._safe_mode:
            self._wallpaper_pixmap = None
            return
        if self._config is None:
            self._wallpaper_pixmap = None
            return
        wp_path = getattr(self._config, "wallpaper_path", "")
        if wp_path and os.path.exists(wp_path):
            pixmap = QPixmap(wp_path)
            if not pixmap.isNull():
                self._wallpaper_pixmap = pixmap
                return
        self._wallpaper_pixmap = None

    def paintEvent(self, event):
        """绘制壁纸背景"""
        if self._safe_mode:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        if self._wallpaper_pixmap and not self._wallpaper_pixmap.isNull():
            scaled = self._wallpaper_pixmap.scaled(
                self.size(),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation
            )
            x = (scaled.width() - self.width()) // 2
            y = (scaled.height() - self.height()) // 2
            cropped = scaled.copy(x, y, self.width(), self.height())
            painter.setOpacity(0.68)
            painter.drawPixmap(0, 0, cropped)
            painter.setOpacity(1.0)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0.0, QColor(255, 255, 255, 24))
        gradient.setColorAt(0.5, QColor(222, 232, 244, 42))
        gradient.setColorAt(1.0, QColor(208, 220, 236, 62))
        painter.fillRect(self.rect(), gradient)
        painter.end()
        super().paintEvent(event)

    def showEvent(self, event):
        logger.info(
            "状态页显示: safe_mode=%s, size=%sx%s",
            self._safe_mode,
            self.width(),
            self.height(),
        )
        super().showEvent(event)

    def set_running(self, is_running: bool):
        """设置运行状态"""
        if is_running:
            self._status_label.setText("▶ 正在计时")
            self._status_label.setStyleSheet(
                """
                color: #effff6;
                background-color: rgba(33, 128, 86, 0.28);
                border: 1px solid rgba(33, 128, 86, 0.42);
                border-radius: 16px;
                padding: 10px 16px;
                """
            )
        else:
            self._status_label.setText("⏸ 未检测到目标程序")
            self._status_label.setStyleSheet(
                """
                color: #25354b;
                background-color: rgba(255, 255, 255, 0.32);
                border: 1px solid rgba(255, 255, 255, 0.5);
                border-radius: 16px;
                padding: 10px 16px;
                """
            )

    def update_time(self, time_str: str):
        """更新计时显示"""
        self._time_label.setText(time_str)

    def update_cost(self, minutes: int, rate: float):
        """更新费用显示"""
        total = minutes * rate
        self._cost_label.setText(f"¥ {total:.2f}")

    def update_process(self, process_name: str):
        """更新进程名显示"""
        self._process_label.setText(process_name or "未设置")

    def reset_display(self):
        """重置所有显示"""
        self.set_running(False)
        self._time_label.setText("00:00:00")
        self._cost_label.setText("¥ 0.00")


class TrayIconManager:
    """系统托盘图标管理器"""

    def __init__(self, config, parent=None):
        self._config = config
        self._status_widget = StatusWidget(config=config)

        # 创建托盘图标
        self._tray = QSystemTrayIcon(create_default_icon(), parent)
        self._tray.setToolTip("计时计费系统 - 等待中")

        # 创建菜单
        self._menu = QMenu()

        self._show_action = QAction("显示状态", parent)
        self._menu.addAction(self._show_action)

        self._admin_action = QAction("管理设置", parent)
        self._menu.addAction(self._admin_action)

        self._manual_trigger_action = QAction("手动触发收费", parent)
        self._menu.addAction(self._manual_trigger_action)

        self._menu.addSeparator()

        self._quit_action = QAction("退出", parent)
        self._menu.addAction(self._quit_action)

        self._tray.setContextMenu(self._menu)

        # 双击托盘图标显示状态窗口
        self._tray.activated.connect(self._on_activated)

    def show(self):
        """显示托盘图标"""
        self._tray.show()

    def _on_activated(self, reason):
        """托盘图标激活事件"""
        if reason == QSystemTrayIcon.DoubleClick:
            logger.info("托盘双击，准备显示状态页")
            self._status_widget.show()
            self._status_widget.raise_()
            self._status_widget.activateWindow()

    def set_running_state(self, is_running: bool):
        """更新运行状态图标和提示"""
        if is_running:
            self._tray.setIcon(create_running_icon())
            self._tray.setToolTip("计时计费系统 - 正在计时")
            self._status_widget.set_running(True)
        else:
            self._tray.setIcon(create_default_icon())
            self._tray.setToolTip("计时计费系统 - 等待中")
            self._status_widget.set_running(False)

    def update_timing(self, time_str: str, minutes: int, rate: float):
        """更新计时信息"""
        self._status_widget.update_time(time_str)
        self._status_widget.update_cost(minutes, rate)

    def update_process_name(self, name: str):
        """更新监控进程名"""
        self._status_widget.update_process(name)

    def show_notification(self, title: str, message: str):
        """显示托盘通知"""
        self._tray.showMessage(title, message, QSystemTrayIcon.Information, 3000)

    def reset(self):
        """重置显示"""
        self._status_widget.reset_display()
        self.set_running_state(False)

    @property
    def show_action(self) -> QAction:
        return self._show_action

    @property
    def admin_action(self) -> QAction:
        return self._admin_action

    @property
    def manual_trigger_action(self) -> QAction:
        return self._manual_trigger_action

    @property
    def quit_action(self) -> QAction:
        return self._quit_action

    @property
    def status_widget(self) -> StatusWidget:
        return self._status_widget

    @property
    def tray(self) -> QSystemTrayIcon:
        return self._tray
