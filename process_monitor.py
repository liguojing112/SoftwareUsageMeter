"""
进程监控与导出检测模块
功能：
1. 检测目标程序（像素蛋糕）是否在运行
2. 检测导出行为（通过窗口标题关键词匹配）
3. 获取目标程序的窗口句柄
"""

import logging
import time

import psutil
from PyQt5.QtCore import QThread, pyqtSignal
from PIL import Image

try:
    import win32gui
    import win32con
    import win32process
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

try:
    from PIL import ImageGrab
    HAS_IMAGE_GRAB = True
except ImportError:
    HAS_IMAGE_GRAB = False

logger = logging.getLogger(__name__)

BUILTIN_EXPORT_KEYWORDS = [
    "导出",
    "export",
    "保存",
    "save",
    "另存为",
    "save as",
]

EXPORT_PROCESS_MARKERS = [
    "isexportprocess",
    "export-single-process",
]

LOCK_WINDOW_TITLE_EXCLUDES = [
    "default ime",
    "msctfime ui",
]

LOCK_WINDOW_CLASS_KEYWORDS_EXCLUDES = [
    "ime",
    "tooltips_class32",
]

PROCESS_STARTUP_GUARD_SECONDS = 3.0
EXPORT_DETECTION_DEBOUNCE_SECONDS = 0.8
EXPORT_CLEAR_DEBOUNCE_SECONDS = 0.8
EXPORT_VISUAL_DETECTION_DEBOUNCE_SECONDS = 0.0
RUNNING_MONITOR_INTERVAL_MS = 200
POST_PAYMENT_EXPORT_CLEAR_DEBOUNCE_SECONDS = 12.0


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


def enumerate_visible_windows() -> list[int]:
    """枚举当前所有可见顶层窗口。"""
    if not HAS_WIN32:
        return []
    windows = []
    win32gui.EnumWindows(_enum_windows_callback, windows)
    return windows


def get_window_pid(hwnd: int) -> int | None:
    """获取窗口所属 PID。"""
    if not HAS_WIN32 or not hwnd:
        return None
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return pid or None
    except Exception:
        return None


def get_window_owner_hwnd(hwnd: int) -> int | None:
    """获取窗口 owner 句柄。"""
    if not HAS_WIN32 or not hwnd:
        return None
    try:
        owner = win32gui.GetWindow(hwnd, win32con.GW_OWNER)
        return owner or None
    except Exception:
        return None


def get_window_title(hwnd: int) -> str:
    """安全获取窗口标题。"""
    if not HAS_WIN32 or not hwnd:
        return ""
    try:
        return win32gui.GetWindowText(hwnd) or ""
    except Exception:
        return ""


def get_window_class(hwnd: int) -> str:
    """安全获取窗口类名。"""
    if not HAS_WIN32 or not hwnd:
        return ""
    try:
        return win32gui.GetClassName(hwnd) or ""
    except Exception:
        return ""


def normalize_export_keywords(keywords: list[str]) -> list[str]:
    """合并配置关键词和内置关键词。"""
    normalized = []
    for keyword in [*(keywords or []), *BUILTIN_EXPORT_KEYWORDS]:
        lowered = (keyword or "").strip().lower()
        if lowered and lowered not in normalized:
            normalized.append(lowered)
    return normalized


def window_matches_keywords(hwnd: int, keywords: list[str]) -> bool:
    """根据窗口标题匹配导出相关窗口。"""
    title = get_window_title(hwnd).lower()
    if not title:
        return False
    return any(keyword in title for keyword in keywords)


