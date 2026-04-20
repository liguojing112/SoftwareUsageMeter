"""
收费弹窗模块 - 全屏置顶的收费明细界面
功能：
1. 全屏置顶显示
2. 显示使用时长、计时单价、合计金额
3. 显示收款码图片
4. "确认收款"按钮（管理员操作）
5. 弹窗期间锁定像素蛋糕窗口
"""

import atexit
import logging
import os

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QPixmap, QColor, QPainter
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QApplication
)

try:
    import win32gui
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


_LOCKED_HWND_REGISTRY = set()


def _unlock_registered_windows():
    """Python 正常退出时恢复所有已被锁定的窗口。"""


    if not HAS_WIN32:
        return

    for hwnd in list(_LOCKED_HWND_REGISTRY):
        try:
            win32gui.EnableWindow(hwnd, True)
        except Exception:
            continue
        finally:
            _LOCKED_HWND_REGISTRY.discard(hwnd)


atexit.register(_unlock_registered_windows)

logger = logging.getLogger(__name__)


class _InlineConfig:
    """兼容独立调试/测试时直接传入收款码路径。"""

    def __init__(self, qr_code_path: str = ""):
        self.qr_code_path = qr_code_path
        self.rate = 1.0
        self.export_rate = 0.0


def calculate_payment_details(
    duration_minutes: int,
    rate: float,
    export_count: int = 0,
    export_rate: float = 0.0,
) -> dict:
    """统一计算计时费用、导出费用和合计金额。"""
    duration_minutes = max(int(duration_minutes), 0)
    export_count = max(int(export_count), 0)
    rate = max(float(rate), 0.0)
    export_rate = max(float(export_rate), 0.0)
    time_total = duration_minutes * rate
    export_total = export_count * export_rate
    return {
        "duration_minutes": duration_minutes,
        "rate": rate,
        "export_count": export_count,
        "export_rate": export_rate,
        "time_total": time_total,
        "export_total": export_total,
        "total": time_total + export_total,
    }


