"""
进程监控与导出检测模块
功能：
1. 检测目标程序（像素蛋糕）是否在运行
2. 检测导出行为（通过窗口标题关键词匹配）
3. 获取目标程序的窗口句柄
"""

import logging

import psutil
from PyQt5.QtCore import QThread, pyqtSignal

try:
    import win32gui
    import win32process
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

logger = logging.getLogger(__name__)


def find_pid_by_name(process_name: str) -> int | None:
    """通过进程名查找 PID，未找到返回 None"""
    process_name_lower = process_name.lower()
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if proc.info['name'] and proc.info['name'].lower() == process_name_lower:
                return proc.info['pid']
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def is_process_running(process_name: str) -> bool:
    """检查指定进程是否正在运行"""
    return find_pid_by_name(process_name) is not None


def _enum_windows_callback(hwnd, results):
    """枚举窗口的回调函数"""
    if win32gui.IsWindowVisible(hwnd):
        results.append(hwnd)


def find_windows_by_pid(pid: int) -> list:
    """查找属于指定 PID 的所有可见窗口句柄"""
    if not HAS_WIN32:
        return []
    windows = []
    win32gui.EnumWindows(_enum_windows_callback, windows)
    result = []
    for hwnd in windows:
        try:
            _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
            if found_pid == pid:
                result.append(hwnd)
        except Exception:
            continue
    return result


def find_main_window(pid: int) -> int | None:
    """查找指定 PID 的主窗口句柄（最大的可见窗口）"""
    windows = find_windows_by_pid(pid)
    if not windows:
        return None
    # 选择面积最大的窗口作为主窗口
    best_hwnd = None
    best_area = 0
    for hwnd in windows:
        try:
            rect = win32gui.GetWindowRect(hwnd)
            area = (rect[2] - rect[0]) * (rect[3] - rect[1])
            if area > best_area:
                best_area = area
                best_hwnd = hwnd
        except Exception:
            continue
    return best_hwnd


def check_export_dialog(pid: int, keywords: list[str]) -> int | None:
    """
    检查指定进程是否出现了包含导出关键词的窗口/对话框。
    返回匹配到的窗口句柄，未找到返回 None。
    """
    if not HAS_WIN32:
        return None
    lowered_keywords = [kw.lower() for kw in keywords if kw]
    windows = find_windows_by_pid(pid)
    for hwnd in windows:
        try:
            title = win32gui.GetWindowText(hwnd)
            if title and any(kw in title.lower() for kw in lowered_keywords):
                return hwnd
        except Exception:
            continue
    return None


def disable_window(hwnd: int) -> bool:
    """禁用指定窗口（使其无法接收输入）"""
    if not HAS_WIN32 or not hwnd:
        return False
    try:
        win32gui.EnableWindow(hwnd, False)
        return True
    except Exception as e:
        logger.error(f"禁用窗口失败: {e}")
        return False


def enable_window(hwnd: int) -> bool:
    """启用指定窗口（恢复可交互）"""
    if not HAS_WIN32 or not hwnd:
        return False
    try:
        win32gui.EnableWindow(hwnd, True)
        return True
    except Exception as e:
        logger.error(f"启用窗口失败: {e}")
        return False


class ProcessMonitor(QThread):
    """
    进程监控线程
    定期检测目标进程状态和导出行为，通过信号通知主程序
    """

    # 信号：目标程序已启动
    process_started = pyqtSignal()
    # 信号：目标程序已退出
    process_stopped = pyqtSignal()
    # 信号：检测到导出行为
    export_detected = pyqtSignal()
    # 信号：导出窗口已关闭（用户取消了导出）
    export_cancelled = pyqtSignal()

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._running = True
        self._was_running = False
        self._current_pid = None
        self._main_hwnd = None
        self._export_hwnd = None
        self._was_exporting = False

    def run(self):
        """监控主循环"""
        while self._running:
            process_name = self._config.process_name
            keywords = self._config.export_window_keywords

            # 检测进程状态
            pid = find_pid_by_name(process_name)
            is_running = pid is not None

            if is_running and not self._was_running:
                self._current_pid = pid
                self._main_hwnd = find_main_window(pid)
                logger.info(f"检测到目标程序启动: PID={pid}")
                self.process_started.emit()
            elif is_running and self._current_pid != pid:
                self._current_pid = pid
                self._main_hwnd = find_main_window(pid)
                logger.info(f"检测到目标程序实例变化，切换到 PID={pid}")
            elif not is_running and self._was_running:
                self._current_pid = None
                self._main_hwnd = None
                self._export_hwnd = None
                self._was_exporting = False
                logger.info("目标程序已退出")
                self.process_stopped.emit()

            self._was_running = is_running

            # 检测导出行为（仅当进程运行时）
            if is_running and self._current_pid:
                self._main_hwnd = find_main_window(self._current_pid) or self._main_hwnd
                export_hwnd = check_export_dialog(self._current_pid, keywords)
                if export_hwnd and not self._was_exporting:
                    self._export_hwnd = export_hwnd
                    self._was_exporting = True
                    logger.info(f"检测到导出窗口: hwnd={export_hwnd}")
                    self.export_detected.emit()
                elif not export_hwnd and self._was_exporting:
                    self._export_hwnd = None
                    self._was_exporting = False
                    logger.info("导出窗口已关闭")
                    self.export_cancelled.emit()

            # 等待下一次检测
            interval = self._config.monitor_interval_ms
            self.msleep(interval)

    def stop(self):
        """停止监控线程"""
        self._running = False
        self.wait(3000)

    @property
    def current_pid(self) -> int | None:
        return self._current_pid

    @property
    def main_hwnd(self) -> int | None:
        return self._main_hwnd

    @property
    def export_hwnd(self) -> int | None:
        return self._export_hwnd

    @property
    def is_process_running(self) -> bool:
        return self._was_running

    @property
    def is_export_dialog_visible(self) -> bool:
        return self._was_exporting

    @property
    def lock_target_hwnds(self) -> list[int]:
        """返回当前应锁定的像素蛋糕窗口集合。"""
        if not HAS_WIN32 or not self._current_pid:
            return [hwnd for hwnd in [self._main_hwnd, self._export_hwnd] if hwnd]

        handles = []
        for hwnd in find_windows_by_pid(self._current_pid):
            if hwnd and hwnd not in handles:
                handles.append(hwnd)

        for hwnd in [self._main_hwnd, self._export_hwnd]:
            if hwnd and hwnd not in handles:
                handles.append(hwnd)

        return handles
