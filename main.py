"""
主程序入口 - 应用初始化与信号连接
功能：
1. 初始化所有模块
2. 连接信号/槽
3. 单实例检测
4. 应用生命周期管理
"""

import sys
import os

# ====== 在任何其他导入之前设置 Qt 兼容性环境变量 ======
# 这一步必须在 PyQt5 导入之前完成，否则显卡驱动兼容性问题会导致启动崩溃
os.environ.setdefault("QT_OPENGL", "software")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")
os.environ.setdefault("QT_SCALE_FACTOR", "1")
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")
os.environ.setdefault("QT_FONT_DPI", "96")

import traceback
import time
from datetime import datetime


def _write_early_crash_log(message: str) -> None:
    """在 PyQt5 等第三方库尚未导入时记录崩溃诊断，专门用于远程排障。"""
    try:
        if getattr(sys, "frozen", False):
            log_dir = os.path.dirname(sys.executable)
        else:
            log_dir = os.path.dirname(os.path.abspath(__file__))
        crash_path = os.path.join(log_dir, "crash.log")
        startup_path = os.path.join(log_dir, "startup.log")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        line = f"{timestamp} [CRASH] {message}\n"
        # 写入 crash.log
        with open(crash_path, "a", encoding="utf-8") as f:
            f.write(line)
        # 同时写入 startup.log（每次启动会覆盖）
        with open(startup_path, "w", encoding="utf-8") as f:
            f.write(f"=== 启动日志 {timestamp} ===\n")
            f.write(line)
    except Exception:
        pass  # 连写文件都失败则静默退出


try:
    _write_early_crash_log(
        f"main.py importing: frozen={getattr(sys, 'frozen', False)}, "
        f"exe={sys.executable}, cwd={os.getcwd()}, "
        f"python={sys.version}, platform={sys.platform}, "
        f"QT_OPENGL={os.environ.get('QT_OPENGL', 'not set')}"
    )
    import logging
    import signal
    import platform

    from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal
    from PyQt5.QtGui import QColor, QFont, QLinearGradient, QPainter, QPixmap
    from PyQt5.QtWidgets import (
        QApplication,
        QDialog,
        QFrame,
        QLabel,
        QMessageBox,
        QPushButton,
        QVBoxLayout,
    )

    _write_early_crash_log("PyQt5 imports succeeded")
except Exception as _early_exc:
    _write_early_crash_log(f"IMPORT FAILED: {_early_exc!r}\n{traceback.format_exc()}")
    # 尝试用 ctypes 弹出一个 Windows 原生对话框，让用户能看到错误，
    # 而不是程序无声无息地消失（PyQt5 此时可能还没加载成功）
    try:
        import ctypes
        _err_msg = (
            f"程序启动失败，请联系技术支持。\n\n"
            f"错误信息：{_early_exc!r}\n\n"
            f"请将程序目录下的 crash.log 文件发给技术支持。"
        )
        ctypes.windll.user32.MessageBoxW(0, _err_msg, "计时计费程序 - 启动错误", 0x10)
    except Exception:
        pass
    raise

try:
    import win32api
    import win32con
    import win32gui
    import win32process
    import psutil

    HAS_FAST_EXPORT_HOTZONE = True
except Exception:
    win32api = None
    win32con = None
    win32gui = None
    win32process = None
    psutil = None
    HAS_FAST_EXPORT_HOTZONE = False

from config_manager import ConfigManager
from process_monitor import ProcessMonitor, recover_process_windows
from timer_manager import TimerManager
from payment_overlay import PaymentOverlay
from admin_panel import PasswordDialog, AdminPanel
from tray_icon import TrayIconManager
from PyQt5.QtCore import QThread, pyqtSignal as _Signal


class _ExportCountWorker(QThread):
    """在后台线程跑 OCR，避免阻塞主线程导致 UI 卡死。"""
    result_ready = _Signal(object, str)  # (count: int|None, source: str)

    def __init__(self, resolve_fn, parent=None):
        super().__init__(parent)
        self._resolve_fn = resolve_fn

    def run(self):
        try:
            count, source = self._resolve_fn(allow_expensive=True)
            self.result_ready.emit(count, source)
        except Exception:
            logger.exception("导出张数后台识别失败")
            self.result_ready.emit(None, "error")

# 配置日志 - 兼容源码运行和 PyInstaller 打包
if getattr(sys, "frozen", False):
    _log_dir = os.path.dirname(sys.executable)
else:
    _log_dir = os.path.dirname(os.path.abspath(__file__))
_bootstrap_log_path = os.path.join(_log_dir, "app.log")
_bootstrap_fallback_log_path = os.path.join(
    os.environ.get("TEMP", _log_dir), "SoftwareUsageMeter_bootstrap.log"
)