def get_process_family_pids(root_pid: int) -> set[int]:
    """获取根进程及其所有子进程 PID。"""
    if not root_pid:
        return set()
    family = {root_pid}
    try:
        parent = psutil.Process(root_pid)
        for child in parent.children(recursive=True):
            family.add(child.pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return family


def process_matches_export_markers(process: psutil.Process) -> bool:
    """判断子进程是否为导出相关 worker。"""
    try:
        parts = [process.name(), *(process.cmdline() or [])]
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False

    lowered_parts = " ".join(part.lower() for part in parts if part)
    return any(marker in lowered_parts for marker in EXPORT_PROCESS_MARKERS)


def find_export_worker_pid(root_pid: int) -> int | None:
    """查找像素蛋糕导出相关的子进程 PID。"""
    worker_pids = find_export_worker_pids(root_pid)
    return min(worker_pids) if worker_pids else None


def find_export_worker_pids(root_pid: int) -> set[int]:
    """查找像素蛋糕导出相关的全部子进程 PID。"""
    if not root_pid:
        return set()
    try:
        root_process = psutil.Process(root_pid)
        children = root_process.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return set()

    worker_pids = set()
    for child in children:
        if process_matches_export_markers(child):
            worker_pids.add(child.pid)
    return worker_pids


def get_new_export_worker_pids(worker_pids: set[int] | None, known_worker_pids: set[int] | None) -> set[int]:
    """计算本轮新出现的导出 worker，忽略启动前就已存在的常驻进程。"""
    return set(worker_pids or set()) - set(known_worker_pids or set())


def is_within_guard_window(now: float, started_at: float | None, guard_seconds: float) -> bool:
    """判断当前是否仍处于启动保护时间窗内。"""
    if not started_at:
        return False
    return (now - started_at) < max(guard_seconds, 0.0)


def is_debounce_satisfied(since: float | None, now: float, debounce_seconds: float) -> bool:
    """判断某个候选状态是否已连续维持到达防抖阈值。"""
    if since is None:
        return False
    return (now - since) >= max(debounce_seconds, 0.0)


def is_strong_export_signal(
    export_hwnd: int | None,
    export_pid: int | None,
    export_visual: bool = False,
) -> bool:
    """窗口标题命中、新导出 worker 或快速导出页命中时，视为强信号，可直接确认。"""
    return bool(export_hwnd or export_pid or export_visual)


def suspend_processes(pids: set[int] | list[int] | tuple[int, ...]) -> list[int]:
    """挂起一组进程，返回成功挂起的 PID 列表。"""
    suspended = []
    for pid in sorted(set(pids or []), reverse=True):
        try:
            psutil.Process(pid).suspend()
            suspended.append(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return suspended


def resume_processes(pids: set[int] | list[int] | tuple[int, ...]) -> list[int]:
    """恢复一组已挂起进程，返回成功恢复的 PID 列表。"""
    resumed = []
    for pid in sorted(set(pids or [])):
        try:
            psutil.Process(pid).resume()
            resumed.append(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return resumed


def image_matches_export_visual_state(image: Image.Image) -> bool:
    """根据界面视觉特征判断是否处于像素蛋糕导出页。"""
    if image is None:
        return False

    image = image.convert("RGB")
    width, height = image.size
    if width < 500 or height < 350:
        return False

    start_x = int(width * 0.55)
    start_y = int(height * 0.60)

    yellow_count = 0
    min_x = width
    min_y = height
    max_x = -1
    max_y = -1

    for y in range(start_y, height):
        for x in range(start_x, width):
            r, g, b = image.getpixel((x, y))
            if r > 180 and g > 140 and b < 130 and abs(r - g) < 95 and r - b > 70:
                yellow_count += 1
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    if yellow_count == 0:
        return False

    box_width = max_x - min_x + 1
    box_height = max_y - min_y + 1
    box_area = max(box_width * box_height, 1)
    fill_ratio = yellow_count / box_area

    return all([
        yellow_count >= max(int(width * height * 0.002), 1500),
        min_x >= int(width * 0.65),
        min_y >= int(height * 0.75),
        max_x >= int(width * 0.82),
        max_y >= int(height * 0.88),
        int(width * 0.08) <= box_width <= int(width * 0.35),
        int(height * 0.04) <= box_height <= int(height * 0.16),
        fill_ratio >= 0.35,
    ])


def capture_window_image(hwnd: int) -> Image.Image | None:
    """截取指定窗口当前屏幕内容。"""
    if not HAS_WIN32 or not HAS_IMAGE_GRAB or not hwnd:
        return None
    try:
        if not win32gui.IsWindow(hwnd):
            return None
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        if right - left < 500 or bottom - top < 350:
            return None
        return ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
    except Exception:
        return None


def detect_export_visual_state(main_hwnd: int | None) -> bool:
    """通过界面截图识别像素蛋糕的快速导出页。"""
    image = capture_window_image(main_hwnd) if main_hwnd else None
    return image_matches_export_visual_state(image) if image else False


def find_windows_by_pid(pid: int) -> list:
    """查找属于指定 PID 的所有可见窗口句柄"""
    if not HAS_WIN32:
        return []
    windows = enumerate_visible_windows()
    result = []
    for hwnd in windows:
        try:
            found_pid = get_window_pid(hwnd)
            if found_pid == pid:
                result.append(hwnd)
        except Exception:
            continue
    return result


def find_windows_by_pids(pids: set[int]) -> list[int]:
    """查找属于多个 PID 的所有可见窗口。"""
    if not HAS_WIN32 or not pids:
        return []
    result = []
    for hwnd in enumerate_visible_windows():
        if get_window_pid(hwnd) in pids:
            result.append(hwnd)
    return result


def find_main_window(pid: int) -> int | None:
    """查找指定 PID 的主窗口句柄（最大的可见窗口）"""
    windows = find_windows_by_pid(pid)
    if not windows:
        return None
    best_hwnd = None
    best_area = -1

    def candidate_score(hwnd: int) -> int:
        try:
            rect = win32gui.GetWindowRect(hwnd)
            width = max(rect[2] - rect[0], 0)
            height = max(rect[3] - rect[1], 0)
            if width == 0 or height == 0:
                return -1
            area = width * height
            if win32gui.IsIconic(hwnd):
                area //= 100
            return area
        except Exception:
            return -1

    for hwnd in windows:
        score = candidate_score(hwnd)
        if score > best_area:
            best_area = score
            best_hwnd = hwnd

    return best_hwnd


def check_export_dialog(pid: int, keywords: list[str], main_hwnd: int | None = None) -> int | None:
    """
    检查指定进程是否出现了包含导出关键词的窗口/对话框。
    返回匹配到的窗口句柄，未找到返回 None。
    """
    if not HAS_WIN32:
        return None

    lowered_keywords = normalize_export_keywords(keywords)
    family_pids = get_process_family_pids(pid)
    family_windows = find_windows_by_pids(family_pids)

    for hwnd in family_windows:
        if window_matches_keywords(hwnd, lowered_keywords):
            return hwnd

    foreground_hwnd = None
    try:
        foreground_hwnd = win32gui.GetForegroundWindow()
    except Exception:
        foreground_hwnd = None

    if foreground_hwnd:
        foreground_pid = get_window_pid(foreground_hwnd)
        if foreground_pid in family_pids and window_matches_keywords(foreground_hwnd, lowered_keywords):
            return foreground_hwnd

    for hwnd in enumerate_visible_windows():
        if hwnd in family_windows or not window_matches_keywords(hwnd, lowered_keywords):
            continue

        owner_hwnd = get_window_owner_hwnd(hwnd)
        owner_pid = get_window_pid(owner_hwnd) if owner_hwnd else None
        if owner_pid in family_pids:
            return hwnd

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


def is_lock_target_window(hwnd: int) -> bool:
    """杩囨护鎺夎緭鍏ユ硶銆佹彁绀虹瓑涓嶉渶閿佸畾鐨勮緟鍔╃獥鍙ｃ€?"""
    if not HAS_WIN32 or not hwnd:
        return False
    try:
        if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            return False

        title = get_window_title(hwnd).strip().lower()
        class_name = get_window_class(hwnd).strip().lower()
        if title in LOCK_WINDOW_TITLE_EXCLUDES:
            return False
        if any(keyword in class_name for keyword in LOCK_WINDOW_CLASS_KEYWORDS_EXCLUDES):
            return False
        if "ime" in title and not title.endswith(".exe"):
            return False

        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width = max(right - left, 0)
        height = max(bottom - top, 0)
        if width < 120 or height < 80:
            return False

        return True
    except Exception:
        return False


def recover_process_windows(process_name: str, hwnds: list[int] | None = None) -> list[int]:
    """鍏ㄩ噺鎭㈠鐩爣杩涚▼鐩稿叧绐楀彛鐨勫彲浜や簰鐘舵€侊紝鐢ㄤ簬鍚姩鑷剤鍜岄€€鍑哄厹搴曘€?"""
    restored = []
    seen = set()
    candidates = list(hwnds or [])

    pid = find_pid_by_name(process_name)
    if pid:
        family_pids = get_process_family_pids(pid)
        candidates.extend(find_windows_by_pids(family_pids))

    for hwnd in candidates:
        if not hwnd or hwnd in seen:
            continue
        seen.add(hwnd)
        if enable_window(hwnd):
            restored.append(hwnd)

    return restored


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
        self._export_pid = None
        self._was_exporting = False
        self._hold_export_state = False
        self._known_export_worker_pids = set()
        self._process_started_at = None
        self._export_candidate_since = None
        self._export_clear_candidate_since = None
        self._startup_guard_logged = False
        self._suspended_pids = set()
        self._post_payment_pending = False

    def _reset_export_candidates(self):
        self._export_candidate_since = None
        self._export_clear_candidate_since = None

    def _get_export_clear_debounce_seconds(self) -> float:
        """付款确认后延长一次导出结束判定，避免同一次导出的尾部痕迹被当成下一单。"""
        if self._post_payment_pending:
            return POST_PAYMENT_EXPORT_CLEAR_DEBOUNCE_SECONDS
        return EXPORT_CLEAR_DEBOUNCE_SECONDS

    def get_runtime_snapshot(self) -> dict:
        """返回监控线程当前关键状态，便于异常日志和现场排查。"""
        return {
            "current_pid": self._current_pid,
            "main_hwnd": self._main_hwnd,
            "export_hwnd": self._export_hwnd,
            "export_pid": self._export_pid,
            "is_process_running": self._was_running,
            "is_exporting": self._was_exporting,
            "hold_export_state": self._hold_export_state,
            "known_export_worker_pids": sorted(self._known_export_worker_pids),
            "process_started_at": self._process_started_at,
            "export_candidate_since": self._export_candidate_since,
            "export_clear_candidate_since": self._export_clear_candidate_since,
            "suspended_pids": sorted(self._suspended_pids),
            "post_payment_pending": self._post_payment_pending,
        }

    def run(self):
        """监控主循环"""
        while self._running:
            now = time.monotonic()
            process_name = self._config.process_name
            keywords = self._config.export_window_keywords

            # 检测进程状态
            pid = find_pid_by_name(process_name)
            is_running = pid is not None

            if is_running and not self._was_running:
                self._current_pid = pid
                self._main_hwnd = find_main_window(pid)
                self._known_export_worker_pids = find_export_worker_pids(pid)
                self._process_started_at = now
                self._startup_guard_logged = False
                self._post_payment_pending = False
                self._reset_export_candidates()
                logger.info(f"检测到目标程序启动: PID={pid}")
                self.process_started.emit()
            elif is_running and self._current_pid != pid:
                self._current_pid = pid
                self._main_hwnd = find_main_window(pid)
                self._known_export_worker_pids = find_export_worker_pids(pid)
                self._process_started_at = now
                self._startup_guard_logged = False
                self._post_payment_pending = False
                self._reset_export_candidates()
                logger.info(f"检测到目标程序实例变化，切换到 PID={pid}")
            elif not is_running and self._was_running:
                self._current_pid = None
                self._main_hwnd = None
                self._export_hwnd = None
                self._export_pid = None
                self._was_exporting = False
                self._known_export_worker_pids = set()
                self._process_started_at = None
                self._startup_guard_logged = False
                self._post_payment_pending = False
                self._reset_export_candidates()
                self._suspended_pids = set()
                logger.info("目标程序已退出")
                self.process_stopped.emit()

            self._was_running = is_running

            # 检测导出行为（仅当进程运行时）
            if is_running and self._current_pid:
                self._main_hwnd = find_main_window(self._current_pid) or self._main_hwnd
                worker_pids = find_export_worker_pids(self._current_pid)
                new_worker_pids = get_new_export_worker_pids(worker_pids, self._known_export_worker_pids)
                export_pid = min(new_worker_pids) if new_worker_pids else None
                export_hwnd = check_export_dialog(self._current_pid, keywords, self._main_hwnd)
                export_visual = detect_export_visual_state(self._main_hwnd)
                has_export_evidence = bool(export_hwnd or export_pid or export_visual)
                startup_guard_active = is_within_guard_window(
                    now, self._process_started_at, PROCESS_STARTUP_GUARD_SECONDS
                )

                if has_export_evidence and not self._was_exporting:
                    self._export_clear_candidate_since = None
                    if startup_guard_active:
                        self._export_candidate_since = None
                        if not self._startup_guard_logged:
                            logger.info(
                                "启动保护生效，暂不触发收费: pid=%s, export_hwnd=%s, export_worker_pid=%s, export_visual=%s",
                                self._current_pid,
                                export_hwnd,
                                export_pid,
                                export_visual,
                            )
                            self._startup_guard_logged = True
                    else:
                        if is_strong_export_signal(export_hwnd, export_pid, export_visual):
                            self._export_hwnd = export_hwnd
                            self._export_pid = export_pid
                            self._was_exporting = True
                            self._export_candidate_since = None
                            self._startup_guard_logged = False
                            if export_hwnd:
                                logger.info(
                                    "确认导出窗口: hwnd=%s, pid=%s, title=%s, class=%s, export_worker_pid=%s",
                                    export_hwnd,
                                    get_window_pid(export_hwnd),
                                    get_window_title(export_hwnd),
                                    get_window_class(export_hwnd),
                                    export_pid,
                                )
                            elif export_visual:
                                logger.info("确认快速导出页视觉特征: main_hwnd=%s", self._main_hwnd)
                            else:
                                logger.info("确认导出子进程: export_worker_pid=%s", export_pid)
                            self.export_detected.emit()
                        elif self._export_candidate_since is None:
                            self._export_candidate_since = now
                            logger.info(
                                "检测到导出候选，进入视觉防抖观察: pid=%s, export_hwnd=%s, export_worker_pid=%s, export_visual=%s",
                                self._current_pid,
                                export_hwnd,
                                export_pid,
                                export_visual,
                            )
                        elif is_debounce_satisfied(
                            self._export_candidate_since, now, EXPORT_VISUAL_DETECTION_DEBOUNCE_SECONDS
                        ):
                            self._export_hwnd = export_hwnd
                            self._export_pid = export_pid
                            self._was_exporting = True
                            self._export_candidate_since = None
                            self._startup_guard_logged = False
                            if export_hwnd:
                                logger.info(
                                    "确认导出窗口: hwnd=%s, pid=%s, title=%s, class=%s, export_worker_pid=%s",
                                    export_hwnd,
                                    get_window_pid(export_hwnd),
                                    get_window_title(export_hwnd),
                                    get_window_class(export_hwnd),
                                    export_pid,
                                )
                            elif export_visual:
                                logger.info("确认导出界面视觉特征: main_hwnd=%s", self._main_hwnd)
                            else:
                                logger.info("确认导出子进程: export_worker_pid=%s", export_pid)
                            self.export_detected.emit()
                elif not has_export_evidence and not self._was_exporting:
                    self._export_candidate_since = None
                    self._startup_guard_logged = False
                elif not has_export_evidence and self._was_exporting:
                    if self._hold_export_state:
                        interval = min(self._config.monitor_interval_ms, 500)
                        self.msleep(interval)
                        continue
                    clear_debounce_seconds = self._get_export_clear_debounce_seconds()
                    if self._export_clear_candidate_since is None:
                        self._export_clear_candidate_since = now
                        if self._post_payment_pending:
                            logger.info(
                                "检测到付款后导出结束候选，进入延迟观察: debounce=%ss",
                                clear_debounce_seconds,
                            )
                        else:
                            logger.info("检测到导出结束候选，进入防抖观察")
                    elif is_debounce_satisfied(
                        self._export_clear_candidate_since, now, clear_debounce_seconds
                    ):
                        self._export_hwnd = None
                        self._export_pid = None
                        self._was_exporting = False
                        self._export_clear_candidate_since = None
                        logger.info("确认导出窗口已关闭")
                        self.export_cancelled.emit()
                elif has_export_evidence and self._was_exporting:
                    self._export_clear_candidate_since = None
                self._known_export_worker_pids = worker_pids

            # 等待下一次检测
            interval = self._config.monitor_interval_ms
            if is_running:
                interval = min(interval, RUNNING_MONITOR_INTERVAL_MS)
            self.msleep(interval)

    def stop(self):
        """停止监控线程"""
        self._running = False
        self.wait(3000)

    def set_export_state_hold(self, hold: bool):
        """收费弹窗显示期间暂时保持导出状态，避免被遮罩误判为取消。"""
        self._hold_export_state = hold

    def set_post_payment_pending(self, active: bool):
        """标记当前是否仍在等待同一次已付款导出完全结束。"""
        if self._post_payment_pending != active:
            self._export_clear_candidate_since = None
        self._post_payment_pending = active

    def suspend_target_processes(self) -> list[int]:
        """挂起像素蛋糕主进程及其子进程，阻止导出在付款前继续执行。"""
        if not self._current_pid:
            return []

        target_pids = get_process_family_pids(self._current_pid)
        suspended = suspend_processes(target_pids)
        if suspended:
            self._suspended_pids.update(suspended)
            logger.info("已挂起目标进程族，等待付款确认: %s", suspended)
        return suspended

    def resume_target_processes(self) -> list[int]:
        """恢复此前挂起的像素蛋糕进程。"""
        if not self._suspended_pids:
            return []

        resumed = resume_processes(self._suspended_pids)
        if resumed:
            logger.info("已恢复目标进程族: %s", resumed)
        self._suspended_pids.difference_update(resumed)
        return resumed

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
            if hwnd and hwnd not in handles and is_lock_target_window(hwnd):
                handles.append(hwnd)

        for hwnd in [self._main_hwnd, self._export_hwnd]:
            if hwnd and hwnd not in handles:
                handles.append(hwnd)

        return handles
