"""
进程监控与导出检测模块
功能：
1. 检测目标程序（像素蛋糕）是否在运行
2. 检测导出行为（通过窗口标题关键词匹配）
3. 获取目标程序的窗口句柄
"""

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import ctypes
from datetime import datetime

import psutil
from PyQt5.QtCore import QThread, pyqtSignal
from PIL import Image, ImageEnhance, ImageOps

try:
    import win32gui
    import win32con
    import win32api
    import win32process
    import win32ui

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
    # 兼容更多可能的窗口标题
    "选择导出",
    "批量导出",
    "快速导出",
    "exporting",
    "output",
    "输出",
    "下载",
    "download",
]

EXPORT_PROCESS_MARKERS = [
    "isexportprocess",
    "export-single-process",
]

EXPORT_WINDOW_TITLE_EXCLUDES = [
    "确认删除该导出进度",
    "导出至创意",
    "至创意",
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
RUNNING_MONITOR_INTERVAL_MS = 50
DETECTION_DIAGNOSTIC_INTERVAL_SECONDS = 5.0
POST_PAYMENT_EXPORT_CLEAR_DEBOUNCE_SECONDS = 12.0
POST_PAYMENT_EXPORT_TAIL_GUARD_SECONDS = 6.0
EXPORT_COUNT_REFRESH_INTERVAL_SECONDS = 1.0
EXPORT_COUNT_CACHE_TTL_SECONDS = 30.0
EXPORT_SUMMARY_PROBE_INTERVAL_SECONDS = 0.3
MONITOR_VISUAL_WARMUP_SECONDS = 0.8
CENTERED_DIALOG_SCAN_INTERVAL_SECONDS = 4.0
CENTERED_DIALOG_DEBUG_DUMP_INTERVAL_SECONDS = 6.0
EXPORT_DEBUG_MAX_BUNDLES = 12
EXPORT_DEBUG_DIRNAME = "debug_export_captures"
FAST_SUMMARY_OCR_TIMEOUT_SECONDS = 0.9
WINDOWS_OCR_TIMEOUT_SECONDS = 2.0
CREATIVE_TRANSFER_SUMMARY_SENTINEL = -1001
CENTERED_DIALOG_SCAN_REGIONS = [
    (0.15, 0.12, 0.48, 0.25),
    (0.10, 0.08, 0.55, 0.32),
]
EXPORT_COUNT_CONTEXT_KEYWORDS = [
    "快速导出",
    "导出至",
    "指定文件夹",
    "图片格式",
    "质量",
    "jpg",
    "自定义设置",
]
CREATIVE_SELECTION_CONTEXT_KEYWORDS = [
    "选图",
    "当前图",
    "全创意",
    "至创意",
    "创意模块",
    "导出选择图",
    "导出当前图",
]
CREATIVE_TRANSFER_CONTEXT_KEYWORDS = [
    "导出至创意",
    "至创意",
    "创意模块",
    "导出选择图",
    "导出当前图",
    "精修导出至创意",
]
LOCAL_EXPORT_ONLY_CONTEXT_KEYWORDS = [
    "快速导出",
    "指定文件夹",
    "图片格式",
    "质量",
    "jpg",
    "jpeg",
    "png",
    "自定义设置",
    "上传至选片交付",
]
EXPORT_BUTTON_TEXT_KEYWORDS = [
    "导出",
    "export",
]

OCR_TEXT_REPLACEMENTS = [
    ("导出选择图", "导出选择图"),
    ("导出当前图", "导出当前图"),
    ("导出至创意", "导出至创意"),
    ("取肖", "取消"),
    ("学选图", "选图"),
    ("选图前图", "选图当前图"),
    ("前图图", "当前图"),
    ("ѡͼ", "选图"),
    ("ԭͼ", "原图"),
    ("Чͼ", "效图"),
    ("ͼƬ", "图片"),
    ("ǰͼ", "前图"),
    ("ԭʼ", "原始"),
    ("ģ֧", "模支"),
]

OCR_CHAR_REPLACEMENTS = str.maketrans(
    {
        "ѡ": "选",
        "ԭ": "原",
        "Ч": "效",
        "ͼ": "图",
        "Ƭ": "片",
        "ǰ": "前",
        "ʼ": "始",
        "ȡ": "取",
        "Ф": "消",
        "ģ": "模",
        "֧": "支",
    }
)

if hasattr(Image, "Resampling"):
    RESAMPLING_LANCZOS = Image.Resampling.LANCZOS
else:
    RESAMPLING_LANCZOS = Image.LANCZOS

WINDOWS_OCR_SCRIPT_TEMPLATE = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrResult, Windows.Media.Ocr, ContentType=WindowsRuntime]

function Await-AsyncOperation($operation, $resultType) {
    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {
            $_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition -and
            $_.GetGenericArguments().Count -eq 1 -and $_.GetParameters().Count -eq 1
        } |
        Select-Object -First 1
    $generic = $method.MakeGenericMethod($resultType)
    $task = $generic.Invoke($null, @($operation))
    return $task.Result
}