def _append_bootstrap_log(message: str) -> None:
    """在 QApplication 创建前也能写入启动痕迹，便于现场排障。"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    line = f"{timestamp} [BOOTSTRAP] main: {message}\n"
    for path in (_bootstrap_log_path, _bootstrap_fallback_log_path):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            continue


def _apply_safe_qt_runtime() -> None:
    """优先使用更稳的 Qt 渲染路径，降低远程交付环境的显卡兼容问题。"""
    # 环境变量已在模块顶部设置，这里只设置 Qt 属性
    try:
        QApplication.setAttribute(Qt.AA_UseSoftwareOpenGL, True)
    except Exception:
        pass
    try:
        QApplication.setAttribute(Qt.AA_DisableHighDpiScaling, True)
    except Exception:
        pass


_append_bootstrap_log(
    f"module imported: frozen={getattr(sys, 'frozen', False)}, exe={sys.executable}, cwd={os.getcwd()}"
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(_log_dir, "app.log"),
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("SoftwareUsageMeter")
SINGLE_INSTANCE_MUTEX = None
APP_MONITOR_START_DELAY_MS = 80


class StartupHintDialog(QDialog):
    """带壁纸的启动提示窗，用来给现场人员确认程序已经启动。"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._wallpaper_pixmap = self._load_wallpaper()
        self._confirmed = False
        self._init_ui()

    def _load_wallpaper(self) -> QPixmap | None:
        wallpaper_path = getattr(self._config, "wallpaper_path", "")
        if not wallpaper_path or not os.path.exists(wallpaper_path):
            return None
        pixmap = QPixmap(wallpaper_path)
        if pixmap.isNull():
            return None
        return pixmap

    def _init_ui(self):
        self.setWindowTitle("请先阅读操作流程")
        self.setFixedSize(1180, 760)
        self.setWindowFlags(
            Qt.Dialog
            | Qt.WindowStaysOnTopHint
            | Qt.CustomizeWindowHint
            | Qt.WindowTitleHint
        )
        self.setWindowModality(Qt.ApplicationModal)
        self.setAutoFillBackground(False)
        self.setObjectName("StartupHintDialog")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(54, 46, 54, 50)
        layout.setSpacing(0)

        card = QFrame(self)
        card.setObjectName("startupHintCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(70, 56, 70, 52)
        card_layout.setSpacing(30)
        layout.addWidget(card)

        eyebrow = QLabel("SOFTWARE USAGE METER")
        eyebrow.setFont(QFont("Microsoft YaHei", 20, QFont.Bold))
        eyebrow.setAlignment(Qt.AlignCenter)
        eyebrow.setStyleSheet("color: #4f7dc9; letter-spacing: 2px;")
        card_layout.addWidget(eyebrow)

        title = QLabel("请先阅读操作流程")
        title.setFont(QFont("Microsoft YaHei", 44, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #112235;")
        card_layout.addWidget(title)

        body = QLabel(
            "点击导出按钮后，系统将自动弹出收费框。"
            "客户完成付款，输入管理员密码解锁即可导出照片。"
        )
        body.setFont(QFont("Microsoft YaHei", 30, QFont.Bold))
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignCenter)
        body.setContentsMargins(20, 10, 20, 10)
        body.setStyleSheet(
            """
            color: rgba(17, 34, 53, 0.86);
            line-height: 1.6;
            background-color: rgba(255, 255, 255, 0.42);
            border: 1px solid rgba(255, 255, 255, 0.62);
            border-radius: 24px;
            padding: 34px 42px;
            """
        )
        card_layout.addWidget(body, 1)

        button = QPushButton("知道了")
        button.setCursor(Qt.PointingHandCursor)
        button.setFont(QFont("Microsoft YaHei", 30, QFont.Bold))
        button.setFixedHeight(108)
        button.clicked.connect(self._confirm_and_close)
        card_layout.addWidget(button)

        self.setStyleSheet(
            """
            QDialog#StartupHintDialog {
                background: transparent;
            }
            QFrame#startupHintCard {
                background-color: rgba(255, 255, 255, 0.68);
                border: 1px solid rgba(255, 255, 255, 0.76);
                border-radius: 34px;
            }
            QPushButton {
                color: #132033;
                background-color: #ffb23f;
                border: none;
                border-radius: 24px;
                padding: 16px 34px;
            }
            QPushButton:hover {
                background-color: #ffc05f;
            }
            QPushButton:pressed {
                background-color: #ee9d29;
            }
            """
        )

    def _confirm_and_close(self):
        self._confirmed = True
        self.accept()

    def closeEvent(self, event):
        if self._confirmed:
            event.accept()
        else:
            event.ignore()

    def keyPressEvent(self, event):
        # 现场交付时避免误按 ESC 绕过说明。
        if event.key() in (Qt.Key_Escape, Qt.Key_Enter, Qt.Key_Return):
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        if self._wallpaper_pixmap and not self._wallpaper_pixmap.isNull():
            scaled = self._wallpaper_pixmap.scaled(
                self.size(),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            x = (scaled.width() - self.width()) // 2
            y = (scaled.height() - self.height()) // 2
            painter.drawPixmap(0, 0, scaled.copy(x, y, self.width(), self.height()))
            painter.fillRect(self.rect(), QColor(245, 248, 252, 76))
        else:
            gradient = QLinearGradient(0, 0, self.width(), self.height())
            gradient.setColorAt(0.0, QColor("#f4f8ff"))
            gradient.setColorAt(0.55, QColor("#e9f0f8"))
            gradient.setColorAt(1.0, QColor("#fdf7ec"))
            painter.fillRect(self.rect(), gradient)

        super().paintEvent(event)


class DuplicateInstanceDialog(StartupHintDialog):
    """重复启动时显示的友好提示，逻辑上仍然只提示并退出。"""

    def _init_ui(self):
        self.setWindowTitle("提示")
        self.setFixedSize(700, 420)
        self.setWindowFlags(
            Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint
        )
        self.setWindowModality(Qt.ApplicationModal)
        self.setAutoFillBackground(False)
        self.setObjectName("DuplicateInstanceDialog")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 32, 36, 34)
        layout.setSpacing(0)

        card = QFrame(self)
        card.setObjectName("duplicateInstanceCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(46, 34, 46, 34)
        card_layout.setSpacing(18)
        layout.addWidget(card)

        badge = QLabel("!")
        badge.setObjectName("warningBadge")
        badge.setFixedSize(58, 58)
        badge.setAlignment(Qt.AlignCenter)
        badge.setFont(QFont("Microsoft YaHei", 28, QFont.Bold))
        card_layout.addWidget(badge, 0, Qt.AlignHCenter)

        title = QLabel("程序已在运行中")
        title.setFont(QFont("Microsoft YaHei", 26, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #112235;")
        card_layout.addWidget(title)

        body = QLabel(
            "请勿重复启动计时计费程序。\n\n"
            "如需查看状态、修改设置或退出程序，请在右下角系统托盘找到“计时计费”图标。"
        )
        body.setFont(QFont("Microsoft YaHei", 15))
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignCenter)
        body.setContentsMargins(8, 0, 8, 0)
        body.setStyleSheet("color: rgba(17, 34, 53, 0.76); line-height: 1.5;")
        card_layout.addWidget(body, 1)

        button = QPushButton("知道了")
        button.setCursor(Qt.PointingHandCursor)
        button.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        button.setFixedHeight(58)
        button.clicked.connect(self.accept)
        card_layout.addWidget(button)

        self.setStyleSheet(
            """
            QDialog#DuplicateInstanceDialog {
                background: transparent;
            }
            QFrame#duplicateInstanceCard {
                background-color: rgba(255, 255, 255, 0.78);
                border: 1px solid rgba(255, 255, 255, 0.82);
                border-radius: 26px;
            }
            QLabel#warningBadge {
                color: #132033;
                background-color: #ffb23f;
                border-radius: 29px;
            }
            QPushButton {
                color: #132033;
                background-color: #ffb23f;
                border: none;
                border-radius: 16px;
                padding: 8px 24px;
            }
            QPushButton:hover {
                background-color: #ffc05f;
            }
            QPushButton:pressed {
                background-color: #ee9d29;
            }
            """
        )


class ExportWaitOverlay(QDialog):
    """导出触发后的短暂等待遮罩，避免用户在收费框出现前继续乱点。"""

    def __init__(self, parent=None, seconds: int = 5):
        super().__init__(parent)
        self._remaining = max(int(seconds), 1)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("请等待")
        self.setWindowFlags(
            Qt.Dialog
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setWindowModality(Qt.ApplicationModal)
        self.setObjectName("ExportWaitOverlay")
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(200, 200, 200, 200)
        layout.setSpacing(0)

        card = QFrame(self)
        card.setObjectName("waitCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(180, 145, 180, 145)
        card_layout.setSpacing(70)
        layout.addWidget(card, alignment=Qt.AlignCenter)

        title = QLabel("请等待 5 秒钟")
        title.setObjectName("waitTitle")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Microsoft YaHei", 120, QFont.Bold))
        card_layout.addWidget(title)
        self._title_label = title

        body = QLabel("系统正在锁定导出流程，请不要点击像素蛋糕或重复操作。")
        body.setAlignment(Qt.AlignCenter)
        body.setWordWrap(True)
        body.setFont(QFont("Microsoft YaHei", 65))
        body.setStyleSheet("color: rgba(17, 34, 53, 0.74);")
        card_layout.addWidget(body)

        self.setStyleSheet(
            """
            QDialog#ExportWaitOverlay {
                background-color: rgba(15, 23, 42, 0.58);
            }
            QFrame#waitCard {
                min-width: 2200px;
                min-height: 800px;
                background-color: rgba(255, 255, 255, 0.86);
                border: 1px solid rgba(255, 255, 255, 0.78);
                border-radius: 85px;
            }
            QLabel#waitTitle {
                color: #112235;
            }
            """
        )

    def show_wait(self):
        self._remaining = 5
        self._update_title()
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self._timer.start()

    def _tick(self):
        self._remaining -= 1
        if self._remaining <= 0:
            self._timer.stop()
            self.accept()
            return
        self._update_title()

    def _update_title(self):
        self._title_label.setText(f"请等待 {self._remaining} 秒钟")

    def keyPressEvent(self, event):
        event.accept()

    def mousePressEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

    def closeEvent(self, event):
        if self._remaining <= 0:
            event.accept()
        else:
            event.ignore()


class Application:
    """主应用程序类"""

    def __init__(self):
        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)  # 关闭窗口不退出应用

        # 初始化配置
        self._config = ConfigManager()

        # 初始化模块
        self._timer = TimerManager()
        self._monitor = ProcessMonitor(self._config)
        self._overlay = PaymentOverlay(self._config)
        self._tray = TrayIconManager(self._config)

        # 状态
        self._is_exporting = False
        self._payment_confirmed = False
        self._current_export_count = 0
        self._cleanup_done = False
        self._quit_requested = False
        self._startup_hint = None
        self._export_wait_overlay = None
        self._pending_wait_payment_args = None
        self._refine_worker = None
        self._original_excepthook = sys.excepthook
        self._original_sigint_handler = signal.getsignal(signal.SIGINT)
        self._signal_pump_timer = QTimer(self._app)
        self._signal_pump_timer.setInterval(200)
        self._signal_pump_timer.timeout.connect(lambda: None)
        self._fast_export_click_timer = QTimer(self._app)
        self._fast_export_click_timer.setInterval(20)
        self._fast_export_click_timer.timeout.connect(
            self._poll_fast_export_click_hotzone
        )
        self._fast_export_left_down = False
        self._fast_export_pending_click = None
        self._last_fast_export_wait_at = 0.0

        # 连接信号
        self._connect_signals()

        # 初始化状态显示
        self._tray.update_process_name(self._config.process_name)

        self._log_startup_context()
        logger.info("应用初始化完成")

    def _start_fast_export_click_timer(self):
        """Start the no-screenshot export-click guard used to show wait overlay fast."""
        if not HAS_FAST_EXPORT_HOTZONE:
            logger.warning("快速导出热区监听不可用：缺少 win32api/win32gui")
            return
        if not self._fast_export_click_timer.isActive():
            self._fast_export_click_timer.start()
            logger.info("快速导出热区监听已启动: interval_ms=%s", self._fast_export_click_timer.interval())

    def _poll_fast_export_click_hotzone(self):
        """Show the wait overlay right after a real PixCake export-button click."""
        if not HAS_FAST_EXPORT_HOTZONE or self._quit_requested:
            return

        try:
            left_down = bool(win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000)
            cursor_x, cursor_y = win32api.GetCursorPos()
        except Exception:
            logger.debug("快速导出热区监听读取鼠标状态失败", exc_info=True)
            return

        was_left_down = self._fast_export_left_down
        self._fast_export_left_down = left_down

        now = time.monotonic()
        if (
            self._fast_export_pending_click is not None
            and now - self._fast_export_pending_click["at"] > 1.2
        ):
            self._fast_export_pending_click = None

        if not left_down and was_left_down:
            pending_click = self._fast_export_pending_click
            self._fast_export_pending_click = None
            if pending_click is None:
                return
            if now - self._last_fast_export_wait_at < 6.0:
                return
            if self._payment_confirmed or self._overlay.isVisible():
                return
            self._last_fast_export_wait_at = now
            logger.info(
                "快速导出热区点击完成，立即显示等待遮罩: down_cursor=%s, up_cursor=(%s,%s), hotzone=%s",
                pending_click["cursor"],
                cursor_x,
                cursor_y,
                pending_click["hotzone"],
            )
            # 设置导出状态，防止监控线程重复触发
            self._is_exporting = True
            self._payment_confirmed = False
            self._monitor.set_export_state_hold(True)
            # 获取计时时长和费率
            minutes = self._timer.get_elapsed_minutes()
            rate = self._config.rate
            self._show_export_wait_overlay(minutes, rate)
            return

        is_new_press = left_down and not was_left_down
        if not is_new_press:
            return

        if (
            self._is_exporting
            or self._payment_confirmed
            or self._overlay.isVisible()
            or (
                self._export_wait_overlay is not None
                and self._export_wait_overlay.isVisible()
            )
        ):
            return

        if now - self._last_fast_export_wait_at < 6.0:
            return

        hotzone = self._get_fast_export_hotzone(cursor_x, cursor_y)
        if hotzone is None:
            return

        left, top, right, bottom = hotzone
        if not (left <= cursor_x <= right and top <= cursor_y <= bottom):
            return

        has_yellow_hint = self._has_export_yellow_near_cursor(cursor_x, cursor_y)
        if not has_yellow_hint:
            logger.info(
                "快速导出热区点击被忽略：未采样到黄色按钮像素 cursor=(%s,%s), hotzone=%s",
                cursor_x,
                cursor_y,
                hotzone,
            )
            return

        self._fast_export_pending_click = {
            "at": now,
            "cursor": (cursor_x, cursor_y),
            "hotzone": hotzone,
        }
        logger.info(
            "快速导出热区按下命中，等待鼠标松开后显示遮罩: cursor=(%s,%s), hotzone=%s",
            cursor_x,
            cursor_y,
            hotzone,
        )

    def _get_fast_export_hotzone(self, cursor_x: int, cursor_y: int):
        """Return a broad top-right PixCake export-button area without taking screenshots."""
        if not HAS_FAST_EXPORT_HOTZONE:
            return None

        hwnd = self._get_fast_export_target_hwnd(cursor_x, cursor_y)
        if not hwnd:
            return None

        try:
            if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
                return None
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        except Exception:
            logger.debug("快速导出热区获取目标窗口失败: hwnd=%s", hwnd, exc_info=True)
            return None

        width = right - left
        height = bottom - top
        if width < 300 or height < 160:
            return None

        # 放宽热区范围，覆盖更广的右上角区域
        hot_width = min(max(int(width * 0.35), 420), 800)
        hot_height = min(max(int(height * 0.18), 100), 200)
        return (
            max(left, right - hot_width),
            top,
            right,
            min(bottom, top + hot_height),
        )

    def _get_fast_export_target_hwnd(self, cursor_x: int, cursor_y: int):
        """Prefer monitor hwnd, but fall back to the PixCake window under the cursor."""
        monitor_hwnd = self._monitor.main_hwnd
        if monitor_hwnd:
            try:
                if win32gui.IsWindow(monitor_hwnd) and win32gui.IsWindowVisible(monitor_hwnd):
                    left, top, right, bottom = win32gui.GetWindowRect(monitor_hwnd)
                    if left <= cursor_x <= right and top <= cursor_y <= bottom:
                        return monitor_hwnd
            except Exception:
                logger.debug("快速导出热区校验监控窗口失败: hwnd=%s", monitor_hwnd, exc_info=True)

        try:
            hwnd = win32gui.WindowFromPoint((cursor_x, cursor_y))
            if not hwnd:
                return None
            root_hwnd = win32gui.GetAncestor(hwnd, win32con.GA_ROOT)
            hwnd = root_hwnd or hwnd
            if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
                return None
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process_name = psutil.Process(pid).name()
        except Exception:
            logger.debug("快速导出热区从鼠标位置解析目标窗口失败", exc_info=True)
            return None

        expected_name = str(self._config.process_name or "").lower()
        if process_name.lower() != expected_name:
            return None
        logger.info(
            "快速导出热区使用鼠标所在窗口作为目标: hwnd=%s, pid=%s, process=%s",
            hwnd,
            pid,
            process_name,
        )
        return hwnd

    def _has_export_yellow_near_cursor(self, cursor_x: int, cursor_y: int) -> bool:
        """Cheaply sample screen pixels around the click to reduce hot-zone false positives."""
        if not HAS_FAST_EXPORT_HOTZONE:
            return False

        offsets = (
            (0, 0),
            (-10, 0),
            (10, 0),
            (0, -10),
            (0, 10),
            (-18, 0),
            (18, 0),
            (0, -18),
            (0, 18),
            (-16, -8),
            (16, -8),
            (-16, 8),
            (16, 8),
        )
        hdc = None
        try:
            hdc = win32gui.GetDC(0)
            for dx, dy in offsets:
                color = win32gui.GetPixel(hdc, cursor_x + dx, cursor_y + dy)
                if color >= 0 and self._is_export_button_yellow(color):
                    return True
        except Exception:
            logger.debug("快速导出热区采样像素失败", exc_info=True)
            return True
        finally:
            if hdc:
                try:
                    win32gui.ReleaseDC(0, hdc)
                except Exception:
                    pass
        return False

    @staticmethod
    def _is_export_button_yellow(color: int) -> bool:
        """Win32 COLORREF is 0x00bbggrr."""
        red = color & 0xFF
        green = (color >> 8) & 0xFF
        blue = (color >> 16) & 0xFF
        # 放宽颜色范围：黄橙色系（红高绿中蓝低）
        return red >= 140 and green >= 100 and blue <= 120 and red >= green - 30

    def _start_monitor_if_needed(self):
        """稍微延后启动监控线程，减少应用首屏卡顿。"""
        if self._monitor.isRunning():
            return
        self._monitor.start()
        logger.info("监控线程已启动")

    def _close_startup_hint(self):
        """自动关闭启动提示，避免影响门店现场操作。"""
        if self._startup_hint is not None and self._startup_hint.isVisible():
            self._startup_hint._confirmed = True
            self._startup_hint.close()

    def _show_startup_hint(self):
        """启动后给现场人员一个明确、友好的运行提示。"""
        if self._quit_requested:
            return
        if self._startup_hint is not None and self._startup_hint.isVisible():
            return

        hint = StartupHintDialog(self._config)
        self._startup_hint = hint
        logger.info("启动操作说明弹窗已显示，等待现场人员点击知道了")
        result = hint.exec_()
        self._startup_hint = None
        logger.info("启动操作说明弹窗已确认: result=%s", result)

    def _log_startup_context(self):
        """记录运行环境和关键配置，便于现场排障。"""
        logger.info(
            "运行环境: frozen=%s, python=%s, executable=%s, cwd=%s, platform=%s, qt_opengl=%s, "
            "ui_shadows_enabled=%s, app_log=%s, bootstrap_log=%s",
            getattr(sys, "frozen", False),
            sys.executable,
            os.path.abspath(sys.argv[0]),
            os.getcwd(),
            platform.platform(),
            os.environ.get("QT_OPENGL", ""),
            not getattr(sys, "frozen", False),
            _bootstrap_log_path,
            _bootstrap_fallback_log_path,
        )
        logger.info(
            "配置摘要: process_name=%s, keywords=%s, rate=%s, export_rate=%s, monitor_interval_ms=%s, "
            "wallpaper_exists=%s, wechat_qr_exists=%s, alipay_qr_exists=%s",
            self._config.process_name,
            self._config.export_window_keywords,
            self._config.rate,
            self._config.export_rate,
            self._config.monitor_interval_ms,
            bool(
                self._config.wallpaper_path
                and os.path.exists(self._config.wallpaper_path)
            ),
            bool(
                self._config.wechat_qr_code_path
                and os.path.exists(self._config.wechat_qr_code_path)
            ),
            bool(
                self._config.alipay_qr_code_path
                and os.path.exists(self._config.alipay_qr_code_path)
            ),
        )

    def _connect_signals(self):
        """连接所有信号/槽"""
        self._app.aboutToQuit.connect(self._cleanup_before_exit)
        sys.excepthook = self._handle_uncaught_exception
        signal.signal(signal.SIGINT, self._handle_sigint)

        # 进程监控信号
        self._monitor.process_started.connect(self._on_process_started)
        self._monitor.process_stopped.connect(self._on_process_stopped)
        self._monitor.export_button_pre_clicked.connect(self._on_export_button_pre_clicked)
        self._monitor.export_detected.connect(self._on_export_detected)
        self._monitor.export_cancelled.connect(self._on_export_cancelled)

        # 计时器信号
        self._timer.tick.connect(self._on_timer_tick)
        self._timer.minute_tick.connect(self._on_minute_tick)

        # 收费弹窗
        self._overlay.payment_completed.connect(self._on_payment_confirmed)

        # 托盘菜单
        self._tray.show_action.triggered.connect(self._on_show_status)
        self._tray.admin_action.triggered.connect(self._on_admin_panel)
        self._tray.manual_trigger_action.triggered.connect(self._on_manual_trigger)
        self._tray.quit_action.triggered.connect(self._on_quit)

    def _recover_locked_target_windows(self, reason: str):
        """兜底恢复像素蛋糕窗口交互状态，避免上次异常退出后残留禁用状态。"""
        restored = recover_process_windows(
            self._config.process_name,
            hwnds=getattr(self._overlay, "_locked_hwnds", []),
        )
        if restored:
            logger.info("%s已恢复目标窗口交互状态: %s", reason, restored)

    def _build_runtime_snapshot(self) -> dict:
        """汇总关键运行态，便于异常日志和现场排查。"""
        return {
            "is_exporting": self._is_exporting,
            "payment_confirmed": self._payment_confirmed,
            "current_export_count": self._current_export_count,
            "overlay_visible": self._overlay.isVisible(),
            "timer_running": self._timer.is_running,
            "elapsed_seconds": self._timer.get_elapsed_seconds(),
            "monitor": self._monitor.get_runtime_snapshot(),
        }

    def _log_runtime_snapshot(self, reason: str, level: int = logging.INFO):
        logger.log(level, "%s运行快照: %s", reason, self._build_runtime_snapshot())

    def _handle_uncaught_exception(self, exc_type, exc_value, exc_tb):
        """记录未捕获异常，并在退出前尽量恢复现场。"""
        if issubclass(exc_type, KeyboardInterrupt):
            logger.info("收到 KeyboardInterrupt，准备退出应用")
            self._handle_sigint(signal.SIGINT, None)
            return

        logger.critical("程序发生未捕获异常: %s", exc_value)
        logger.critical(
            "异常堆栈:\n%s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        )
        self._log_runtime_snapshot("异常前", level=logging.CRITICAL)
        try:
            self._cleanup_before_exit()
        except Exception as cleanup_error:
            logger.critical("异常清理失败: %s", cleanup_error)

        if self._original_excepthook:
            self._original_excepthook(exc_type, exc_value, exc_tb)

    def _cleanup_before_exit(self):
        """退出前统一清理锁定状态，保证像素蛋糕窗口一定恢复可操作。"""
        if self._cleanup_done:
            return

        self._cleanup_done = True
        self._signal_pump_timer.stop()
        self._fast_export_click_timer.stop()
        self._fast_export_pending_click = None
        sys.excepthook = self._original_excepthook
        signal.signal(signal.SIGINT, self._original_sigint_handler)
        self._log_runtime_snapshot("退出前")
        self._monitor.set_export_state_hold(False)
        self._monitor.set_post_payment_pending(False)
        self._monitor.resume_target_processes()
        if self._export_wait_overlay is not None:
            self._export_wait_overlay._remaining = 0
            self._export_wait_overlay.hide()
            self._export_wait_overlay.deleteLater()
            self._export_wait_overlay = None
        self._pending_wait_payment_args = None
        self._overlay.close_payment()
        self._current_export_count = 0
        self._recover_locked_target_windows("退出前兜底解锁，")

    def _handle_sigint(self, signum, frame):
        """处理 Ctrl+C，确保 Qt 事件循环可以优雅退出。"""
        if self._quit_requested:
            return

        self._quit_requested = True
        logger.info("收到 Ctrl+C，正在退出应用...")
        QTimer.singleShot(0, self._on_quit)

    def _on_process_started(self):
        """目标程序启动"""
        self._monitor.set_post_payment_pending(False)
        if self._is_exporting:
            logger.info("目标程序已启动，但当前仍处于导出结算流程，暂不开始新计时")
            self._tray.set_running_state(False)
            return

        logger.info("目标程序已启动，开始计时")
        self._timer.start()
        self._tray.set_running_state(True)
        self._tray.show_notification(
            "计时开始", f"检测到 {self._config.process_name}，已开始计时"
        )

    def _on_process_stopped(self):
        """目标程序退出"""
        logger.info("目标程序已退出，结束本轮计时并清零")
        self._monitor.set_export_state_hold(False)
        self._monitor.set_post_payment_pending(False)
        self._monitor.resume_target_processes()
        if self._overlay.isVisible():
            self._overlay.close_payment()

        # 保底：程序退出时若有未结算计时，强制弹出收费框
        elapsed_minutes = self._timer.get_elapsed_minutes()
        if elapsed_minutes > 0 and not self._payment_confirmed and not self._is_exporting:
            logger.info(
                "目标程序退出时检测到未结算计时 %s 分钟，触发保底收费", elapsed_minutes
            )
            self._trigger_retroactive_payment(elapsed_minutes)
            return

        self._timer.reset()
        self._tray.reset()
        self._is_exporting = False
        self._payment_confirmed = False
        self._current_export_count = 0
        self._tray.show_notification(
            "本轮已结束", f"{self._config.process_name} 已退出，计时已清零"
        )

    def _trigger_retroactive_payment(self, minutes: int):
        """程序退出后的保底收费，防止漏单。"""
        self._is_exporting = True
        self._payment_confirmed = False
        rate = self._config.rate
        cached_count = self._monitor.get_recent_export_count()
        export_count = cached_count if cached_count is not None else 0
        self._current_export_count = export_count
        self._overlay.show_payment(
            minutes,
            rate,
            export_count=export_count,
            export_rate=self._config.export_rate,
        )
        self._tray.set_running_state(False)
        self._tray.show_notification(
            "检测到未结算记录", "程序已退出，请完成本次付款后再继续"
        )

    def _resolve_export_count_for_payment(
        self, allow_expensive: bool = False
    ) -> tuple[int | None, str]:
        """尽量用最近缓存的导出信息，避免为了显示收费框再次做重截图。"""
        cached_export_count = self._monitor.get_recent_export_count()
        if cached_export_count is not None:
            logger.info("本次收费优先使用预缓存导出张数: %s", cached_export_count)
            return cached_export_count, "cache"

        last_export_image = self._monitor.get_last_export_capture_image()
        last_export_dialog_mode = self._monitor.get_last_export_capture_dialog_mode()
        current_dialog_mode = self._monitor.export_hwnd is not None

        detected_export_count = None
        if last_export_image is not None:
            detected_export_count = (
                self._monitor.detect_export_summary_count_from_image(
                    last_export_image, dialog_mode=last_export_dialog_mode
                )
            )
            if detected_export_count is None:
                detected_export_count = (
                    self._monitor.detect_export_image_count_from_image(
                        last_export_image, dialog_mode=last_export_dialog_mode
                    )
                )
            if detected_export_count is not None:
                return detected_export_count, "last_capture"

        if not allow_expensive:
            return None, "deferred"

        pre_suspend_image = self._monitor.capture_main_window_image()
        if pre_suspend_image is not None:
            detected_export_count = (
                self._monitor.detect_export_summary_count_from_image(
                    pre_suspend_image, dialog_mode=current_dialog_mode
                )
            )
            if detected_export_count is None:
                detected_export_count = (
                    self._monitor.detect_export_image_count_from_image(
                        pre_suspend_image, dialog_mode=current_dialog_mode
                    )
                )
            if detected_export_count is not None:
                return detected_export_count, "live_capture"

        detected_export_count = self._monitor.detect_export_summary_count()
        if detected_export_count is not None:
            return detected_export_count, "summary_scan"

        detected_export_count = self._monitor.detect_export_image_count()
        if detected_export_count is not None:
            return detected_export_count, "image_scan"

        return None, "default"

    def _resolve_export_count_for_overlay(self) -> tuple[int, str]:
        """收费框首屏使用的快速导出张数来源，优先保证弹窗能立即出现。"""
        detected_export_count, export_count_source = (
            self._resolve_export_count_for_payment(allow_expensive=False)
        )
        if detected_export_count is None:
            return self._config.default_export_count, "default"
        return detected_export_count, export_count_source

    def _apply_export_count_to_overlay(
        self, export_count: int, export_count_source: str, minutes: int, rate: float
    ):
        """把当前导出张数同步到收费框并补充日志。"""
        self._current_export_count = export_count
        if export_count_source == "default":
            logger.warning(
                "未能快速识别导出张数，先使用默认值: %s 张，单张导出单价: %.2f，导出费用: %.2f",
                self._current_export_count,
                self._config.export_rate,
                self._current_export_count * self._config.export_rate,
            )
        else:
            logger.info(
                "本次导出识别到导出张数: %s，来源: %s，单张导出单价: %.2f，导出费用: %.2f",
                self._current_export_count,
                export_count_source,
                self._config.export_rate,
                self._current_export_count * self._config.export_rate,
            )

        self._overlay.update_display(
            minutes,
            rate,
            export_count=self._current_export_count,
            export_rate=self._config.export_rate,
        )

    def _refine_export_count_after_overlay(self, minutes: int, rate: float):
        """收费框显示后启动后台 OCR 线程，避免阻塞主线程。"""
        if (
            not self._is_exporting
            or self._payment_confirmed
            or not self._overlay.isVisible()
        ):
            self._overlay.set_counting_status(False)
            return

        if self._refine_worker is not None and self._refine_worker.isRunning():
            return

        worker = _ExportCountWorker(self._resolve_export_count_for_payment)
        worker.result_ready.connect(
            lambda count, source: self._on_refine_result(count, source, minutes, rate)
        )
        self._refine_worker = worker
        worker.start()

    def _on_refine_result(self, count, source: str, minutes: int, rate: float):
        """OCR 线程完成后在主线程更新收费框。"""
        if not self._is_exporting or self._payment_confirmed or not self._overlay.isVisible():
            self._overlay.set_counting_status(False)
            return

        # 识别失败或识别到0张时，启用手动输入模式
        if count is None or count <= 0:
            logger.warning(
                "收费框已显示，但识别失败或张数为0，启用手动输入模式: count=%s, source=%s",
                count, source
            )
            self._overlay.set_counting_status(False)
            self._overlay.set_manual_export_count_required(True)
            return

        if (
            count == self._current_export_count
            and source in {"cache", "last_capture"}
        ):
            logger.info(
                "收费框显示后无需更新导出张数: %s，来源: %s", count, source
            )
            self._overlay.set_counting_status(False)
            self._overlay.update_display(
                minutes, rate,
                export_count=self._current_export_count,
                export_rate=self._config.export_rate,
            )
            return

        logger.info(
            "收费框已显示，延后更新导出张数: old=%s, new=%s, source=%s",
            self._current_export_count, count, source,
        )
        self._overlay.set_counting_status(False)
        self._apply_export_count_to_overlay(count, source, minutes, rate)

    def _show_payment_overlay_after_wait(self, minutes: int, rate: float):
        """5 秒等待结束后继续原来的收费弹窗流程。"""
        if not self._is_exporting or self._payment_confirmed:
            return

        # 先尝试快速获取导出张数
        detected_export_count, export_count_source = (
            self._resolve_export_count_for_overlay()
        )
        self._monitor.suspend_target_processes()
        self._overlay.show_payment(
            minutes,
            rate,
            hwnd=self._monitor.main_hwnd,
            lock_targets=self._monitor.lock_target_hwnds,
            export_count=detected_export_count,
            export_rate=self._config.export_rate,
        )
        self._apply_export_count_to_overlay(
            detected_export_count, export_count_source, minutes, rate
        )
        logger.info(
            "等待遮罩结束，收费弹窗已显示: minutes=%s, export_count=%s, source=%s",
            minutes, detected_export_count, export_count_source
        )

        # 如果首屏是默认值或0，启动后台OCR线程精修
        if export_count_source == "default" or detected_export_count <= 0:
            QTimer.singleShot(
                120,
                lambda m=minutes, r=rate: self._refine_export_count_after_overlay(m, r),
            )

    def _on_export_wait_finished(self, _result=None):
        """等待遮罩结束：有待显示的收费框就继续显示，否则只关闭遮罩。"""
        if self._export_wait_overlay is not None:
            self._export_wait_overlay.hide()
            self._export_wait_overlay.deleteLater()
            self._export_wait_overlay = None

        pending_args = self._pending_wait_payment_args
        self._pending_wait_payment_args = None
        if pending_args is None:
            logger.info("导出等待遮罩结束，暂无收费弹窗待显示")
            return

        minutes, rate = pending_args
        self._show_payment_overlay_after_wait(minutes, rate)

    def _show_export_wait_overlay(self, minutes: int | None = None, rate: float | None = None):
        """显示 5 秒等待遮罩，拦截鼠标点击后再弹收费框。"""
        if minutes is not None and rate is not None:
            self._pending_wait_payment_args = (minutes, rate)

        if self._export_wait_overlay is not None:
            if self._export_wait_overlay.isVisible():
                self._export_wait_overlay.raise_()
                self._export_wait_overlay.activateWindow()
                logger.info("导出等待遮罩已存在，不重置倒计时")
                return
            self._export_wait_overlay.deleteLater()

        wait_overlay = ExportWaitOverlay(seconds=5)
        wait_overlay.finished.connect(self._on_export_wait_finished)
        self._export_wait_overlay = wait_overlay
        wait_overlay.show_wait()
        logger.info("导出触发后已显示 5 秒等待遮罩")

    def _on_export_button_pre_clicked(self):
        """用户点击导出按钮的瞬间先弹等待遮罩，给后续检测争取时间。"""
        if self._quit_requested or self._payment_confirmed:
            return
        if self._overlay.isVisible():
            return
        self._show_export_wait_overlay()

    def _on_export_detected(self):
        """检测到导出行为"""
        if self._is_exporting:
            return  # 防止重复触发

        try:
            self._is_exporting = True
            self._payment_confirmed = False
            self._monitor.set_post_payment_pending(False)
            logger.info("检测到导出行为，停止计时并准备立即显示收费弹窗")
            self._log_runtime_snapshot("导出触发前")

            # 先暂停计时，并立刻进入导出保持状态。
            self._timer.pause()
            self._tray.set_running_state(False)
            self._monitor.set_export_state_hold(True)

            # 目标进程此时已在监控线程里预挂起；这里再补一次幂等调用，兼容旧状态。
            self._monitor.suspend_target_processes()

            minutes = self._timer.get_elapsed_minutes()
            rate = self._config.rate

            # 先用全屏等待遮罩吃掉鼠标点击，5 秒后再继续原来的收费弹窗流程。
            self._show_export_wait_overlay(minutes, rate)
        except Exception:
            logger.exception("处理导出触发失败，正在恢复现场")
            self._monitor.set_export_state_hold(False)
            self._monitor.set_post_payment_pending(False)
            logger.info("导出接管异常，准备恢复交互")
            self._monitor.restore_target_interaction()
            if self._export_wait_overlay is not None:
                self._export_wait_overlay._remaining = 0
                self._export_wait_overlay.hide()
                self._export_wait_overlay.deleteLater()
                self._export_wait_overlay = None
            self._pending_wait_payment_args = None
            if self._overlay.isVisible():
                self._overlay.close_payment()
            self._is_exporting = False
            self._payment_confirmed = False
            self._current_export_count = 0
            if self._monitor.is_process_running:
                self._timer.start()
                self._tray.set_running_state(True)
                self._tray.show_notification("恢复计时", "导出接管失败，已恢复当前计时")

    def _on_export_cancelled(self):
        """导出窗口关闭（取消导出或导出完成）"""
        if not self._is_exporting:
            return

        if self._payment_confirmed:
            logger.info("导出已结束，进入下一次计时周期")
            self._monitor.set_export_state_hold(False)
            self._finish_export_cycle()
            return

        logger.info("导出在付款前被取消，关闭收费弹窗并恢复计时")
        self._monitor.set_export_state_hold(False)
        self._monitor.set_post_payment_pending(False)
        restore_result = self._monitor.restore_target_interaction()
        logger.info("导出取消后已执行交互恢复: %s", restore_result)
        if self._export_wait_overlay is not None:
            self._export_wait_overlay._remaining = 0
            self._export_wait_overlay.hide()
            self._export_wait_overlay.deleteLater()
            self._export_wait_overlay = None
        self._pending_wait_payment_args = None
        if self._overlay.isVisible():
            self._overlay.close_payment()
        self._is_exporting = False
        self._payment_confirmed = False
        self._current_export_count = 0
        if self._monitor.is_process_running:
            self._timer.start()
            self._tray.set_running_state(True)
            self._tray.show_notification("恢复计时", "导出已取消，继续当前计时")

    def _on_timer_tick(self, seconds: int):
        """每秒更新计时显示"""
        time_str = self._timer.format_elapsed()
        minutes = self._timer.get_elapsed_minutes()
        rate = self._config.rate
        self._tray.update_timing(time_str, minutes, rate)

    def _on_minute_tick(self, minutes: int):
        """每分钟更新一次费用"""
        rate = self._config.rate
        self._tray.update_timing(self._timer.format_elapsed(), minutes, rate)

    def _on_payment_confirmed(self):
        """管理员确认收款"""
        admin_confirmed = False
        pwd_dialog = PasswordDialog(self._config, self._overlay)
        self._overlay.pause_keep_on_top()
        try:
            if (
                pwd_dialog.exec_() != PasswordDialog.Accepted
                or not pwd_dialog.authenticated
            ):
                logger.info("确认收款已取消或密码验证失败，收费框保持显示")
                self._overlay.reset_payment_confirmation()
                return
            admin_confirmed = True
        finally:
            if self._overlay.isVisible() and not admin_confirmed:
                self._overlay.resume_keep_on_top()

        logger.info("确认收款，关闭弹窗并等待本次导出结束")
        self._log_runtime_snapshot("确认收款前")
        self._overlay.close_payment()
        self._monitor.set_post_payment_pending(True)
        self._monitor.set_export_state_hold(False)
        try:
            restore_result = self._monitor.restore_target_interaction()
        except Exception:
            logger.exception("确认收款后执行交互恢复失败")
            restore_result = {"error": True}
        logger.info("确认收款后已执行交互恢复: %s", restore_result)
        QTimer.singleShot(
            180,
            lambda: logger.info(
                "确认收款后延迟恢复结果: %s",
                self._monitor.restore_target_interaction(),
            ),
        )
        self._timer.reset()
        self._tray.reset()
        self._is_exporting = True
        self._payment_confirmed = True

        # 手动触发收费等场景下可能没有导出窗口，直接进入下一轮
        if not self._monitor.is_export_dialog_visible:
            self._finish_export_cycle()
            return

        self._tray.show_notification(
            "已确认收款", "已解锁导出，导出完成后将开始下一轮计时"
        )

    def _on_show_status(self):
        """显示状态窗口"""
        logger.info("菜单操作：显示状态页")
        self._tray.status_widget.show()
        self._tray.status_widget.raise_()
        self._tray.status_widget.activateWindow()

    def _on_admin_panel(self):
        """打开管理设置面板"""
        # 先验证密码
        pwd_dialog = PasswordDialog(self._config)
        if pwd_dialog.exec_() != PasswordDialog.Accepted:
            return
        if not pwd_dialog.authenticated:
            return

        # 显示设置面板
        admin_panel = AdminPanel(self._config)
        admin_panel.exec_()

        # 设置可能已更新，刷新状态
        self._tray.update_process_name(self._config.process_name)
        self._tray.status_widget.update_process(self._config.process_name)

        # 如果监控正在运行，需要重启以应用新的进程名/关键词
        if self._monitor.isRunning():
            self._monitor.stop()
            self._monitor = ProcessMonitor(self._config)
            self._monitor.process_started.connect(self._on_process_started)
            self._monitor.process_stopped.connect(self._on_process_stopped)
            self._monitor.export_button_pre_clicked.connect(self._on_export_button_pre_clicked)
            self._monitor.export_detected.connect(self._on_export_detected)
            self._monitor.export_cancelled.connect(self._on_export_cancelled)
            self._monitor.start()
            logger.info("监控已重启以应用新设置")

    def _on_manual_trigger(self):
        """手动触发收费"""
        if not self._timer.is_running and self._timer.get_elapsed_seconds() == 0:
            QMessageBox.information(None, "提示", "当前没有使用记录，无法触发收费。")
            return

        # 需要管理员密码确认
        pwd_dialog = PasswordDialog(self._config)
        if pwd_dialog.exec_() != PasswordDialog.Accepted:
            return
        if not pwd_dialog.authenticated:
            return

        # 停止计时并显示收费
        self._timer.pause()
        self._tray.set_running_state(False)
        minutes = self._timer.get_elapsed_minutes()
        rate = self._config.rate
        self._is_exporting = True
        self._payment_confirmed = False
        self._monitor.set_export_state_hold(True)
        self._monitor.set_post_payment_pending(False)
        detected_export_count, export_count_source = (
            self._resolve_export_count_for_overlay()
        )
        self._monitor.suspend_target_processes()
        self._overlay.show_payment(
            minutes,
            rate,
            hwnd=self._monitor.main_hwnd,
            lock_targets=self._monitor.lock_target_hwnds,
            export_count=detected_export_count,
            export_rate=self._config.export_rate,
        )
        self._apply_export_count_to_overlay(
            detected_export_count, export_count_source, minutes, rate
        )

        if export_count_source == "default":
            QTimer.singleShot(
                120,
                lambda m=minutes, r=rate: self._refine_export_count_after_overlay(m, r),
            )

    def _finish_export_cycle(self):
        """当前收费流程结束，准备进入下一轮计时。"""
        self._is_exporting = False
        self._payment_confirmed = False
        self._current_export_count = 0
        self._monitor.set_post_payment_pending(False)
        if self._monitor.is_process_running:
            self._timer.start()
            self._tray.set_running_state(True)
            self._tray.show_notification(
                "开始新一轮计时", "本次导出已结束，已进入下一轮计时"
            )

    def _on_quit(self):
        """退出应用"""
        if self._cleanup_done:
            QApplication.quit()
            return
        self._cleanup_before_exit()
        self._monitor.stop()
        self._timer.pause()
        QApplication.quit()
        logger.info("应用已退出")

    def run(self) -> int:
        """启动应用"""
        self._recover_locked_target_windows("启动时自恢复，")

        # 显示托盘图标
        self._tray.show()

        # 现场人员必须先阅读流程说明并点击“知道了”，再开始监控。
        self._show_startup_hint()
        self._start_fast_export_click_timer()

        # 延后启动监控线程，让界面先完成首帧渲染，减少启动瞬间卡顿。
        QTimer.singleShot(APP_MONITOR_START_DELAY_MS, self._start_monitor_if_needed)
        self._signal_pump_timer.start()

        logger.info(
            "应用已启动，%sms 后开始监控目标程序...", APP_MONITOR_START_DELAY_MS
        )

        return self._app.exec_()


def check_single_instance():
    """检查是否已有实例在运行（通过互斥体）"""
    try:
        import ctypes

        global SINGLE_INSTANCE_MUTEX
        kernel32 = ctypes.windll.kernel32
        SINGLE_INSTANCE_MUTEX = kernel32.CreateMutexW(
            None, False, "SoftwareUsageMeter_SingleInstance"
        )
        last_error = kernel32.GetLastError()
        if last_error == 183:  # ERROR_ALREADY_EXISTS
            return False
        return True
    except Exception:
        return True


def main():
    """主入口"""
    _append_bootstrap_log("main() entered")
    _apply_safe_qt_runtime()
    _append_bootstrap_log(
        f"safe Qt runtime applied: QT_OPENGL={os.environ.get('QT_OPENGL')}, QT_QUICK_BACKEND={os.environ.get('QT_QUICK_BACKEND')}"
    )
    # 单实例检测
    if not check_single_instance():
        _append_bootstrap_log("single instance check failed")
        # 重复启动时不再弹旧提示框，避免现场人员越点越乱。
        sys.exit(1)

    _append_bootstrap_log("single instance check passed; creating Application")
    try:
        app = Application()
        _append_bootstrap_log("Application created successfully; entering event loop")
        _write_early_crash_log("Application created; entering event loop")
        sys.exit(app.run())
    except Exception as exc:
        _append_bootstrap_log(f"startup exception: {exc!r}")
        _write_early_crash_log(f"startup exception: {exc!r}\n{traceback.format_exc()}")
        logger.exception("启动阶段发生异常")
        try:
            _err_app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(
                None,
                "计时计费程序 - 启动错误",
                f"程序启动失败，请联系技术支持。\n\n"
                f"错误信息：{exc!r}\n\n"
                f"请将程序目录下的 crash.log 文件发给技术支持。",
            )
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
