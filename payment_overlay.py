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
import sys

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QPixmap, QColor, QPainter, QLinearGradient
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QApplication, QGraphicsDropShadowEffect
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
ENABLE_UI_SHADOWS = not getattr(sys, "frozen", False)

_OVERLAY_CARD_BG = "rgba(255, 255, 255, 0.74)"
_OVERLAY_PANEL_BG = "rgba(255, 255, 255, 0.42)"
_OVERLAY_PANEL_BORDER = "rgba(255, 255, 255, 0.65)"


class _InlineConfig:
    """兼容独立调试/测试时直接传入收款码路径。"""

    def __init__(self, qr_code_path: str = "", wallpaper_path: str = ""):
        self.qr_code_path = qr_code_path
        self.wechat_qr_code_path = qr_code_path
        self.alipay_qr_code_path = qr_code_path
        self.wallpaper_path = wallpaper_path
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
        self._config = config or _InlineConfig(qr_code_path=qr_code_path)
        self._locked_hwnds = []
        self._payment_completion_emitted = False
        self._keep_top_timer = QTimer(self)
        self._keep_top_timer.setInterval(500)
        self._keep_top_timer.timeout.connect(self._keep_on_top)

        # 壁纸相关
        self._wallpaper_pixmap = None
        self._wallpaper_opacity = 0.58  # 提高壁纸存在感

        self._init_ui()
        self.update_display(
            0,
            float(getattr(self._config, "rate", 1.0)),
            export_count=0,
            export_rate=float(getattr(self._config, "export_rate", 0.0)),
        )
        self._load_qr_code()
        self._load_wallpaper()
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
        self.setStyleSheet("color: white;")

        root_layout = QVBoxLayout(self)
        root_layout.setSpacing(0)
        root_layout.setContentsMargins(48, 18, 48, 18)

        shell = QFrame(self)
        shell.setObjectName("paymentShell")
        shell.setStyleSheet(
            f"""
            QFrame#paymentShell {{
                background-color: {_OVERLAY_CARD_BG};
                border: 1px solid rgba(255, 255, 255, 168);
                border-radius: 32px;
            }}
            QFrame#paymentMetricPanel, QFrame#paymentQrPanel, QFrame#paymentTotalPanel {{
                background-color: {_OVERLAY_PANEL_BG};
                border: 1px solid {_OVERLAY_PANEL_BORDER};
                border-radius: 24px;
            }}
            """
        )
        if ENABLE_UI_SHADOWS:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(42)
            shadow.setOffset(0, 20)
            shadow.setColor(QColor(0, 0, 0, 110))
            shell.setGraphicsEffect(shadow)
        shell.setMinimumHeight(940)
        root_layout.addWidget(shell, alignment=Qt.AlignCenter)

        layout = QVBoxLayout(shell)
        layout.setSpacing(30)
        layout.setContentsMargins(42, 36, 42, 40)
        self._content_layout = layout

        eyebrow = QLabel("AUTO BILLING · 自助修图计费")
        eyebrow.setAlignment(Qt.AlignCenter)
        eyebrow.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        eyebrow.setStyleSheet("color: #4b74c6; letter-spacing: 1px;")
        layout.addWidget(eyebrow)

        title_label = QLabel("请先完成本次付费")
        title_label.setFont(QFont("Microsoft YaHei", 34, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #18263a;")
        layout.addWidget(title_label)

        subtitle = QLabel("收费确认后，系统会恢复导出操作。")
        subtitle.setFont(QFont("Microsoft YaHei", 16))
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: rgba(24, 38, 58, 0.72);")
        layout.addWidget(subtitle)

        body_layout = QHBoxLayout()
        body_layout.setSpacing(22)

        info_panel = QFrame()
        info_panel.setObjectName("paymentMetricPanel")
        info_panel_layout = QVBoxLayout(info_panel)
        info_panel_layout.setSpacing(18)
        info_panel_layout.setContentsMargins(24, 24, 24, 30)

        info_title = QLabel("本次费用明细")
        info_title.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
        info_title.setStyleSheet("color: #233247;")
        info_panel_layout.addWidget(info_title)

        self._time_label = QLabel("使用时长：--")
        self._time_label.setFont(QFont("Microsoft YaHei", 24, QFont.Bold))
        self._time_label.setStyleSheet("color: #18263a;")
        info_panel_layout.addWidget(self._time_label)

        self._rate_label = QLabel("计时单价：-- 元/分钟")
        self._rate_label.setFont(QFont("Microsoft YaHei", 18))
        self._rate_label.setStyleSheet("color: rgba(24, 38, 58, 0.78);")
        info_panel_layout.addWidget(self._rate_label)

        self._time_amount_label = QLabel("计时费用：¥ 0.00")
        self._time_amount_label.setFont(QFont("Microsoft YaHei", 18))
        self._time_amount_label.setStyleSheet("color: #2d6fbe;")
        info_panel_layout.addWidget(self._time_amount_label)

        self._export_count_label = QLabel("导出张数：0 张")
        self._export_count_label.setFont(QFont("Microsoft YaHei", 24, QFont.Bold))
        self._export_count_label.setStyleSheet("color: #18263a;")
        info_panel_layout.addWidget(self._export_count_label)

        self._export_rate_label = QLabel("单张导出单价：¥ 0.00 元/张")
        self._export_rate_label.setFont(QFont("Microsoft YaHei", 18))
        self._export_rate_label.setStyleSheet("color: rgba(24, 38, 58, 0.78);")
        info_panel_layout.addWidget(self._export_rate_label)

        self._export_amount_label = QLabel("导出费用：¥ 0.00")
        self._export_amount_label.setFont(QFont("Microsoft YaHei", 18))
        self._export_amount_label.setStyleSheet("color: #2d6fbe;")
        info_panel_layout.addWidget(self._export_amount_label)

        total_panel = QFrame()
        total_panel.setObjectName("paymentTotalPanel")
        total_panel_layout = QVBoxLayout(total_panel)
        total_panel_layout.setContentsMargins(20, 18, 20, 18)
        total_panel_layout.setSpacing(8)

        total_hint = QLabel("当前应付")
        total_hint.setFont(QFont("Microsoft YaHei", 14))
        total_hint.setStyleSheet("color: rgba(24, 38, 58, 0.56);")
        total_panel_layout.addWidget(total_hint)

        self._amount_label = QLabel("合计金额：¥ --")
        self._amount_label.setFont(QFont("Microsoft YaHei", 30, QFont.Bold))
        self._amount_label.setStyleSheet("color: #f39b2f;")
        total_panel_layout.addWidget(self._amount_label)
        info_panel_layout.addWidget(total_panel)

        hint_label = QLabel("请扫码支付，支付完成后由管理员确认。")
        hint_label.setFont(QFont("Microsoft YaHei", 15))
        hint_label.setStyleSheet("color: rgba(24, 38, 58, 0.68);")
        hint_label.setWordWrap(True)
        info_panel_layout.addWidget(hint_label)
        info_panel_layout.addStretch()
        info_panel.setMinimumHeight(620)

        body_layout.addWidget(info_panel, stretch=3)

        qr_panel = QFrame()
        qr_panel.setObjectName("paymentQrPanel")
        qr_layout = QVBoxLayout(qr_panel)
        qr_layout.setSpacing(16)
        qr_layout.setContentsMargins(26, 24, 26, 30)

        qr_title = QLabel("扫码完成支付")
        qr_title.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
        qr_title.setStyleSheet("color: #233247;")
        qr_title.setAlignment(Qt.AlignCenter)
        qr_layout.addWidget(qr_title)

        qr_subtitle = QLabel("支持微信 / 支付宝")
        qr_subtitle.setFont(QFont("Microsoft YaHei", 14))
        qr_subtitle.setStyleSheet("color: rgba(24, 38, 58, 0.6);")
        qr_subtitle.setAlignment(Qt.AlignCenter)
        qr_layout.addWidget(qr_subtitle)

        self._wechat_qr_label = QLabel()
        self._wechat_qr_label.setFixedSize(210, 210)
        self._wechat_qr_label.setStyleSheet(
            """
            background-color: rgba(255, 255, 255, 0.98);
            border: 1px solid rgba(255, 255, 255, 0.35);
            border-radius: 22px;
            padding: 12px;
            """
        )
        self._wechat_qr_label.setAlignment(Qt.AlignCenter)
        self._wechat_qr_label.setScaledContents(True)

        self._alipay_qr_label = QLabel()
        self._alipay_qr_label.setFixedSize(210, 210)
        self._alipay_qr_label.setStyleSheet(
            """
            background-color: rgba(255, 255, 255, 0.98);
            border: 1px solid rgba(255, 255, 255, 0.35);
            border-radius: 22px;
            padding: 12px;
            """
        )
        self._alipay_qr_label.setAlignment(Qt.AlignCenter)
        self._alipay_qr_label.setScaledContents(True)

        def _build_qr_slot(title: str, qr_label: QLabel) -> QFrame:
            slot = QFrame()
            slot.setStyleSheet(
                """
                background-color: rgba(255, 255, 255, 0.28);
                border: 1px solid rgba(255, 255, 255, 0.55);
                border-radius: 18px;
                """
            )
            slot_layout = QVBoxLayout(slot)
            slot_layout.setSpacing(10)
            slot_layout.setContentsMargins(12, 14, 12, 14)
            slot_title = QLabel(title)
            slot_title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
            slot_title.setAlignment(Qt.AlignCenter)
            slot_title.setStyleSheet("color: #233247;")
            slot_layout.addWidget(slot_title)
            slot_layout.addWidget(qr_label, alignment=Qt.AlignCenter)
            return slot

        qr_slots = QVBoxLayout()
        qr_slots.setSpacing(12)
        qr_slots.addWidget(_build_qr_slot("微信支付", self._wechat_qr_label))
        qr_slots.addWidget(_build_qr_slot("支付宝", self._alipay_qr_label))
        qr_layout.addLayout(qr_slots)

        qr_footer = QLabel("付款完成后请交由店员确认")
        qr_footer.setFont(QFont("Microsoft YaHei", 13))
        qr_footer.setStyleSheet("color: rgba(24, 38, 58, 0.58);")
        qr_footer.setAlignment(Qt.AlignCenter)
        qr_layout.addWidget(qr_footer)
        qr_layout.addStretch()
        qr_panel.setMinimumHeight(620)

        body_layout.addWidget(qr_panel, stretch=2)
        layout.addLayout(body_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._confirm_btn = QPushButton("已付款 · 确认收款")
        self._confirm_btn.setFont(QFont("Microsoft YaHei", 22, QFont.Bold))
        self._confirm_btn.setFixedSize(680, 92)
        self._confirm_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #f6b03d;
                color: #1b1f27;
                border: none;
                border-radius: 18px;
                padding: 14px 34px;
            }
            QPushButton:hover { background-color: #ffc45b; }
            QPushButton:pressed { background-color: #e4a23a; }
            """
        )
        btn_layout.addWidget(self._confirm_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        footer = QLabel("支付前将暂停导出，避免未付款先导出图片。")
        footer.setFont(QFont("Microsoft YaHei", 14))
        footer.setStyleSheet("color: rgba(24, 38, 58, 0.56);")
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

        # 刷新壁纸（配置可能已更新）
        self._load_wallpaper()

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
        wechat_path = getattr(self._config, "wechat_qr_code_path", "") or getattr(
            self._config, "qr_code_path", ""
        )
        alipay_path = getattr(self._config, "alipay_qr_code_path", "") or getattr(
            self._config, "qr_code_path", ""
        )

        loaded = False
        if wechat_path and os.path.exists(wechat_path):
            pixmap = QPixmap(wechat_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    184, 184,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self._wechat_qr_label.setPixmap(scaled)
                loaded = True

        if alipay_path and os.path.exists(alipay_path):
            pixmap = QPixmap(alipay_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    184, 184,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self._alipay_qr_label.setPixmap(scaled)
                loaded = True

        if loaded:
            if not (wechat_path and os.path.exists(wechat_path)):
                self._wechat_qr_label.setPixmap(self._alipay_qr_label.pixmap())
            if not (alipay_path and os.path.exists(alipay_path)):
                self._alipay_qr_label.setPixmap(self._wechat_qr_label.pixmap())
            return

        # 没有收款码时显示占位图
        self._show_placeholder_qr()

    def _load_wallpaper(self):
        """加载壁纸图片并缩放到屏幕大小"""
        wp_path = getattr(self._config, "wallpaper_path", "")
        if wp_path and os.path.exists(wp_path):
            pixmap = QPixmap(wp_path)
            if not pixmap.isNull():
                self._wallpaper_pixmap = pixmap
                return
        self._wallpaper_pixmap = None

    def paintEvent(self, event):
        """自定义绘制：先画壁纸，再叠加深色氛围层。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        if self._wallpaper_pixmap and not self._wallpaper_pixmap.isNull():
            scaled_wp = self._wallpaper_pixmap.scaled(
                self.size(),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation
            )
            x = (scaled_wp.width() - self.width()) // 2
            y = (scaled_wp.height() - self.height()) // 2
            cropped = scaled_wp.copy(x, y, self.width(), self.height())
            painter.setOpacity(self._wallpaper_opacity)
            painter.drawPixmap(0, 0, cropped)
            painter.setOpacity(1.0)

        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0.0, QColor(255, 255, 255, 30))
        gradient.setColorAt(0.45, QColor(214, 225, 244, 42))
        gradient.setColorAt(1.0, QColor(202, 214, 230, 62))
        painter.fillRect(self.rect(), gradient)

        painter.end()
        super().paintEvent(event)

    def _show_placeholder_qr(self):
        """显示收款码占位图"""
        def _placeholder(text: str) -> QPixmap:
            pixmap = QPixmap(184, 184)
            pixmap.fill(QColor(255, 255, 255))
            painter = QPainter(pixmap)
            painter.setFont(QFont("Microsoft YaHei", 14))
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(pixmap.rect(), Qt.AlignCenter, text)
            painter.end()
            return pixmap

        self._wechat_qr_label.setPixmap(_placeholder("请设置微信收款码"))
        self._alipay_qr_label.setPixmap(_placeholder("请设置支付宝收款码"))

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
        return self._wechat_qr_label

    @property
    def central_layout(self) -> QVBoxLayout:
        return self._content_layout
