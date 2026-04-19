"""
系统托盘图标模块 - 后台运行形态的主界面
功能：
1. 系统托盘图标 + 右键菜单
2. 状态窗口（小窗口显示计时信息）
3. 托盘提示气泡
"""

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QIcon, QPixmap, QPainter, QColor, QBrush
from PyQt5.QtWidgets import (
    QSystemTrayIcon, QMenu, QAction, QWidget,
    QVBoxLayout, QLabel, QHBoxLayout, QApplication, QSizePolicy
)


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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowStaysOnTopHint |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowCloseButtonHint
        )
        # 门店场景需足够宽高，避免大字号「已用时」等被裁切
        self.resize(1080, 780)
        self.setMinimumSize(1020, 700)
        self.setWindowTitle("计时计费 - 状态")
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #f7fbff;
            }
            QLabel {
                color: #1f2d3d;
            }
            QLabel#status_label {
                padding: 6px 4px 10px 4px;
            }
            QLabel#time_label {
                padding: 96px 36px 108px 36px;
            }
            QLabel#cost_label {
                padding: 8px 4px 12px 4px;
            }
            QLabel#process_label {
                padding: 6px 4px;
            }
            QLabel#hint_label {
                padding: 10px 4px 16px 4px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(24)
        layout.setContentsMargins(44, 36, 44, 36)

        wide_policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        wide_policy.setHorizontalStretch(1)

        # 状态标签
        self._status_label = QLabel("⏸ 未检测到目标程序")
        self._status_label.setObjectName("status_label")
        self._status_label.setFont(QFont("Microsoft YaHei", 20, QFont.Bold))
        self._status_label.setStyleSheet("color: #666666;")
        self._status_label.setSizePolicy(wide_policy)
        self._status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self._status_label)

        layout.addSpacing(24)

        # 计时显示（行高与左右留白按约三倍放大，避免大字号被裁成一条）
        self._time_label = QLabel("已用时：00:00:00")
        self._time_label.setObjectName("time_label")
        self._time_label.setFont(QFont("Microsoft YaHei", 40, QFont.Bold))
        self._time_label.setStyleSheet("color: #2c3e50;")
        self._time_label.setWordWrap(False)
        time_row_policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        time_row_policy.setHorizontalStretch(1)
        self._time_label.setSizePolicy(time_row_policy)
        self._time_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._time_label.setMinimumHeight(312)
        layout.addWidget(self._time_label)

        layout.addSpacing(24)

        # 费用显示
        self._cost_label = QLabel("预计费用：¥ 0.00")
        self._cost_label.setObjectName("cost_label")
        self._cost_label.setFont(QFont("Microsoft YaHei", 26))
        self._cost_label.setStyleSheet("color: #e74c3c;")
        self._cost_label.setSizePolicy(wide_policy)
        self._cost_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self._cost_label)

        # 进程名
        self._process_label = QLabel("")
        self._process_label.setObjectName("process_label")
        self._process_label.setFont(QFont("Microsoft YaHei", 16))
        self._process_label.setStyleSheet("color: #999999;")
        self._process_label.setSizePolicy(wide_policy)
        self._process_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self._process_label)

        self._hint_label = QLabel("检测到导出窗口后会暂停计时，并弹出收费页面。")
        self._hint_label.setObjectName("hint_label")
        self._hint_label.setWordWrap(True)
        self._hint_label.setFont(QFont("Microsoft YaHei", 15))
        self._hint_label.setStyleSheet("color: #607d8b;")
        self._hint_label.setSizePolicy(wide_policy)
        self._hint_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        layout.addWidget(self._hint_label)

        layout.addStretch()

    def set_running(self, is_running: bool):
        """设置运行状态"""
        status_pad = "padding: 6px 4px 10px 4px;"
        if is_running:
            self._status_label.setText("▶ 正在计时")
            self._status_label.setStyleSheet(f"color: #27ae60; {status_pad}")
        else:
            self._status_label.setText("⏸ 未检测到目标程序")
            self._status_label.setStyleSheet(f"color: #666666; {status_pad}")

    def update_time(self, time_str: str):
        """更新计时显示"""
        self._time_label.setText(f"已用时：{time_str}")

    def update_cost(self, minutes: int, rate: float):
        """更新费用显示"""
        total = minutes * rate
        self._cost_label.setText(f"预计费用：¥ {total:.2f}")

    def update_process(self, process_name: str):
        """更新进程名显示"""
        self._process_label.setText(f"监控进程：{process_name}")

    def reset_display(self):
        """重置所有显示"""
        self.set_running(False)
        self._time_label.setText("已用时：00:00:00")
        self._cost_label.setText("预计费用：¥ 0.00")


class TrayIconManager:
    """系统托盘图标管理器"""

    def __init__(self, config, parent=None):
        self._config = config
        self._status_widget = StatusWidget()

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