$path = '__IMAGE_PATH__'
$fileOp = [Windows.Storage.StorageFile]::GetFileFromPathAsync($path)
$file = Await-AsyncOperation $fileOp ([Windows.Storage.StorageFile])
$streamOp = $file.OpenAsync([Windows.Storage.FileAccessMode]::Read)
$stream = Await-AsyncOperation $streamOp ([Windows.Storage.Streams.IRandomAccessStream])
$decoderOp = [Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)
$decoder = Await-AsyncOperation $decoderOp ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmapOp = $decoder.GetSoftwareBitmapAsync()
$bitmap = Await-AsyncOperation $bitmapOp ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
$resultOp = $engine.RecognizeAsync($bitmap)
$result = Await-AsyncOperation $resultOp ([Windows.Media.Ocr.OcrResult])
$result.Text
"""


def find_pids_by_name(process_name: str) -> list[int]:
    """通过进程名查找全部匹配 PID。"""
    process_name_lower = process_name.lower()
    matched = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if proc.info["name"] and proc.info["name"].lower() == process_name_lower:
                matched.append(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return matched


def _get_window_area(hwnd: int | None) -> int:
    """计算窗口面积，用于在多实例中优先挑选真正的主界面进程。"""
    if not HAS_WIN32 or not hwnd:
        return -1
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    except Exception:
        return -1
    return max(right - left, 0) * max(bottom - top, 0)


def is_valid_target_main_window(hwnd: int | None) -> bool:
    """判断窗口是否像真正可操作的像素蛋糕主窗口，而不是后台/过渡进程窗口。"""
    if not HAS_WIN32 or not hwnd:
        return False
    try:
        if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            return False

        title = get_window_title(hwnd).strip().lower()
        class_name = get_window_class(hwnd).strip().lower()
        if class_name in {"consolewindowclass"}:
            return False
        if any(
            keyword in class_name
            for keyword in ["toolsavebits", "tooltips_class32", "ime"]
        ):
            return False
        if not title and not any(
            keyword in class_name for keyword in ["qt", "qwindow"]
        ):
            return False

        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width = max(right - left, 0)
        height = max(bottom - top, 0)
        if width < 500 or height < 350:
            return False

        return True
    except Exception:
        return False


def find_pid_by_name(process_name: str) -> int | None:
    """通过进程名查找最合适的 PID，优先选择真正带主窗口的实例。"""
    matched_pids = find_pids_by_name(process_name)
    if not matched_pids:
        return None

    candidates: list[tuple[int, float, int]] = []
    fallback_candidates: list[tuple[int, float]] = []
    for pid in matched_pids:
        try:
            created_at = psutil.Process(pid).create_time()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            created_at = 0.0
        main_hwnd = find_main_window(pid)
        if is_valid_target_main_window(main_hwnd):
            window_area = _get_window_area(main_hwnd)
            candidates.append((pid, created_at, window_area))
        else:
            # 进程存在但主窗口尚未就绪（正在启动、最小化、DPI 异常等），
            # 保留为 fallback，避免漏检。
            fallback_candidates.append((pid, created_at))

    if candidates:
        candidates.sort(
            key=lambda item: (
                item[2] > 0,  # 先选有主窗口的
                item[2],  # 再选窗口更大的
                item[1],  # 最后选更新的实例
            ),
            reverse=True,
        )
        selected_pid = candidates[0][0]
        if len(matched_pids) > 1:
            logger.info(
                "检测到多个同名进程，已选择主实例: process_name=%s, matched_pids=%s, selected_pid=%s",
                process_name,
                matched_pids,
                selected_pid,
            )
        return selected_pid

    # 没有带有效主窗口的候选时，fallback 到最新启动的进程，
    # 避免因 DPI 缩放/窗口未完全加载导致进程永远检测不到。
    if fallback_candidates:
        fallback_candidates.sort(key=lambda item: item[1], reverse=True)
        selected_pid = fallback_candidates[0][0]
        logger.info(
            "未找到带有效主窗口的实例，使用 fallback PID: process_name=%s, matched_pids=%s, selected_pid=%s",
            process_name,
            matched_pids,
            selected_pid,
        )
        return selected_pid

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
    title = get_window_title(hwnd).strip().lower()
    if not title:
        return False
    if any(excluded in title for excluded in EXPORT_WINDOW_TITLE_EXCLUDES):
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


def get_new_export_worker_pids(
    worker_pids: set[int] | None, known_worker_pids: set[int] | None
) -> set[int]:
    """计算本轮新出现的导出 worker，忽略启动前就已存在的常驻进程。"""
    return set(worker_pids or set()) - set(known_worker_pids or set())


def is_within_guard_window(
    now: float, started_at: float | None, guard_seconds: float
) -> bool:
    """判断当前是否仍处于启动保护时间窗内。"""
    if not started_at:
        return False
    return (now - started_at) < max(guard_seconds, 0.0)


def is_debounce_satisfied(
    since: float | None, now: float, debounce_seconds: float
) -> bool:
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
    return locate_export_button_bounds(image) is not None


def looks_like_creative_transfer_layout(
    image: Image.Image | None,
    button_bounds: tuple[int, int, int, int] | None,
) -> bool:
    """用纯视觉结构判断是否是“导出至创意”中转框。

    创意中转框在黄色按钮上方有一整块深色统计面板（原图/精修图），
    本地导出框则是文件夹、格式、质量等表单项。这个判断不跑 OCR，
    用来在热路径里快速挡掉“导出至创意”的误触发。
    """
    if image is None or button_bounds is None:
        return False

    try:
        image = image.convert("RGB")
        width, height = image.size
        bx1, by1, bx2, by2 = button_bounds
        button_width = max(bx2 - bx1, 1)
        button_height = max(by2 - by1, 1)

        left = max(int(bx1 - button_width * 4.8), 0)
        right = min(int(bx2 + button_width * 0.2), width)
        top = max(int(by1 - button_height * 7.0), 0)
        bottom = max(int(by1 - button_height * 3.0), top + 1)
        bottom = min(bottom, height)
        if right - left < button_width * 2.2 or bottom - top < button_height * 1.2:
            return False

        crop = ImageOps.grayscale(image.crop((left, top, right, bottom)))
        if crop.width > 360:
            scale = 360 / crop.width
            crop = crop.resize(
                (360, max(int(crop.height * scale), 1)), RESAMPLING_LANCZOS
            )

        max_dark_run = 0
        dark_run = 0
        row_width = max(crop.width, 1)
        for y in range(crop.height):
            row = [crop.getpixel((x, y)) for x in range(row_width)]
            dark_ratio = sum(1 for value in row if value <= 42) / row_width
            if dark_ratio >= 0.62:
                dark_run += 1
                max_dark_run = max(max_dark_run, dark_run)
            else:
                dark_run = 0

        is_creative_layout = max_dark_run >= max(10, int(crop.height * 0.28))
        if is_creative_layout:
            logger.info(
                "视觉结构识别为导出至创意中转页: button_bounds=%s, dark_run=%s, crop_size=%s",
                button_bounds,
                max_dark_run,
                crop.size,
            )
        return is_creative_layout
    except Exception:
        logger.debug("导出至创意结构判断失败", exc_info=True)
        return False


def locate_export_button_bounds(
    image: Image.Image,
) -> tuple[int, int, int, int] | None:
    """定位快速导出页右下角黄色导出按钮的近似范围。"""
    if image is None:
        return None

    image = image.convert("RGB")
    width, height = image.size
    if width < 500 or height < 350:
        return None

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
            # 放宽黄色检测条件，兼容不同显示器色彩设置
            is_yellow = (
                # 标准黄色/橙色
                (r > 170 and g > 130 and b < 140 and abs(r - g) < 100 and r - b > 50)
                or
                # 更亮的黄色
                (r > 200 and g > 160 and b < 100)
                or
                # 橙黄色
                (r > 180 and g > 100 and g < 180 and b < 100)
            )
            if is_yellow:
                yellow_count += 1
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    if yellow_count == 0:
        return None

    box_width = max_x - min_x + 1
    box_height = max_y - min_y + 1
    box_area = max(box_width * box_height, 1)
    fill_ratio = yellow_count / box_area

    # 放宽匹配条件
    is_match = all(
        [
            yellow_count >= max(int(width * height * 0.001), 800),  # 降低像素阈值
            min_x >= int(width * 0.55),  # 放宽左边界
            min_y >= int(height * 0.65),  # 放宽上边界
            max_x >= int(width * 0.75),  # 放宽右边界
            max_y >= int(height * 0.80),  # 放宽下边界
            int(width * 0.06) <= box_width <= int(width * 0.40),  # 放宽宽度范围
            int(height * 0.03) <= box_height <= int(height * 0.20),  # 放宽高度范围
            fill_ratio >= 0.25,  # 降低填充率要求
        ]
    )
    if not is_match:
        return None

    return (min_x, min_y, max_x, max_y)


def capture_window_image(hwnd: int) -> Image.Image | None:
    """截取指定窗口当前屏幕内容。"""
    if not HAS_WIN32 or not hwnd:
        return None
    try:
        if not win32gui.IsWindow(hwnd):
            return None
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        if right - left < 500 or bottom - top < 350:
            return None
        image = _capture_window_image_printwindow(hwnd, left, top, right, bottom)
        if image is not None:
            return image
        if not HAS_IMAGE_GRAB:
            return None
        return ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
    except Exception:
        return None


def _capture_window_image_printwindow(
    hwnd: int,
    left: int | None = None,
    top: int | None = None,
    right: int | None = None,
    bottom: int | None = None,
) -> Image.Image | None:
    """优先通过 PrintWindow 抓取窗口内容，避免依赖窗口必须处于前台。"""
    if not HAS_WIN32 or not hwnd:
        return None

    try:
        if not win32gui.IsWindow(hwnd):
            return None
        if None in (left, top, right, bottom):
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width = max(int(right - left), 0)
        height = max(int(bottom - top), 0)
        if width < 500 or height < 350:
            return None

        hwnd_dc = win32gui.GetWindowDC(hwnd)
        if not hwnd_dc:
            return None

        source_dc = None
        memory_dc = None
        bitmap = None
        try:
            source_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            memory_dc = source_dc.CreateCompatibleDC()
            bitmap = win32ui.CreateBitmap()
            bitmap.CreateCompatibleBitmap(source_dc, width, height)
            memory_dc.SelectObject(bitmap)

            printed = ctypes.windll.user32.PrintWindow(
                hwnd, memory_dc.GetSafeHdc(), 0x2
            )
            if printed != 1:
                printed = ctypes.windll.user32.PrintWindow(
                    hwnd, memory_dc.GetSafeHdc(), 0x0
                )
            if printed != 1:
                return None

            bitmap_info = bitmap.GetInfo()
            bitmap_bits = bitmap.GetBitmapBits(True)
            image = Image.frombuffer(
                "RGB",
                (bitmap_info["bmWidth"], bitmap_info["bmHeight"]),
                bitmap_bits,
                "raw",
                "BGRX",
                0,
                1,
            )
            return image.copy()
        finally:
            if bitmap is not None:
                win32gui.DeleteObject(bitmap.GetHandle())
            if memory_dc is not None:
                memory_dc.DeleteDC()
            if source_dc is not None:
                source_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwnd_dc)
    except Exception as exc:
        logger.debug("PrintWindow 截图失败: hwnd=%s, error=%s", hwnd, exc)
        return None


def detect_export_visual_state(main_hwnd: int | None) -> bool:
    """通过界面截图识别像素蛋糕的快速导出页。"""
    image = capture_window_image(main_hwnd) if main_hwnd else None
    return image_matches_export_visual_state(image) if image else False


def run_windows_ocr(
    image_path: str, timeout_seconds: float = WINDOWS_OCR_TIMEOUT_SECONDS
) -> str:
    """调用 Windows 自带 OCR 识别截图文本，无需额外安装第三方环境。"""
    if os.name != "nt" or not image_path or not os.path.exists(image_path):
        return ""

    startupinfo = None
    if hasattr(subprocess, "STARTUPINFO"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0

    escaped_path = image_path.replace("'", "''")
    script = WINDOWS_OCR_SCRIPT_TEMPLATE.replace("__IMAGE_PATH__", escaped_path)

    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout_seconds,
            startupinfo=startupinfo,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("调用 Windows OCR 失败: %s", exc)
        return ""

    if completed.returncode != 0:
        logger.warning("Windows OCR 返回异常: %s", completed.stderr.strip())
        return ""

    return (completed.stdout or "").strip()


def run_windows_ocr_on_image(
    image: Image.Image | None,
    prefix: str = "ocr",
    timeout_seconds: float = WINDOWS_OCR_TIMEOUT_SECONDS,
) -> str:
    """将 PIL 图像临时落盘后交给 Windows OCR。"""
    if image is None:
        return ""

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f"{prefix}_", suffix=".png", delete=False
        ) as handle:
            temp_path = handle.name
        image.save(temp_path, format="PNG")
        return run_windows_ocr(temp_path, timeout_seconds=timeout_seconds)
    except Exception as exc:
        logger.warning("图像 OCR 失败: %s", exc)
        return ""
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def normalize_ocr_text(text: str) -> str:
    """规范化 OCR 文本，便于后续规则匹配。"""
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return ""

    compact = compact.translate(OCR_CHAR_REPLACEMENTS)
    for source, target in OCR_TEXT_REPLACEMENTS:
        compact = compact.replace(source, target)
    return compact


def contains_export_page_context(text: str) -> bool:
    """判断 OCR 文本是否像像素蛋糕导出页。"""
    compact = normalize_ocr_text(text)
    if not compact:
        return False

    if contains_creative_transfer_context(compact):
        return False

    has_local_export_context = any(
        keyword in compact for keyword in EXPORT_COUNT_CONTEXT_KEYWORDS
    )
    has_creative_selection_context = any(
        keyword in compact for keyword in CREATIVE_SELECTION_CONTEXT_KEYWORDS
    )

    if has_creative_selection_context and not has_local_export_context:
        return False

    if has_local_export_context:
        return True

    if re.search(r"导出\d+张", compact):
        return True

    return bool(re.search(r"(精修|免费|原图)[^0-9]{0,8}[（(]?\d+[）)]?", compact))


def contains_creative_transfer_context(text: str) -> bool:
    """判断 OCR 文本是否属于“导出至创意”的中转页。

    该页面只是把图片送入创意模块，真正需要计费的是进入创意后的
    “导出至本地”对话框，所以这里必须在收费触发前排除。
    """
    compact = normalize_ocr_text(text)
    if not compact:
        return False

    compact_lower = compact.lower()
    has_creative_context = any(
        keyword in compact for keyword in CREATIVE_TRANSFER_CONTEXT_KEYWORDS
    )
    if not has_creative_context:
        has_creative_context = bool(
            "创意" in compact
            and (
                "选图" in compact
                or "当前图" in compact
                or ("原图" in compact and "精修图" in compact)
            )
        )
    if not has_creative_context:
        # 部分机器 OCR 会把“创意模块/精修图”识别成乱码，但“选图 + 原图”
        # 这组结构仍然能稳定区别于本地导出页。
        has_creative_context = "选图" in compact and (
            "原图" in compact or "当前图" in compact or "前图" in compact
        )
    if not has_creative_context:
        return False

    has_local_export_context = any(
        keyword.lower() in compact_lower for keyword in LOCAL_EXPORT_ONLY_CONTEXT_KEYWORDS
    )
    return not has_local_export_context


def contains_export_button_text(text: str) -> bool:
    """判断按钮 OCR 文本是否像“导出”按钮。"""
    compact = normalize_ocr_text(text).lower()
    if not compact:
        return False

    if contains_creative_transfer_context(compact):
        return False

    return any(keyword in compact for keyword in EXPORT_BUTTON_TEXT_KEYWORDS)


def _crop_relative(
    image: Image.Image, region: tuple[float, float, float, float]
) -> Image.Image | None:
    """按相对比例裁剪图像。"""
    width, height = image.size
    left = max(int(width * region[0]), 0)
    top = max(int(height * region[1]), 0)
    right = min(int(width * region[2]), width)
    bottom = min(int(height * region[3]), height)
    if right - left < 40 or bottom - top < 24:
        return None
    return image.crop((left, top, right, bottom))


def _crop_summary_from_button_anchor(
    image: Image.Image,
    button_bounds: tuple[int, int, int, int] | None,
    widen: bool = False,
) -> Image.Image | None:
    """根据黄色导出按钮反推出其上方的导出摘要区。"""
    if image is None or button_bounds is None:
        return None

    width, height = image.size
    bx1, by1, bx2, by2 = button_bounds
    button_width = max(bx2 - bx1, 1)
    button_height = max(by2 - by1, 1)

    left_factor = 5.2 if widen else 4.8
    right_factor = 0.9 if widen else 0.6
    top_factor = 10.2 if widen else 9.2
    height_factor = 3.0 if widen else 2.4

    left = max(int(bx1 - button_width * left_factor), 0)
    top = max(int(by1 - button_height * top_factor), 0)
    right = min(
        max(int(bx2 + button_width * right_factor), left + int(button_width * 4.8)),
        width,
    )
    bottom = min(max(int(top + button_height * height_factor), top + 24), height)

    if right - left < 40 or bottom - top < 24:
        return None
    return image.crop((left, top, right, bottom))


def _prepare_export_count_ocr_variants(
    image: Image.Image,
    cache_mode: bool = False,
    dialog_mode: bool = False,
    button_bounds: tuple[int, int, int, int] | None = None,
) -> list[tuple[str, Image.Image]]:
    """构建导出张数 OCR 变体，深色 UI 会做放大和增强。"""
    if image is None:
        return []

    width, height = image.size
    if width < 120 or height < 80:
        return [("full", image)]

    if dialog_mode:
        relative_regions = [
            ("summary", (0.04, 0.08, 0.84, 0.24)),
            ("summary_wide", (0.02, 0.04, 0.92, 0.28)),
        ]
        if not cache_mode:
            relative_regions.append(("header_and_counts", (0.0, 0.0, 0.94, 0.34)))
    else:
        relative_regions = [
            ("summary_popup_title", (0.03, 0.02, 0.45, 0.18)),
            ("summary_popup_title_wide", (0.02, 0.02, 0.58, 0.20)),
            ("summary", (0.02, 0.08, 0.52, 0.24)),
            ("summary_center", (0.18, 0.12, 0.66, 0.30)),
            ("type_counts", (0.02, 0.18, 0.78, 0.37)),
        ]
        if not cache_mode:
            relative_regions.extend(
                [
                    ("summary_wide", (0.0, 0.0, 0.72, 0.28)),
                    ("summary_wide_center", (0.12, 0.06, 0.82, 0.34)),
                    ("header_and_counts", (0.0, 0.0, 0.86, 0.45)),
                    ("header_and_counts_center", (0.10, 0.04, 0.86, 0.42)),
                ]
            )

    variants: list[tuple[str, Image.Image]] = []
    seen_sizes: set[tuple[str, tuple[int, int]]] = set()

    def add_variant(label: str, variant: Image.Image):
        key = (label, variant.size)
        if key in seen_sizes:
            return
        seen_sizes.add(key)
        variants.append((label, variant))

    def build_variant_set(
        base_label: str, base_image: Image.Image, include_binary: bool
    ):
        base_width, base_height = base_image.size
        scaled = base_image.resize(
            (max(base_width * 2, 1), max(base_height * 2, 1)),
            RESAMPLING_LANCZOS,
        )
        add_variant(f"{base_label}-rgb2x", scaled)

        grayscale = ImageOps.grayscale(scaled)
        contrasted = ImageEnhance.Contrast(ImageOps.autocontrast(grayscale)).enhance(
            1.8
        )
        sharpened = ImageEnhance.Sharpness(contrasted).enhance(2.2)
        add_variant(f"{base_label}-gray2x", sharpened)

        if include_binary:
            binary = sharpened.point(lambda value: 255 if value >= 148 else 0).convert(
                "L"
            )
            add_variant(f"{base_label}-binary2x", ImageOps.invert(binary))

    anchored_summary = _crop_summary_from_button_anchor(
        image, button_bounds, widen=False
    )
    if anchored_summary is not None:
        build_variant_set(
            "summary_anchor", anchored_summary, include_binary=not cache_mode
        )

    anchored_summary_wide = _crop_summary_from_button_anchor(
        image, button_bounds, widen=True
    )
    if anchored_summary_wide is not None:
        build_variant_set(
            "summary_anchor_wide", anchored_summary_wide, include_binary=not cache_mode
        )

    for label, region in relative_regions:
        cropped = _crop_relative(image, region)
        if cropped is None:
            continue
        build_variant_set(label, cropped, include_binary=not cache_mode)

    if not cache_mode:
        build_variant_set("full", image, include_binary=False)

    return variants


def extract_export_image_count_from_text(
    text: str, allow_numeric_fallback: bool = True
) -> int | None:
    """从 OCR 文本中提取导出张数。"""
    if not text:
        logger.debug("OCR文本为空")
        return None

    logger.debug(f"原始OCR文本: '{text}'")
    compact = normalize_ocr_text(text)
    logger.debug(f"紧凑化OCR文本: '{compact}'")

    if not compact:
        return None

    if contains_creative_transfer_context(compact):
        logger.info("忽略导出至创意中转页张数: text=%s", compact[:120])
        return None

    has_export_context = contains_export_page_context(compact)

    # 尝试多种匹配模式
    patterns = [
        (r"导出(\d+)张图片", "直接匹配: 导出X张图片"),
        (r"导出(\d+)张图", "直接匹配: 导出X张图"),
        (r"导出(\d+)张", "通用匹配: 导出X张"),
        (r"(\d+)张图片", "简单匹配: X张图片"),
        (r"图片(\d+)张", "倒序匹配: 图片X张"),
        (r"共(\d+)张", "总计匹配: 共X张"),
        (r"总计(\d+)张", "总计匹配2: 总计X张"),
    ]

    for pattern, description in patterns:
        match = re.search(pattern, compact)
        if match:
            count = int(match.group(1))
            logger.debug(f"{description}: 找到 {count} 张")
            return count

    # 尝试分类统计模式
    per_type_counts = []
    type_patterns = [
        (r"精修效果图[（(](\d+)[）)]", "精修效果图"),
        (r"免费效果图[（(](\d+)[）)]", "免费效果图"),
        (r"原图[（(](\d+)[）)]", "原图"),
        (r"精修[（(](\d+)[）)]", "精修"),
        (r"免费[（(](\d+)[）)]", "免费"),
    ]

    for pattern, type_name in type_patterns:
        match = re.search(pattern, compact)
        if match:
            count = int(match.group(1))
            logger.debug(f"找到{type_name}: {count} 张")
            per_type_counts.append(count)

    if per_type_counts:
        total = sum(per_type_counts)
        logger.debug(f"分类统计总计: {total} 张 (来自 {len(per_type_counts)} 个分类)")
        return total

    # 尝试查找纯数字（可能是导出数量）
    numbers = re.findall(r"(\d+)", compact)
    if allow_numeric_fallback and numbers and has_export_context:
        logger.debug(f"找到数字: {numbers}")
        # 如果只有一个数字，可能是导出数量
        if len(numbers) == 1:
            count = int(numbers[0])
            if count > 0 and count <= 100:  # 合理范围
                logger.debug(f"使用唯一数字作为导出数量: {count}")
                return count

    logger.debug("未找到导出张数匹配")
    return None


def extract_export_summary_count_from_text(text: str) -> int | None:
    """只针对左上角摘要文案提取导出张数，避免被分类区和路径区带偏。"""
    compact = normalize_ocr_text(text)
    if not compact:
        return None

    if contains_creative_transfer_context(compact):
        logger.info("忽略导出至创意摘要张数: text=%s", compact[:120])
        return None

    # 排除"导入"相关文本，避免创意编辑页的"成功导入X张图片"被误识别
    if "导入" in compact:
        logger.info("忽略导入相关文本，不识别为导出张数: text=%s", compact[:120])
        return None

    patterns = [
        r"导出(\d+)张图片",
        r"导出(\d+)张图",
        r"导出(\d+)张",
        r"(\d+)张图片",
        r"(\d+)张图",
        r"(?:^|[^\d])(\d+)图片",
    ]
    for pattern in patterns:
        match = re.search(pattern, compact)
        if match:
            return int(match.group(1))

    return None


def extract_export_count_from_variant_text(variant_name: str, text: str) -> int | None:
    """结合变体区域语义，对 OCR 结果做更宽松的数字兜底。"""
    export_count = extract_export_image_count_from_text(
        text, allow_numeric_fallback=False
    )
    if export_count is not None:
        return export_count

    compact = normalize_ocr_text(text)
    if not compact:
        return None

    numbers = [int(value) for value in re.findall(r"(\d+)", compact)]
    plausible_numbers = [value for value in numbers if 0 <= value <= 100]
    if not plausible_numbers:
        return None

    has_path_like_noise = any(
        token in compact.lower()
        for token in ["/", "\\", ".py", ".png", "user", "download", "windows", ":"]
    )
    has_ascii_noise = bool(re.search(r"[A-Za-z]{2,}", compact))

    if variant_name.startswith("summary-"):
        positives = [value for value in plausible_numbers if value > 0]
        if (
            len(positives) == 1
            and len(compact) <= 20
            and not has_path_like_noise
            and not has_ascii_noise
        ):
            logger.info(
                "导出张数数字兜底命中(summary): %s (variant=%s, text=%s)",
                positives[0],
                variant_name,
                compact[:80],
            )
            return positives[0]

    if variant_name.startswith("type_counts-"):
        if has_path_like_noise or has_ascii_noise:
            return None
        if not re.search(r"(精修|免费|原图|[（(]\d+[)）])", compact):
            return None
        candidate_numbers = [value for value in plausible_numbers[:3] if value <= 20]
        if (
            len(candidate_numbers) >= 2
            and candidate_numbers
            and any(value > 0 for value in candidate_numbers)
        ):
            total = sum(candidate_numbers)
            logger.info(
                "导出张数数字兜底命中(type_counts): %s (variant=%s, text=%s)",
                total,
                variant_name,
                compact[:80],
            )
            return total

    return None


def detect_export_summary_count_from_image(
    image: Image.Image | None,
    dialog_mode: bool = False,
    button_bounds: tuple[int, int, int, int] | None = None,
    fast_mode: bool = False,
    return_creative_sentinel: bool = False,
) -> int | None:
    """优先从导出页左上角摘要区识别张数。"""
    if image is None:
        return None

    variants = [
        item
        for item in _prepare_export_count_ocr_variants(
            image,
            cache_mode=True,
            dialog_mode=dialog_mode,
            button_bounds=button_bounds,
        )
        if item[0].startswith("summary")
    ]
    if fast_mode:
        fast_variant_priority = {
            "summary_anchor_wide-rgb2x": 0,
            "summary_anchor-rgb2x": 1,
            "summary_popup_title_wide-rgb2x": 2,
            "summary_popup_title-rgb2x": 3,
            "summary_wide_center-rgb2x": 4,
            "summary_center-rgb2x": 5,
            "summary_wide-rgb2x": 6,
            "summary-rgb2x": 7,
        }
        variants.sort(key=lambda item: fast_variant_priority.get(item[0], 100))
        variants = variants[:4]

    for variant_name, variant in variants:
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="export_summary_", suffix=".png", delete=False
            ) as handle:
                temp_path = handle.name
            variant.save(temp_path, format="PNG")
            ocr_text = run_windows_ocr(
                temp_path,
                timeout_seconds=FAST_SUMMARY_OCR_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.warning("导出摘要 OCR 失败: %s", exc)
            ocr_text = ""
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

        if contains_creative_transfer_context(ocr_text):
            logger.info(
                "左上角摘要识别为导出至创意中转页: variant=%s, text=%s",
                variant_name,
                normalize_ocr_text(ocr_text)[:120],
            )
            if return_creative_sentinel:
                return CREATIVE_TRANSFER_SUMMARY_SENTINEL
            continue

        export_count = extract_export_summary_count_from_text(ocr_text)
        if export_count is not None:
            logger.info(
                "左上角导出摘要命中: %s (variant=%s, text=%s)",
                export_count,
                variant_name,
                normalize_ocr_text(ocr_text)[:120],
            )
            return export_count

    return None


def detect_export_image_count_from_image(
    image: Image.Image | None,
    cache_mode: bool = False,
    explicit_only: bool = False,
    dialog_mode: bool = False,
    button_bounds: tuple[int, int, int, int] | None = None,
) -> int | None:
    """从导出页截图中自动识别导出张数。"""
    if image is None:
        logger.debug("检测导出张数：图像为None")
        return None

    width, height = image.size
    logger.debug(f"检测导出张数：图像尺寸 {width}x{height}")
    summary_export_count = detect_export_summary_count_from_image(
        image, dialog_mode=dialog_mode, button_bounds=button_bounds, fast_mode=True
    )
    if summary_export_count is not None:
        return summary_export_count

    variants = _prepare_export_count_ocr_variants(
        image,
        cache_mode=cache_mode,
        dialog_mode=dialog_mode,
        button_bounds=button_bounds,
    )
    logger.debug(f"总共 {len(variants)} 个图像变体用于OCR")
    fallback_candidates: dict[int, list[str]] = {}

    for i, (variant_name, variant) in enumerate(variants):
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="export_count_", suffix=".png", delete=False
            ) as handle:
                temp_path = handle.name
            variant.save(temp_path, format="PNG")
            logger.debug(
                "变体 %s(%s) 已保存到临时文件: %s", i + 1, variant_name, temp_path
            )
            ocr_text = run_windows_ocr(temp_path)
            logger.debug(
                f"变体 {i + 1}({variant_name}) OCR结果: '{ocr_text[:100]}...'"
                if len(ocr_text) > 100
                else f"变体 {i + 1}({variant_name}) OCR结果: '{ocr_text}'"
            )
        except Exception as exc:
            logger.warning("导出张数 OCR 预处理失败: %s", exc)
            ocr_text = ""
        finally:
            if "temp_path" in locals() and temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

        explicit_export_count = extract_export_image_count_from_text(
            ocr_text, allow_numeric_fallback=False
        )
        if explicit_export_count is not None:
            logger.info(
                "成功识别导出张数: %s (来自变体 %s:%s)",
                explicit_export_count,
                i + 1,
                variant_name,
            )
            return explicit_export_count

        if explicit_only:
            logger.debug("变体 %s(%s) 未命中显式导出张数", i + 1, variant_name)
            continue

        fallback_export_count = extract_export_count_from_variant_text(
            variant_name, ocr_text
        )
        if fallback_export_count is not None:
            fallback_candidates.setdefault(fallback_export_count, []).append(
                variant_name
            )
            logger.debug(
                "记录导出张数候选: count=%s, variant=%s, hits=%s",
                fallback_export_count,
                variant_name,
                len(fallback_candidates[fallback_export_count]),
            )
        else:
            logger.debug("变体 %s(%s) 未识别到导出张数", i + 1, variant_name)

    stable_candidates = [
        (count, variant_names)
        for count, variant_names in fallback_candidates.items()
        if len(variant_names) >= 2
    ]
    if stable_candidates:
        stable_candidates.sort(key=lambda item: (-len(item[1]), item[0]))
        selected_count, selected_variants = stable_candidates[0]
        logger.info(
            "成功识别导出张数(多变体一致): %s (variants=%s)",
            selected_count,
            ",".join(selected_variants),
        )
        return selected_count

    if explicit_only or cache_mode:
        logger.debug("所有图像变体均未识别到导出张数")
    else:
        logger.warning("所有图像变体均未识别到导出张数")
    return None


def detect_export_image_count(main_hwnd: int | None) -> int | None:
    """从像素蛋糕导出页自动识别导出张数。"""
    image = capture_window_image(main_hwnd) if main_hwnd else None
    return detect_export_image_count_from_image(image)


def detect_export_page_context_from_image(image: Image.Image | None) -> bool:
    """通过 OCR 判断当前截图是否真的是快速导出页。"""
    if image is None:
        return False

    context_variants = [
        item
        for item in _prepare_export_count_ocr_variants(image, cache_mode=False)
        if item[0].startswith(("summary_wide", "header_and_counts", "full"))
    ]
    for variant_name, variant in context_variants:
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="export_context_", suffix=".png", delete=False
            ) as handle:
                temp_path = handle.name
            variant.save(temp_path, format="PNG")
            ocr_text = run_windows_ocr(temp_path)
        except Exception as exc:
            logger.warning("导出页上下文 OCR 失败: %s", exc)
            ocr_text = ""
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

        if contains_export_page_context(ocr_text):
            logger.info(
                "导出页上下文命中: variant=%s, text=%s",
                variant_name,
                normalize_ocr_text(ocr_text)[:120],
            )
            return True

    return False


def detect_export_button_text_from_image(
    image: Image.Image | None, button_bounds: tuple[int, int, int, int] | None
) -> bool:
    """通过 OCR 判断黄色按钮自身是否真的是“导出”。"""
    if image is None or button_bounds is None:
        return False

    try:
        crop = image.crop(button_bounds)
    except Exception:
        return False

    button_variants = [
        (
            "button-rgb6x",
            crop.resize(
                (max(crop.width * 6, 1), max(crop.height * 6, 1)), RESAMPLING_LANCZOS
            ),
        ),
    ]
    gray = ImageOps.grayscale(button_variants[0][1])
    gray = ImageEnhance.Contrast(ImageOps.autocontrast(gray)).enhance(2.5)
    button_variants.append(("button-gray6x", gray))
    button_variants.append(("button-inv6x", ImageOps.invert(gray)))

    for variant_name, variant in button_variants:
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="export_button_", suffix=".png", delete=False
            ) as handle:
                temp_path = handle.name
            variant.save(temp_path, format="PNG")
            ocr_text = run_windows_ocr(temp_path)
        except Exception as exc:
            logger.warning("导出按钮 OCR 失败: %s", exc)
            ocr_text = ""
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

        if contains_export_button_text(ocr_text):
            logger.info(
                "导出按钮文字命中: variant=%s, text=%s",
                variant_name,
                normalize_ocr_text(ocr_text)[:60],
            )
            return True

    return False


def get_preferred_capture_hwnd(
    root_pid: int | None,
    fallback_hwnd: int | None,
    preferred_hwnd: int | None = None,
) -> int | None:
    """优先返回当前前台的目标进程家族窗口，否则回退到主窗口或最大窗口。"""
    if not HAS_WIN32:
        return preferred_hwnd or fallback_hwnd

    family_pids = get_process_family_pids(root_pid) if root_pid else set()
    try:
        foreground_hwnd = win32gui.GetForegroundWindow()
    except Exception:
        foreground_hwnd = None

    if preferred_hwnd and win32gui.IsWindow(preferred_hwnd):
        preferred_pid = get_window_pid(preferred_hwnd)
        if not family_pids or preferred_pid in family_pids:
            return preferred_hwnd

    if foreground_hwnd and get_window_pid(foreground_hwnd) in family_pids:
        return foreground_hwnd

    if fallback_hwnd and win32gui.IsWindow(fallback_hwnd):
        return fallback_hwnd

    best_hwnd = None
    best_area = -1
    for hwnd in find_windows_by_pids(family_pids):
        try:
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        except Exception:
            continue
        area = max(right - left, 0) * max(bottom - top, 0)
        if area > best_area:
            best_area = area
            best_hwnd = hwnd

    return best_hwnd or fallback_hwnd


def is_process_family_foreground(
    root_pid: int | None, fallback_hwnd: int | None
) -> bool:
    """判断像素蛋糕当前是否位于前台。"""
    if not HAS_WIN32:
        return True
    try:
        foreground_hwnd = win32gui.GetForegroundWindow()
    except Exception:
        return False
    family_pids = get_process_family_pids(root_pid) if root_pid else set()
    if foreground_hwnd and get_window_pid(foreground_hwnd) in family_pids:
        return True
    if fallback_hwnd and foreground_hwnd == fallback_hwnd:
        return True
    return False


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
            if not is_valid_target_main_window(hwnd):
                return -1
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


def check_export_dialog(
    pid: int, keywords: list[str], main_hwnd: int | None = None
) -> int | None:
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
        if foreground_pid in family_pids and window_matches_keywords(
            foreground_hwnd, lowered_keywords
        ):
            return foreground_hwnd

    for hwnd in enumerate_visible_windows():
        if hwnd in family_windows or not window_matches_keywords(
            hwnd, lowered_keywords
        ):
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
        if any(
            keyword in class_name for keyword in LOCK_WINDOW_CLASS_KEYWORDS_EXCLUDES
        ):
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


def recover_process_windows(
    process_name: str, hwnds: list[int] | None = None
) -> list[int]:
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


def activate_window(hwnd: int | None) -> bool:
    """尽量把目标窗口恢复到前台并恢复可见。"""
    if not HAS_WIN32 or not hwnd:
        return False
    try:
        if not win32gui.IsWindow(hwnd):
            return False
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        else:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        win32gui.BringWindowToTop(hwnd)
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        try:
            win32gui.SetActiveWindow(hwnd)
        except Exception:
            pass
        return True
    except Exception:
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
    # 信号：检测到用户刚点击导出按钮，用于尽早显示等待遮罩
    export_button_pre_clicked = pyqtSignal()
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
        self._monitor_started_at = None
        self._export_candidate_since = None
        self._export_clear_candidate_since = None
        self._startup_guard_logged = False
        self._suspended_pids = set()
        self._post_payment_pending = False
        self._post_payment_pending_since = None
        self._cached_export_count = None
        self._cached_export_count_at = None
        self._cached_export_count_pid = None
        self._last_export_count_refresh_at = 0.0
        self._last_export_capture_image = None
        self._last_export_capture_at = None
        self._last_export_capture_pid = None
        self._last_export_capture_hwnd = None
        self._last_export_capture_dialog_mode = False
        self._last_left_button_down = False
        self._last_export_button_pre_signal_at = 0.0
        self._export_page_context_active = False
        self._export_page_context_checked_at = 0.0
        self._export_page_context_hwnd = None
        self._creative_transfer_context_active = False
        self._creative_transfer_ignore_worker_until = 0.0
        self._last_centered_dialog_scan_at = 0.0
        self._last_summary_probe_at = 0.0
        self._last_summary_probe_hwnd = None
        self._last_summary_probe_button_bounds = None
        self._last_detection_diagnostic_at = 0.0
        self._debug_export_capture_enabled = bool(
            self._config.get("debug_export_capture", False)
        )
        # 默认开启居中对话框扫描，覆盖更多机器上的导出场景。
        self._centered_dialog_scan_enabled = bool(
            self._config.get("centered_dialog_scan", True)
        )
        self._debug_export_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), EXPORT_DEBUG_DIRNAME
        )
        self._last_debug_export_dump_at = 0.0
        self._debug_export_dump_seq = 0
        self._last_debug_export_bundle = None
        self._last_heartbeat = time.monotonic()
        self._cleanup_debug_export_artifacts_if_disabled()
        logger.info(
            "监控器初始化: process_name=%s, keywords=%s, monitor_interval_ms=%s, "
            "running_interval_ms=%s, startup_guard_s=%s, visual_warmup_s=%s, "
            "summary_probe_interval_s=%s, centered_dialog_scan=%s, debug_export_capture=%s",
            self._config.process_name,
            self._config.export_window_keywords,
            self._config.monitor_interval_ms,
            RUNNING_MONITOR_INTERVAL_MS,
            PROCESS_STARTUP_GUARD_SECONDS,
            MONITOR_VISUAL_WARMUP_SECONDS,
            EXPORT_SUMMARY_PROBE_INTERVAL_SECONDS,
            self._centered_dialog_scan_enabled,
            self._debug_export_capture_enabled,
        )

    def _reset_export_candidates(self):
        self._export_candidate_since = None
        self._export_clear_candidate_since = None

    def _reset_export_count_cache(self):
        self._cached_export_count = None
        self._cached_export_count_at = None
        self._cached_export_count_pid = None
        self._last_export_count_refresh_at = 0.0
        self._last_export_capture_image = None
        self._last_export_capture_at = None
        self._last_export_capture_pid = None
        self._last_export_capture_hwnd = None
        self._last_export_capture_dialog_mode = False
        self._export_page_context_active = False
        self._export_page_context_checked_at = 0.0
        self._export_page_context_hwnd = None
        self._creative_transfer_context_active = False
        self._creative_transfer_ignore_worker_until = 0.0
        self._last_centered_dialog_scan_at = 0.0
        self._last_summary_probe_at = 0.0
        self._last_summary_probe_hwnd = None
        self._last_summary_probe_button_bounds = None

    def _log_detection_diagnostic(
        self,
        now: float,
        capture_hwnd: int | None,
        export_hwnd: int | None,
        export_pid: int | None,
        main_image: Image.Image | None,
        export_visual_candidate: bool,
        export_button_clicked: bool,
        summary_probe_count: int | None,
        has_cached_export_count: bool,
        has_export_evidence: bool,
        startup_guard_active: bool,
        should_skip_visual_probe: bool,
        dialog_mode: bool,
        creative_transfer_context: bool,
        trigger_reason: str,
    ):
        if (
            self._last_detection_diagnostic_at
            and (now - self._last_detection_diagnostic_at)
            < DETECTION_DIAGNOSTIC_INTERVAL_SECONDS
        ):
            return
        self._last_detection_diagnostic_at = now
        capture_title = get_window_title(capture_hwnd) if capture_hwnd else ""
        capture_class = get_window_class(capture_hwnd) if capture_hwnd else ""
        logger.info(
            "导出检测诊断: pid=%s, main_hwnd=%s, capture_hwnd=%s, capture_title=%s, "
            "capture_class=%s, export_hwnd=%s, export_worker_pid=%s, image_ok=%s, "
            "visual_candidate=%s, button_clicked=%s, summary_probe=%s, cached_count=%s, "
            "has_evidence=%s, startup_guard=%s, visual_warmup_skip=%s, dialog_mode=%s, "
            "creative_transfer=%s, centered_scan=%s, trigger_reason=%s",
            self._current_pid,
            self._main_hwnd,
            capture_hwnd,
            capture_title,
            capture_class,
            export_hwnd,
            export_pid,
            main_image is not None,
            export_visual_candidate,
            export_button_clicked,
            summary_probe_count,
            self.get_recent_export_count(5.0) if has_cached_export_count else None,
            has_export_evidence,
            startup_guard_active,
            should_skip_visual_probe,
            dialog_mode,
            creative_transfer_context,
            self._centered_dialog_scan_enabled,
            trigger_reason,
        )

    def _remember_export_count(self, export_count: int | None, observed_at: float):
        if export_count is None or export_count < 0:
            return
        self._cached_export_count = export_count
        self._cached_export_count_at = observed_at
        self._cached_export_count_pid = self._current_pid

    def _remember_export_capture(
        self,
        image: Image.Image | None,
        observed_at: float,
        capture_hwnd: int | None,
        dialog_mode: bool,
    ):
        if image is None:
            return
        self._last_export_capture_image = image.copy()
        self._last_export_capture_at = observed_at
        self._last_export_capture_pid = self._current_pid
        self._last_export_capture_hwnd = capture_hwnd
        self._last_export_capture_dialog_mode = dialog_mode

    def _prune_export_debug_bundles(self):
        if not os.path.isdir(self._debug_export_dir):
            return

        bundle_dirs = [
            os.path.join(self._debug_export_dir, entry)
            for entry in os.listdir(self._debug_export_dir)
            if os.path.isdir(os.path.join(self._debug_export_dir, entry))
        ]
        bundle_dirs.sort(key=lambda path: os.path.getmtime(path), reverse=True)
        for stale_dir in bundle_dirs[EXPORT_DEBUG_MAX_BUNDLES:]:
            try:
                shutil.rmtree(stale_dir)
            except OSError:
                pass

    def _cleanup_debug_export_artifacts_if_disabled(self):
        """默认关闭调试时，顺手清掉历史调试包，避免现场目录越堆越乱。"""
        if self._debug_export_capture_enabled or not os.path.isdir(
            self._debug_export_dir
        ):
            return

        removed_any = False
        for entry in os.listdir(self._debug_export_dir):
            path = os.path.join(self._debug_export_dir, entry)
            if not os.path.isdir(path):
                continue
            try:
                shutil.rmtree(path)
                removed_any = True
            except OSError:
                pass

        try:
            if not os.listdir(self._debug_export_dir):
                os.rmdir(self._debug_export_dir)
        except OSError:
            pass

        if removed_any:
            logger.info("调试截图未开启，已清理旧的导出调试包")

    def _dump_export_debug_bundle(
        self,
        now: float,
        capture_hwnd: int | None,
        main_image: Image.Image | None,
        button_bounds: tuple[int, int, int, int] | None,
        reason: str,
    ) -> str | None:
        """保存当前导出检测相关截图和 OCR 原文，便于现场排查。"""
        if (
            not self._debug_export_capture_enabled
            or main_image is None
            or (
                self._last_debug_export_dump_at
                and (now - self._last_debug_export_dump_at)
                < CENTERED_DIALOG_DEBUG_DUMP_INTERVAL_SECONDS
            )
        ):
            return None

        self._last_debug_export_dump_at = now
        self._debug_export_dump_seq += 1
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        safe_reason = re.sub(r"[^A-Za-z0-9_-]+", "_", reason or "probe").strip("_")
        bundle_name = (
            f"{timestamp}_{self._debug_export_dump_seq:03d}_{safe_reason or 'probe'}"
        )
        bundle_dir = os.path.join(self._debug_export_dir, bundle_name)
        os.makedirs(bundle_dir, exist_ok=True)

        meta = {
            "reason": reason,
            "capture_hwnd": capture_hwnd,
            "button_bounds": list(button_bounds) if button_bounds else None,
            "image_size": list(main_image.size),
            "cached_export_count": self._cached_export_count,
            "export_page_context_active": self._export_page_context_active,
            "process_pid": self._current_pid,
            "dumped_at": timestamp,
        }

        ocr_records: list[dict] = []

        def save_image(name: str, image: Image.Image | None):
            if image is None:
                return
            image.save(os.path.join(bundle_dir, name), format="PNG")

        def add_ocr_record(name: str, image: Image.Image | None):
            if image is None:
                return
            ocr_text = run_windows_ocr_on_image(image, prefix=f"debug_{name}")
            ocr_records.append(
                {
                    "name": name,
                    "normalized": normalize_ocr_text(ocr_text)[:300],
                    "raw": ocr_text[:1200],
                }
            )

        save_image("00_main.png", main_image)
        add_ocr_record("00_main", main_image)

        if button_bounds is not None:
            try:
                button_crop = main_image.crop(button_bounds)
            except Exception:
                button_crop = None
            save_image("01_button.png", button_crop)
            add_ocr_record("01_button", button_crop)

            summary_anchor = _crop_summary_from_button_anchor(
                main_image, button_bounds, widen=False
            )
            summary_anchor_wide = _crop_summary_from_button_anchor(
                main_image, button_bounds, widen=True
            )
            save_image("02_summary_anchor.png", summary_anchor)
            add_ocr_record("02_summary_anchor", summary_anchor)
            save_image("03_summary_anchor_wide.png", summary_anchor_wide)
            add_ocr_record("03_summary_anchor_wide", summary_anchor_wide)

        summary_center = _crop_relative(main_image, (0.18, 0.12, 0.66, 0.30))
        summary_wide_center = _crop_relative(main_image, (0.12, 0.06, 0.82, 0.34))
        type_counts = _crop_relative(main_image, (0.02, 0.18, 0.78, 0.37))
        save_image("04_summary_center.png", summary_center)
        add_ocr_record("04_summary_center", summary_center)
        save_image("05_summary_wide_center.png", summary_wide_center)
        add_ocr_record("05_summary_wide_center", summary_wide_center)
        save_image("06_type_counts.png", type_counts)
        add_ocr_record("06_type_counts", type_counts)

        for index, region in enumerate(CENTERED_DIALOG_SCAN_REGIONS, start=1):
            cropped = _crop_relative(main_image, region)
            save_image(f"10_centered_scan_{index}.png", cropped)
            add_ocr_record(f"10_centered_scan_{index}", cropped)
            if cropped is None:
                continue
            scaled = cropped.resize(
                (max(cropped.width * 2, 1), max(cropped.height * 2, 1)),
                RESAMPLING_LANCZOS,
            )
            gray = ImageOps.grayscale(scaled)
            enhanced = ImageEnhance.Contrast(ImageOps.autocontrast(gray)).enhance(1.8)
            enhanced = ImageEnhance.Sharpness(enhanced).enhance(2.2)
            save_image(f"11_centered_scan_{index}_enhanced.png", enhanced)
            add_ocr_record(f"11_centered_scan_{index}_enhanced", enhanced)

        with open(
            os.path.join(bundle_dir, "meta.json"), "w", encoding="utf-8"
        ) as handle:
            json.dump(meta, handle, ensure_ascii=False, indent=2)
        with open(
            os.path.join(bundle_dir, "ocr_results.json"), "w", encoding="utf-8"
        ) as handle:
            json.dump(ocr_records, handle, ensure_ascii=False, indent=2)

        self._prune_export_debug_bundles()
        self._last_debug_export_bundle = bundle_dir
        logger.info("已保存导出调试包: %s", bundle_dir)
        return bundle_dir

    def _refresh_export_count_cache(
        self,
        now: float,
        main_image: Image.Image | None = None,
        dialog_mode: bool = False,
        button_bounds: tuple[int, int, int, int] | None = None,
    ) -> int | None:
        if (
            self._last_export_count_refresh_at
            and (now - self._last_export_count_refresh_at)
            < EXPORT_COUNT_REFRESH_INTERVAL_SECONDS
        ):
            return self._cached_export_count

        self._last_export_count_refresh_at = now
        if main_image is None:
            main_image = self.capture_main_window_image()
        export_count = detect_export_image_count_from_image(
            main_image,
            cache_mode=True,
            explicit_only=True,
            dialog_mode=dialog_mode,
            button_bounds=button_bounds,
        )
        if export_count is not None:
            logger.info("已缓存导出页张数: %s", export_count)
            self._remember_export_count(export_count, now)
        return export_count

    def _probe_export_summary_count(
        self,
        now: float,
        main_image: Image.Image | None,
        capture_hwnd: int | None = None,
        dialog_mode: bool = False,
        button_bounds: tuple[int, int, int, int] | None = None,
    ) -> int | None:
        """直接用摘要区做一次导出页预判，命中后立刻可用于触发收费。"""
        if main_image is None or button_bounds is None:
            return None
        same_probe_target = (
            self._last_summary_probe_hwnd == capture_hwnd
            and self._last_summary_probe_button_bounds == button_bounds
        )
        if (
            self._last_summary_probe_at
            and same_probe_target
            and (now - self._last_summary_probe_at)
            < EXPORT_SUMMARY_PROBE_INTERVAL_SECONDS
        ):
            return None

        self._last_summary_probe_at = now
        self._last_summary_probe_hwnd = capture_hwnd
        self._last_summary_probe_button_bounds = button_bounds
        export_count = detect_export_summary_count_from_image(
            main_image,
            dialog_mode=dialog_mode,
            button_bounds=button_bounds,
            fast_mode=True,
            return_creative_sentinel=True,
        )
        if export_count == CREATIVE_TRANSFER_SUMMARY_SENTINEL:
            self._creative_transfer_context_active = True
            self._creative_transfer_ignore_worker_until = now + 60.0  # 延长到60秒
            logger.info("导出摘要预判识别为导出至创意中转页，本轮不触发收费")
            return export_count
        if export_count is not None:
            self._creative_transfer_context_active = False
            logger.info("导出摘要预判命中: count=%s", export_count)
            self._remember_export_count(export_count, now)
        return export_count

    def _confirm_export_detected(
        self,
        now: float,
        main_image: Image.Image | None,
        capture_hwnd: int | None,
        export_hwnd: int | None,
        export_pid: int | None,
        pre_export_visual: bool,
        dialog_mode: bool,
        trigger_reason: str,
    ):
        """在监控线程内立刻确认导出，避免后续慢 OCR 再拖延触发。"""
        self._remember_export_capture(
            main_image,
            now,
            capture_hwnd,
            dialog_mode=dialog_mode,
        )
        self._export_hwnd = export_hwnd
        self._export_pid = export_pid
        self._was_exporting = True
        # 在信号发到主线程前，先把监控状态切到“导出保持”，并立即冻结目标进程，
        # 避免慢机器上收费框还没显示出来，像素蛋糕已经先完成导出。
        self._hold_export_state = True
        self._post_payment_pending = False
        self._post_payment_pending_since = None
        self.suspend_target_processes()
        self._export_candidate_since = None
        self._startup_guard_logged = False
        if export_hwnd:
            logger.info(
                "确认导出窗口: hwnd=%s, pid=%s, title=%s, class=%s, export_worker_pid=%s, trigger_reason=%s",
                export_hwnd,
                get_window_pid(export_hwnd),
                get_window_title(export_hwnd),
                get_window_class(export_hwnd),
                export_pid,
                trigger_reason,
            )
        elif pre_export_visual:
            logger.info(
                "确认导出页预判: capture_hwnd=%s, cached_export_count=%s, trigger_reason=%s",
                capture_hwnd,
                self.get_recent_export_count(5.0),
                trigger_reason,
            )
        else:
            logger.info(
                "确认导出子进程: export_worker_pid=%s, trigger_reason=%s",
                export_pid,
                trigger_reason,
            )
        self.export_detected.emit()

    def _get_export_clear_debounce_seconds(self) -> float:
        """付款确认后延长一次导出结束判定，避免同一次导出的尾部痕迹被当成下一单。"""
        if self._post_payment_pending:
            return POST_PAYMENT_EXPORT_CLEAR_DEBOUNCE_SECONDS
        return EXPORT_CLEAR_DEBOUNCE_SECONDS

    def _refresh_export_page_context(
        self,
        now: float,
        capture_hwnd: int | None,
        main_image: Image.Image | None,
        button_bounds: tuple[int, int, int, int] | None,
    ) -> bool:
        """节流刷新当前截图是否真的是导出页。"""
        if main_image is None or not capture_hwnd or button_bounds is None:
            self._export_page_context_active = False
            self._export_page_context_checked_at = now
            self._export_page_context_hwnd = capture_hwnd
            return False

        should_recheck = any(
            [
                self._export_page_context_hwnd != capture_hwnd,
                not self._export_page_context_checked_at,
                (now - self._export_page_context_checked_at)
                >= EXPORT_COUNT_REFRESH_INTERVAL_SECONDS,
            ]
        )
        if should_recheck:
            self._export_page_context_active = all(
                [
                    detect_export_page_context_from_image(main_image),
                    detect_export_button_text_from_image(main_image, button_bounds),
                ]
            )
            self._export_page_context_checked_at = now
            self._export_page_context_hwnd = capture_hwnd

        return self._export_page_context_active

    def _scan_for_centered_export_dialog(
        self,
        now: float,
        main_image: Image.Image | None,
    ) -> int | None:
        """扫描主窗口中央区域，检测嵌入式导出对话框并提取张数。"""
        if main_image is None:
            return None
        if (
            now - self._last_centered_dialog_scan_at
        ) < CENTERED_DIALOG_SCAN_INTERVAL_SECONDS:
            return None
        self._last_centered_dialog_scan_at = now

        width, height = main_image.size
        if width < 500 or height < 350:
            return None

        for region in CENTERED_DIALOG_SCAN_REGIONS:
            cropped = _crop_relative(main_image, region)
            if cropped is None:
                continue
            scaled = cropped.resize(
                (max(cropped.width * 2, 1), max(cropped.height * 2, 1)),
                RESAMPLING_LANCZOS,
            )
            gray = ImageOps.grayscale(scaled)
            enhanced = ImageEnhance.Contrast(ImageOps.autocontrast(gray)).enhance(1.8)
            enhanced = ImageEnhance.Sharpness(enhanced).enhance(2.2)

            for variant_img in [scaled, enhanced]:
                temp_path = None
                try:
                    with tempfile.NamedTemporaryFile(
                        prefix="dialog_scan_", suffix=".png", delete=False
                    ) as handle:
                        temp_path = handle.name
                    variant_img.save(temp_path, format="PNG")
                    ocr_text = run_windows_ocr(
                        temp_path, timeout_seconds=FAST_SUMMARY_OCR_TIMEOUT_SECONDS
                    )
                except Exception as exc:
                    logger.debug("居中对话框扫描 OCR 失败: %s", exc)
                    ocr_text = ""
                finally:
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except OSError:
                            pass

                export_count = extract_export_summary_count_from_text(ocr_text)
                if export_count is not None:
                    logger.info(
                        "居中导出对话框扫描命中: count=%s, region=%s, text=%s",
                        export_count,
                        region,
                        normalize_ocr_text(ocr_text)[:120],
                    )
                    return export_count

        return None

    def _consume_export_button_click(
        self,
        capture_hwnd: int | None,
        button_bounds: tuple[int, int, int, int] | None,
    ) -> bool:
        """检测当前是否刚刚点击了黄色导出按钮。"""
        if not HAS_WIN32 or not capture_hwnd or not button_bounds:
            self._last_left_button_down = False
            return False

        try:
            left_button_down = bool(
                win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000
            )
            cursor_x, cursor_y = win32api.GetCursorPos()
            left, top, _, _ = win32gui.GetWindowRect(capture_hwnd)
        except Exception:
            self._last_left_button_down = False
            return False

        button_left = left + button_bounds[0]
        button_top = top + button_bounds[1]
        button_right = left + button_bounds[2]
        button_bottom = top + button_bounds[3]
        inside_button = (
            button_left <= cursor_x <= button_right
            and button_top <= cursor_y <= button_bottom
        )
        is_new_click = (
            left_button_down and not self._last_left_button_down and inside_button
        )
        self._last_left_button_down = left_button_down
        if is_new_click:
            logger.info(
                "检测到导出按钮点击: capture_hwnd=%s, cursor=(%s,%s), bounds=%s",
                capture_hwnd,
                cursor_x,
                cursor_y,
                button_bounds,
            )
        return is_new_click

    def _emit_export_button_pre_clicked(
        self,
        now: float,
        capture_hwnd: int | None,
        button_bounds: tuple[int, int, int, int] | None,
    ) -> None:
        """点击黄色导出按钮时先通知主线程弹等待遮罩。"""
        if (
            self._last_export_button_pre_signal_at
            and (now - self._last_export_button_pre_signal_at) < 6.0
        ):
            return
        self._last_export_button_pre_signal_at = now
        logger.info(
            "导出按钮点击预警已发出: capture_hwnd=%s, button_bounds=%s",
            capture_hwnd,
            button_bounds,
        )
        self.export_button_pre_clicked.emit()

    def get_runtime_snapshot(self) -> dict:
        """返回监控线程当前关键状态，便于异常日志和现场排查。"""
        return {
            "current_pid": self._current_pid,
            "main_hwnd": self._main_hwnd,
            "capture_hwnd": get_preferred_capture_hwnd(
                self._current_pid, self._main_hwnd, self._export_hwnd
            ),
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
            "post_payment_pending_since": self._post_payment_pending_since,
            "cached_export_count": self._cached_export_count,
            "cached_export_count_at": self._cached_export_count_at,
            "cached_export_count_pid": self._cached_export_count_pid,
            "export_page_context_active": self._export_page_context_active,
            "creative_transfer_context_active": self._creative_transfer_context_active,
            "creative_transfer_ignore_worker_until": self._creative_transfer_ignore_worker_until,
            "last_export_capture_hwnd": self._last_export_capture_hwnd,
            "last_export_capture_pid": self._last_export_capture_pid,
            "last_export_capture_dialog_mode": self._last_export_capture_dialog_mode,
            "last_centered_dialog_scan_at": self._last_centered_dialog_scan_at,
            "last_debug_export_bundle": self._last_debug_export_bundle,
        }

    def get_heartbeat_age(self) -> float:
        """返回距离上次心跳的秒数，用于主线程判断监控线程是否存活。"""
        if self._last_heartbeat == 0.0:
            return 0.0
        return time.monotonic() - self._last_heartbeat

    def run(self):
        """监控主循环"""
        if self._monitor_started_at is None:
            self._monitor_started_at = time.monotonic()
        while self._running:
            now = time.monotonic()
            self._last_heartbeat = now
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
                self._post_payment_pending_since = None
                self._reset_export_candidates()
                self._reset_export_count_cache()
                logger.info(
                    "检测到目标程序启动: PID=%s, main_hwnd=%s, existing_export_worker_pids=%s",
                    pid,
                    self._main_hwnd,
                    sorted(self._known_export_worker_pids),
                )
                self.process_started.emit()
            elif is_running and self._current_pid != pid:
                keep_post_payment_pending = self._post_payment_pending
                self._current_pid = pid
                self._main_hwnd = find_main_window(pid)
                self._known_export_worker_pids = find_export_worker_pids(pid)
                self._process_started_at = now
                self._startup_guard_logged = False
                if not keep_post_payment_pending:
                    self._post_payment_pending = False
                    self._post_payment_pending_since = None
                self._reset_export_candidates()
                self._reset_export_count_cache()
                logger.info(
                    "检测到目标程序实例变化，切换到 PID=%s, main_hwnd=%s, existing_export_worker_pids=%s",
                    pid,
                    self._main_hwnd,
                    sorted(self._known_export_worker_pids),
                )
                if keep_post_payment_pending:
                    logger.info(
                        "付款后等待导出结束期间检测到实例变化，保留同一次导出保护状态"
                    )
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
                self._post_payment_pending_since = None
                self._reset_export_candidates()
                self._reset_export_count_cache()
                self._suspended_pids = set()
                logger.info("目标程序已退出")
                self.process_stopped.emit()

            self._was_running = is_running

            # 检测导出行为（仅当进程运行时）
            if is_running and self._current_pid:
                self._main_hwnd = find_main_window(self._current_pid) or self._main_hwnd
                worker_pids = find_export_worker_pids(self._current_pid)
                new_worker_pids = get_new_export_worker_pids(
                    worker_pids, self._known_export_worker_pids
                )
                export_pid = min(new_worker_pids) if new_worker_pids else None
                export_hwnd = check_export_dialog(
                    self._current_pid, keywords, self._main_hwnd
                )
                capture_hwnd = get_preferred_capture_hwnd(
                    self._current_pid, self._main_hwnd, export_hwnd
                )
                monitor_warmup_active = (
                    self._monitor_started_at is not None
                    and (now - self._monitor_started_at) < MONITOR_VISUAL_WARMUP_SECONDS
                )
                should_skip_visual_probe = (
                    monitor_warmup_active
                    and export_hwnd is None
                    and export_pid is None
                    and not self._hold_export_state
                    and not self._post_payment_pending
                    and not self._was_exporting
                )
                # export_hwnd 已命中时跳过截图，直接走窗口信号触发路径，
                # 避免慢机器上截图耗时（50-200ms）延误冻结时机。
                should_skip_visual_probe = should_skip_visual_probe or (
                    export_hwnd is not None
                    and not self._hold_export_state
                    and not self._post_payment_pending
                    and not self._was_exporting
                )
                main_image = (
                    None
                    if should_skip_visual_probe
                    else capture_window_image(capture_hwnd)
                    if capture_hwnd
                    else None
                )
                export_button_bounds = (
                    locate_export_button_bounds(main_image) if main_image else None
                )
                export_visual_candidate = export_button_bounds is not None
                dialog_mode = bool(export_hwnd and export_hwnd != self._main_hwnd)
                summary_probe_count = None
                if (
                    export_visual_candidate
                    and main_image is not None
                    and not self._hold_export_state
                    and not self._post_payment_pending
                    and not self._was_exporting
                ):
                    summary_probe_count = self._probe_export_summary_count(
                        now,
                        main_image,
                        capture_hwnd=capture_hwnd,
                        dialog_mode=dialog_mode,
                        button_bounds=export_button_bounds,
                    )
                creative_transfer_layout = (
                    looks_like_creative_transfer_layout(main_image, export_button_bounds)
                    if export_visual_candidate and main_image is not None
                    else False
                )
                if creative_transfer_layout:
                    self._creative_transfer_context_active = True
                    self._creative_transfer_ignore_worker_until = now + 60.0  # 延长到60秒
                creative_transfer_worker_tail = (
                    export_pid is not None
                    and self._creative_transfer_ignore_worker_until > now
                    and summary_probe_count is None
                )
                # 创意上下文保护：只要在保护时间内，就应该跳过收费
                creative_transfer_context = (
                    summary_probe_count == CREATIVE_TRANSFER_SUMMARY_SENTINEL
                    or creative_transfer_layout
                    or creative_transfer_worker_tail
                    or (
                        self._creative_transfer_context_active
                        and self._creative_transfer_ignore_worker_until > now
                    )
                )
                if creative_transfer_context:
                    if (
                        export_visual_candidate
                        or summary_probe_count is not None
                        or export_pid is not None
                    ):
                        logger.info(
                            "当前为创意上下文保护中，跳过收费触发: capture_hwnd=%s, export_pid=%s, summary_probe=%s, button_bounds=%s",
                            capture_hwnd,
                            export_pid,
                            summary_probe_count,
                            export_button_bounds,
                        )
                    export_hwnd = None
                    export_pid = None
                    summary_probe_count = None
                    export_button_bounds = None
                    export_visual_candidate = False
                    self._last_left_button_down = False
                else:
                    # 只有在保护超时后才清除保护状态
                    if self._creative_transfer_ignore_worker_until <= now:
                        self._creative_transfer_context_active = False
                        self._creative_transfer_ignore_worker_until = 0.0
                self._export_page_context_active = False
                self._export_page_context_hwnd = capture_hwnd
                self._export_page_context_checked_at = now
                # 找到黄色按钮即视为视觉证据，不再强制要求 OCR 二次验证。
                export_visual = export_visual_candidate
                export_button_clicked = (
                    self._consume_export_button_click(
                        capture_hwnd, export_button_bounds
                    )
                    if export_visual or export_visual_candidate
                    else False
                )
                if (
                    export_button_clicked
                    and not self._was_exporting
                    and not self._hold_export_state
                    and not self._post_payment_pending
                    and not is_within_guard_window(
                        now, self._process_started_at, PROCESS_STARTUP_GUARD_SECONDS
                    )
                ):
                    self._emit_export_button_pre_clicked(
                        now, capture_hwnd, export_button_bounds
                    )
                if not export_visual:
                    self._last_left_button_down = False
                has_cached_export_count = self.get_recent_export_count(5.0) is not None
                pre_export_visual = (
                    summary_probe_count is not None
                    or export_visual
                    or export_button_clicked
                    or (export_visual_candidate and has_cached_export_count)
                )
                trigger_reasons = []
                if export_hwnd is not None:
                    trigger_reasons.append("export_hwnd")
                if export_pid is not None:
                    trigger_reasons.append("export_worker_pid")
                if summary_probe_count is not None:
                    trigger_reasons.append("summary_probe")
                if export_visual:
                    trigger_reasons.append("export_visual")
                if export_button_clicked:
                    trigger_reasons.append("export_button_clicked")
                trigger_reason = (
                    ",".join(trigger_reasons) if trigger_reasons else "unknown"
                )
                if (
                    not self._was_exporting
                    and not self._hold_export_state
                    and not self._post_payment_pending
                    and not is_within_guard_window(
                        now, self._process_started_at, PROCESS_STARTUP_GUARD_SECONDS
                    )
                    and (
                        export_hwnd is not None
                        or export_pid is not None
                        or summary_probe_count is not None
                        or export_visual
                        or export_button_clicked
                    )
                ):
                    self._export_clear_candidate_since = None
                    self._confirm_export_detected(
                        now,
                        main_image,
                        capture_hwnd,
                        export_hwnd,
                        export_pid,
                        pre_export_visual,
                        dialog_mode,
                        trigger_reason,
                    )
                    continue
                # 有强信号（窗口标题命中或黄色按钮出现）时跳过 OCR，
                # 直接进 _confirm_export_detected 立刻冻结目标进程，
                # 避免 OCR 耗时导致像素蛋糕在收费框弹出前完成导出。
                has_strong_signal = bool(export_hwnd or export_visual)
                should_refresh_export_count = all(
                    [
                        not self._hold_export_state,
                        not self._post_payment_pending,
                        not self._was_exporting,
                        not has_strong_signal,
                        main_image is not None,
                        (export_hwnd or export_visual_candidate),
                        summary_probe_count is None,
                    ]
                )
                if should_refresh_export_count:
                    self._refresh_export_count_cache(
                        now,
                        main_image,
                        dialog_mode=dialog_mode,
                        button_bounds=export_button_bounds,
                    )
                has_export_evidence = bool(
                    export_hwnd
                    or export_pid
                    or pre_export_visual
                    or export_button_clicked
                )
                centered_dialog_count = None
                if (
                    not has_export_evidence
                    and not creative_transfer_context
                    and self._centered_dialog_scan_enabled
                    and not self._was_exporting
                    and not self._hold_export_state
                    and not self._post_payment_pending
                    and main_image is not None
                ):
                    self._dump_export_debug_bundle(
                        now,
                        capture_hwnd,
                        main_image,
                        export_button_bounds,
                        reason="pre_export_probe",
                    )
                    centered_dialog_count = self._scan_for_centered_export_dialog(
                        now, main_image
                    )
                    if centered_dialog_count is not None:
                        self._remember_export_count(centered_dialog_count, now)
                        self._remember_export_capture(
                            main_image, now, capture_hwnd, dialog_mode=False
                        )
                        pre_export_visual = True
                        has_export_evidence = True
                        if "centered_dialog_scan" not in trigger_reasons:
                            trigger_reasons.append("centered_dialog_scan")
                        trigger_reason = ",".join(trigger_reasons)
                startup_guard_active = is_within_guard_window(
                    now, self._process_started_at, PROCESS_STARTUP_GUARD_SECONDS
                )
                self._log_detection_diagnostic(
                    now,
                    capture_hwnd,
                    export_hwnd,
                    export_pid,
                    main_image,
                    export_visual_candidate,
                    export_button_clicked,
                    summary_probe_count,
                    has_cached_export_count,
                    has_export_evidence,
                    startup_guard_active,
                    should_skip_visual_probe,
                    dialog_mode,
                    creative_transfer_context,
                    trigger_reason,
                )

                if (
                    self._post_payment_pending
                    and has_export_evidence
                    and not self._was_exporting
                ):
                    self._remember_export_capture(
                        main_image,
                        now,
                        capture_hwnd,
                        dialog_mode=dialog_mode,
                    )
                    self._export_hwnd = export_hwnd
                    self._export_pid = export_pid
                    self._was_exporting = True
                    self._export_clear_candidate_since = None
                    logger.info(
                        "付款后检测到同一次导出尾迹，继续等待导出结束: export_hwnd=%s, export_worker_pid=%s, trigger_reason=%s",
                        export_hwnd,
                        export_pid,
                        trigger_reason,
                    )
                    self._known_export_worker_pids = worker_pids
                    interval = min(
                        self._config.monitor_interval_ms, RUNNING_MONITOR_INTERVAL_MS
                    )
                    self.msleep(interval)
                    continue

                if has_export_evidence and not self._was_exporting:
                    self._export_clear_candidate_since = None
                    if startup_guard_active:
                        self._export_candidate_since = None
                        if not self._startup_guard_logged:
                            logger.info(
                                "启动保护生效，暂不触发收费: pid=%s, export_hwnd=%s, export_worker_pid=%s, export_visual=%s, trigger_reason=%s",
                                self._current_pid,
                                export_hwnd,
                                export_pid,
                                export_visual,
                                trigger_reason,
                            )
                            self._startup_guard_logged = True
                    else:
                        if (
                            is_strong_export_signal(
                                export_hwnd, export_pid, pre_export_visual
                            )
                            or export_button_clicked
                        ):
                            self._confirm_export_detected(
                                now,
                                main_image,
                                capture_hwnd,
                                export_hwnd,
                                export_pid,
                                pre_export_visual,
                                dialog_mode,
                                trigger_reason,
                            )
                        elif self._export_candidate_since is None:
                            self._export_candidate_since = now
                            logger.info(
                                "检测到导出候选，进入视觉防抖观察: pid=%s, export_hwnd=%s, export_worker_pid=%s, export_visual=%s, trigger_reason=%s",
                                self._current_pid,
                                export_hwnd,
                                export_pid,
                                export_visual,
                                trigger_reason,
                            )
                        elif is_debounce_satisfied(
                            self._export_candidate_since,
                            now,
                            EXPORT_VISUAL_DETECTION_DEBOUNCE_SECONDS,
                        ):
                            self._confirm_export_detected(
                                now,
                                main_image,
                                capture_hwnd,
                                export_hwnd,
                                export_pid,
                                pre_export_visual,
                                dialog_mode,
                                trigger_reason,
                            )
                elif not has_export_evidence and not self._was_exporting:
                    self._export_candidate_since = None
                    self._startup_guard_logged = False
                elif not has_export_evidence and self._was_exporting:
                    if self._hold_export_state:
                        interval = min(self._config.monitor_interval_ms, 500)
                        self.msleep(interval)
                        continue
                    if (
                        self._post_payment_pending
                        and self._post_payment_pending_since is not None
                        and (now - self._post_payment_pending_since)
                        < POST_PAYMENT_EXPORT_TAIL_GUARD_SECONDS
                    ):
                        self._export_clear_candidate_since = None
                        interval = min(
                            self._config.monitor_interval_ms,
                            RUNNING_MONITOR_INTERVAL_MS,
                        )
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
        # 当开始真正的导出流程时，清除创意上下文保护状态
        if hold:
            self._creative_transfer_context_active = False
            self._creative_transfer_ignore_worker_until = 0.0

    def assume_export_in_progress(
        self, reason: str = "", main_hwnd: int | None = None
    ):
        """外部快速触发路径已接管导出时，预先进入导出状态。"""
        if main_hwnd:
            try:
                pid = get_window_pid(main_hwnd)
            except Exception:
                pid = None
            if pid and pid != self._current_pid:
                self._current_pid = pid
                self._known_export_worker_pids = find_export_worker_pids(pid)
                self._reset_export_count_cache()
                self._reset_export_candidates()
            self._main_hwnd = main_hwnd
        self._was_exporting = True
        self._export_clear_candidate_since = None
        logger.info(
            "外部触发已标记导出进行中: reason=%s, main_hwnd=%s, pid=%s",
            reason,
            main_hwnd,
            self._current_pid,
        )

    def clear_export_count_cache(self, reason: str = ""):
        """清空导出张数和截图缓存，进入新的 PixCake 使用生命周期。"""
        self._reset_export_count_cache()
        logger.info("已清空导出张数缓存: reason=%s", reason)

    def snapshot_current_export_capture(self, reason: str = "") -> bool:
        """保存当前 PixCake 导出页截图，供挂起后后台 OCR 使用。"""
        if self._suspended_pids:
            logger.info("目标进程已挂起，跳过导出页截图快照: reason=%s", reason)
            return False
        capture_hwnd = get_preferred_capture_hwnd(
            self._current_pid, self._main_hwnd, self._export_hwnd
        )
        if not capture_hwnd:
            logger.info("无可截图窗口，跳过导出页截图快照: reason=%s", reason)
            return False
        image = capture_window_image(capture_hwnd)
        if image is None:
            logger.info(
                "导出页截图快照失败: reason=%s, pid=%s, hwnd=%s",
                reason,
                self._current_pid,
                capture_hwnd,
            )
            return False
        self._remember_export_capture(
            image,
            time.monotonic(),
            capture_hwnd,
            dialog_mode=self._current_dialog_mode(),
        )
        logger.info(
            "已保存当前生命周期导出页截图快照: reason=%s, pid=%s, hwnd=%s",
            reason,
            self._current_pid,
            capture_hwnd,
        )
        return True

    def set_post_payment_pending(self, active: bool):
        """标记当前是否仍在等待同一次已付款导出完全结束。"""
        if self._post_payment_pending != active:
            self._export_clear_candidate_since = None
        self._post_payment_pending = active
        self._post_payment_pending_since = time.monotonic() if active else None

    def get_recent_export_count(
        self, max_age_seconds: float = EXPORT_COUNT_CACHE_TTL_SECONDS
    ) -> int | None:
        """获取最近一次在导出页识别到的导出张数。"""
        if self._cached_export_count is None or self._cached_export_count_at is None:
            return None
        if self._cached_export_count_pid != self._current_pid:
            logger.info(
                "忽略上一生命周期的导出张数缓存: cached_pid=%s, current_pid=%s, count=%s",
                self._cached_export_count_pid,
                self._current_pid,
                self._cached_export_count,
            )
            return None
        if (time.monotonic() - self._cached_export_count_at) > max(
            max_age_seconds, 0.0
        ):
            return None
        return self._cached_export_count

    def get_last_export_capture_image(
        self, max_age_seconds: float = 5.0
    ) -> Image.Image | None:
        """获取最近一次触发导出前保存下来的那一帧截图。"""
        if (
            self._last_export_capture_image is None
            or self._last_export_capture_at is None
            or self._last_export_capture_pid != self._current_pid
            or (time.monotonic() - self._last_export_capture_at)
            > max(max_age_seconds, 0.0)
        ):
            return None
        return self._last_export_capture_image.copy()

    def get_last_export_capture_dialog_mode(self, max_age_seconds: float = 5.0) -> bool:
        """最近一次导出前截图是否来自导出对话框。"""
        if self._last_export_capture_at is None or (
            time.monotonic() - self._last_export_capture_at
        ) > max(max_age_seconds, 0.0):
            return False
        return self._last_export_capture_dialog_mode

    def _current_dialog_mode(self) -> bool:
        return bool(self._export_hwnd and self._export_hwnd != self._main_hwnd)

    def capture_main_window_image(self) -> Image.Image | None:
        """抓取当前像素蛋糕主窗口截图，用于后续离线 OCR。"""
        if self._suspended_pids:
            return self.get_last_export_capture_image(max_age_seconds=30.0)
        capture_hwnd = get_preferred_capture_hwnd(
            self._current_pid, self._main_hwnd, self._export_hwnd
        )
        if not capture_hwnd:
            return None
        return capture_window_image(capture_hwnd)

    def detect_export_summary_count_from_image(
        self, image: Image.Image | None, dialog_mode: bool | None = None
    ) -> int | None:
        """优先读取左上角摘要区里的导出张数。"""
        if dialog_mode is None:
            dialog_mode = self._current_dialog_mode()
        return detect_export_summary_count_from_image(image, dialog_mode=dialog_mode)

    def detect_export_summary_count(self) -> int | None:
        """读取当前导出页左上角摘要中的导出张数。"""
        return detect_export_summary_count_from_image(
            self.capture_main_window_image(),
            dialog_mode=self._current_dialog_mode(),
        )

    def detect_export_image_count_from_image(
        self, image: Image.Image | None, dialog_mode: bool | None = None
    ) -> int | None:
        """从给定截图中识别导出张数。"""
        if dialog_mode is None:
            dialog_mode = self._current_dialog_mode()
        return detect_export_image_count_from_image(image, dialog_mode=dialog_mode)

    def detect_export_image_count(self) -> int | None:
        """读取当前导出页中的导出张数。"""
        return detect_export_image_count_from_image(
            self.capture_main_window_image(),
            dialog_mode=self._current_dialog_mode(),
        )

    def suspend_target_processes(self) -> list[int]:
        """挂起像素蛋糕主进程及其子进程，阻止导出在付款前继续执行。"""
        if not self._current_pid:
            return []

        target_pids = get_process_family_pids(self._current_pid)
        pending_pids = set(target_pids) - set(self._suspended_pids)
        if not pending_pids:
            logger.info(
                "目标进程族已处于挂起状态，跳过重复挂起: %s",
                sorted(self._suspended_pids),
            )
            return sorted(self._suspended_pids)

        suspended = suspend_processes(pending_pids)
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

    def restore_target_interaction(self) -> dict:
        """恢复付款后/取消后的目标程序交互状态，并尽量把主窗口拉回前台。"""
        try:
            resumed = self.resume_target_processes()

            selected_pid = find_pid_by_name(self._config.process_name)
            if selected_pid and selected_pid != self._current_pid:
                self._current_pid = selected_pid
                self._main_hwnd = find_main_window(selected_pid) or self._main_hwnd
                self._reset_export_count_cache()
                self._reset_export_candidates()
                logger.info(
                    "恢复交互时重新选择主实例: process_name=%s, current_pid=%s, main_hwnd=%s",
                    self._config.process_name,
                    self._current_pid,
                    self._main_hwnd,
                )
            elif selected_pid and not self._main_hwnd:
                self._main_hwnd = find_main_window(selected_pid) or self._main_hwnd

            restored = recover_process_windows(
                self._config.process_name, hwnds=self.lock_target_hwnds
            )
            target_hwnd = self._main_hwnd
            if not target_hwnd and self._current_pid:
                target_hwnd = find_main_window(self._current_pid)
                self._main_hwnd = target_hwnd or self._main_hwnd

            activated = activate_window(target_hwnd)
            result = {
                "resumed": resumed,
                "restored": restored,
                "activated": activated,
                "target_hwnd": target_hwnd,
                "current_pid": self._current_pid,
            }
            logger.info("目标交互恢复结果: %s", result)
            return result
        except Exception:
            logger.exception("恢复目标交互失败")
            return {
                "resumed": [],
                "restored": [],
                "activated": False,
                "target_hwnd": self._main_hwnd,
                "current_pid": self._current_pid,
                "error": True,
            }

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