class PaymentOverlay(QWidget):
    """全屏置顶收费弹窗"""

    payment_completed = pyqtSignal()

    def __init__(self, config=None, parent=None, qr_code_path: str = ""):
        super().__init__(parent)
        self._config = config or _InlineConfig(qr_code_path)
        self._locked_hwnds = []
        self._payment_completion_emitted = False
        self._keep_top_timer = QTimer(self)
        self._keep_top_timer.setInterval(500)
        self._keep_top_timer.timeout.connect(self._keep_on_top)

        self._init_ui()
        self.update_display(
            0,
            float(getattr(self._config, "rate", 1.0)),
            export_count=0,
            export_rate=float(getattr(self._config, "export_rate", 0.0)),
        )
        self._load_qr_code()
        self._confirm_btn.pressed.connect(self._emit_payment_completed)

    def _init_ui(self):
        """初始化界面"""
        # 窗口属性：全屏、置顶、无边框
        self.setWindowFlags(
            Qt.Window |  # 独立窗口
            Qt.FramelessWindowHint |  # 无边框
            Qt.WindowStaysOnTopHint |  # 置顶
            Qt.Tool  # 不在任务栏显示
        )
        self.setWindowModality(Qt.ApplicationModal)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 230); color: white;")

        # 主布局
        layout = QVBoxLayout(self)
        layout.setSpacing(30)
        layout.setContentsMargins(80, 60, 80, 60)
        self._content_layout = layout

        # 标题
        title_label = QLabel("使 用 计 费")
        title_label.setFont(QFont("Microsoft YaHei", 48, QFont.Bold))
        title_label.setStyleSheet("color: #FFD700;")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #555555; background-color: #555555; max-height: 2px;")
        layout.addWidget(line)

        # 信息区域
        info_layout = QHBoxLayout()
        info_layout.setSpacing(60)

        # 左侧：计费信息
        info_container = QVBoxLayout()
        info_container.setSpacing(20)

        self._time_label = QLabel("使用时长：--")
        self._time_label.setFont(QFont("Microsoft YaHei", 28))
        self._time_label.setStyleSheet("color: #FFFFFF;")
        info_container.addWidget(self._time_label)

        self._rate_label = QLabel("计时单价：-- 元/分钟")
        self._rate_label.setFont(QFont("Microsoft YaHei", 28))
        self._rate_label.setStyleSheet("color: #FFFFFF;")
        info_container.addWidget(self._rate_label)

        self._time_amount_label = QLabel("计时费用：¥ 0.00")
        self._time_amount_label.setFont(QFont("Microsoft YaHei", 24))
        self._time_amount_label.setStyleSheet("color: #CFD8DC;")
        info_container.addWidget(self._time_amount_label)

        self._export_count_label = QLabel("导出张数：0 张")
        self._export_count_label.setFont(QFont("Microsoft YaHei", 28))
        self._export_count_label.setStyleSheet("color: #FFFFFF;")
        info_container.addWidget(self._export_count_label)

        self._export_rate_label = QLabel("单张导出单价：¥ 0.00 元/张")
        self._export_rate_label.setFont(QFont("Microsoft YaHei", 28))
        self._export_rate_label.setStyleSheet("color: #FFFFFF;")
        info_container.addWidget(self._export_rate_label)

        self._export_amount_label = QLabel("导出费用：¥ 0.00")
        self._export_amount_label.setFont(QFont("Microsoft YaHei", 24))
        self._export_amount_label.setStyleSheet("color: #CFD8DC;")
        info_container.addWidget(self._export_amount_label)

        self._amount_label = QLabel("合计金额：¥ --")
        self._amount_label.setFont(QFont("Microsoft YaHei", 36, QFont.Bold))
        self._amount_label.setStyleSheet("color: #FF6B6B;")
        info_container.addWidget(self._amount_label)

        # 提示
        hint_label = QLabel("请扫码支付，支付完成后由管理员确认")
        hint_label.setFont(QFont("Microsoft YaHei", 20))
        hint_label.setStyleSheet("color: #AAAAAA;")
        info_container.addWidget(hint_label)

        info_layout.addLayout(info_container, stretch=3)

        # 右侧：收款码
        qr_container = QVBoxLayout()
        qr_container.setAlignment(Qt.AlignCenter)

        qr_title = QLabel("扫码支付")
        qr_title.setFont(QFont("Microsoft YaHei", 24))
        qr_title.setStyleSheet("color: #FFFFFF;")
        qr_title.setAlignment(Qt.AlignCenter)
        qr_container.addWidget(qr_title)

        self._qr_label = QLabel()
        self._qr_label.setFixedSize(300, 300)
        self._qr_label.setStyleSheet(
            "background-color: white; border-radius: 10px; padding: 10px;"
        )
        self._qr_label.setAlignment(Qt.AlignCenter)
        self._qr_label.setScaledContents(True)
        qr_container.addWidget(self._qr_label, alignment=Qt.AlignCenter)

        info_layout.addLayout(qr_container, stretch=2)
        layout.addLayout(info_layout)

        # 确认收款按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._confirm_btn = QPushButton("已付款 · 确认收款")
        self._confirm_btn.setFont(QFont("Microsoft YaHei", 24, QFont.Bold))
        self._confirm_btn.setFixedSize(700, 110)
        self._confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 15px 40px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        btn_layout.addWidget(self._confirm_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 底部提示
        footer = QLabel("⚠ 支付完成后请告知工作人员确认收款")
        footer.setFont(QFont("Microsoft YaHei", 16))
        footer.setStyleSheet("color: #888888;")
        footer.setAlignment(Qt.AlignCenter)
        layout.addWidget(footer)

    def show_payment(
        self,
        minutes: int,
        rate: float,
        hwnd=None,
        lock_targets=None,
        export_count: int = 0,
        export_rate: float = 0.0,
    ):
        """
        显示收费弹窗
        :param minutes: 使用分钟数
        :param rate: 计时单价
        :param hwnd: 要锁定的窗口句柄
        :param lock_targets: 需要统一锁定的窗口句柄列表
        """
        # 更新显示
        self.update_display(minutes, rate, export_count=export_count, export_rate=export_rate)
        self._payment_completion_emitted = False

        # 通过全屏置顶遮罩层阻断操作，避免直接禁用外部窗口导致异常退出后残留不可点击状态
        self._locked_hwnds = []

        # 加载收款码
        self._load_qr_code()

        # 全屏显示
        self.show()
        self.raise_()
        self.activateWindow()
        self._confirm_btn.setFocus()

        # 启动置顶保持定时器
        self._keep_top_timer.start()

    def update_display(
        self,
        duration_minutes: int,
        rate: float,
        export_count: int = 0,
        export_rate: float = 0.0,
    ):
        """单独更新弹窗金额信息，便于调试和测试。"""
        details = calculate_payment_details(
            duration_minutes=duration_minutes,
            rate=rate,
            export_count=export_count,
            export_rate=export_rate,
        )
        self._time_label.setText(f"使用时长：{details['duration_minutes']} 分钟")
        self._rate_label.setText(f"计时单价：¥ {details['rate']:.2f} 元/分钟")
        self._export_count_label.setText(f"导出张数：{details['export_count']} 张")
        self._export_rate_label.setText(f"单张导出单价：¥ {details['export_rate']:.2f} 元/张")
        self._time_amount_label.setText(f"计时费用：¥ {details['time_total']:.2f}")
        self._export_amount_label.setText(f"导出费用：¥ {details['export_total']:.2f}")
        self._amount_label.setText(f"合计金额：¥ {details['total']:.2f}")

    def _lock_windows(self, handles: list[int]):
        """锁定像素蛋糕相关窗口，防止收费前继续操作。"""
        self._locked_hwnds = []
        if not HAS_WIN32:
            return

        for hwnd in handles:
            if not hwnd or hwnd in self._locked_hwnds:
                continue
            try:
                win32gui.EnableWindow(hwnd, False)
                self._locked_hwnds.append(hwnd)
                _LOCKED_HWND_REGISTRY.add(hwnd)
            except Exception:
                continue

    def _unlock_windows(self, handles: list[int] | None = None):
        if not HAS_WIN32:
            return

        for hwnd in list(handles or []):
            try:
                win32gui.EnableWindow(hwnd, True)
            except Exception:
                continue
            finally:
                _LOCKED_HWND_REGISTRY.discard(hwnd)

    def _load_qr_code(self):
        """加载收款码图片"""
        qr_path = self._config.qr_code_path
        if qr_path and os.path.exists(qr_path):
            pixmap = QPixmap(qr_path)
            if not pixmap.isNull():
                # 缩放到固定大小，保持宽高比
                scaled = pixmap.scaled(
                    280, 280,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self._qr_label.setPixmap(scaled)
                return

        # 没有收款码时显示占位图
        self._show_placeholder_qr()

    def _show_placeholder_qr(self):
        """显示收款码占位图"""
        pixmap = QPixmap(280, 280)
        pixmap.fill(QColor(255, 255, 255))
        painter = QPainter(pixmap)
        painter.setFont(QFont("Microsoft YaHei", 16))
        painter.setPen(QColor(150, 150, 150))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "请设置收款码")
        painter.end()
        self._qr_label.setPixmap(pixmap)

    def _keep_on_top(self):
        """保持窗口置顶（防止被其他窗口抢占焦点）"""
        if self.isVisible():
            self.raise_()

    def pause_keep_on_top(self):
        """临时暂停置顶保持，避免管理员确认对话框被遮挡。"""
        self._keep_top_timer.stop()

    def resume_keep_on_top(self):
        """恢复置顶保持。"""
        if self.isVisible():
            self._keep_top_timer.start()
            self.raise_()

    def _emit_payment_completed(self):
        """尽早发出确认收款信号，避免鼠标释放阶段被其他窗口抢焦点后丢失点击。"""
        if self._payment_completion_emitted:
            return

        self._payment_completion_emitted = True
        logger.info("收费框确认按钮已触发")
        self.payment_completed.emit()

    def showEvent(self, event):
        """确保通过任意方式显示时都铺满主屏幕。"""
        screen = QApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.availableGeometry())
        super().showEvent(event)

    def close_payment(self):
        """关闭收费弹窗并解锁目标窗口"""
        self._keep_top_timer.stop()
        self._payment_completion_emitted = False

        # 解锁目标窗口
        self._unlock_windows(self._locked_hwnds)
        self._locked_hwnds = []

        self.hide()

    def reset_payment_confirmation(self):
        """管理员未确认时，允许再次点击确认收款按钮。"""
        self._payment_completion_emitted = False
        if self.isVisible():
            self._confirm_btn.setFocus()

    def keyPressEvent(self, event):
        """禁用 ESC 等快捷键关闭弹窗"""
        # 不允许通过键盘关闭弹窗，只有点击"确认收款"才能关闭
        event.accept()

    def mousePressEvent(self, event):
        """吞掉背景区域鼠标点击，防止透传到底层导出界面。"""
        if self.childAt(event.pos()) is self._confirm_btn:
            super().mousePressEvent(event)
            return
        event.accept()

    def mouseReleaseEvent(self, event):
        if self.childAt(event.pos()) is self._confirm_btn:
            super().mouseReleaseEvent(event)
            return
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if self.childAt(event.pos()) is self._confirm_btn:
            super().mouseDoubleClickEvent(event)
            return
        event.accept()

    def closeEvent(self, event):
        """禁止通过关闭按钮关闭"""
        event.ignore()

    @property
    def confirm_button(self) -> QPushButton:
        """获取确认收款按钮的引用"""
        return self._confirm_btn

    @property
    def duration_label(self) -> QLabel:
        return self._time_label

    @property
    def rate_label(self) -> QLabel:
        return self._rate_label

    @property
    def export_count_label(self) -> QLabel:
        return self._export_count_label

    @property
    def export_rate_label(self) -> QLabel:
        return self._export_rate_label

    @property
    def time_amount_label(self) -> QLabel:
        return self._time_amount_label

    @property
    def export_amount_label(self) -> QLabel:
        return self._export_amount_label

    @property
    def amount_label(self) -> QLabel:
        return self._amount_label

    @property
    def pay_button(self) -> QPushButton:
        return self._confirm_btn

    @property
    def qr_label(self) -> QLabel:
        return self._qr_label

    @property
    def central_layout(self) -> QVBoxLayout:
        return self._content_layout
