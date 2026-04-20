"""
进程监控模块测试
测试进程检测、窗口查找、导出检测、窗口锁定等功能
"""

import os
import sys
import time
import tempfile
import subprocess
import unittest
from unittest import mock
from PIL import Image, ImageDraw

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import win32gui
    import win32process

    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    print("⚠ pywin32未安装，跳过部分窗口测试")


class TestProcessMonitor(unittest.TestCase):
    """测试进程监控功能"""

    def setUp(self):
        """测试前准备"""
        from process_monitor import (
            is_process_running,
            find_pid_by_name,
            find_windows_by_pid,
            find_main_window,
            check_export_dialog,
            disable_window,
            enable_window,
            recover_process_windows,
        )

        self.is_process_running = is_process_running
        self.find_pid_by_name = find_pid_by_name
        self.find_windows_by_pid = find_windows_by_pid
        self.find_main_window = find_main_window
        self.check_export_dialog = check_export_dialog
        self.disable_window = disable_window
        self.enable_window = enable_window
        self.recover_process_windows = recover_process_windows

        # 测试进程
        self.test_process_name = "notepad.exe"
        self.test_process = None

    def tearDown(self):
        """测试后清理"""
        # 确保测试进程被终止
        if self.test_process:
            try:
                self.test_process.terminate()
                self.test_process.wait(timeout=2)
            except:
                pass

    def start_test_process(self):
        """启动测试进程"""
        if self.test_process is None or self.test_process.poll() is not None:
            self.test_process = subprocess.Popen([self.test_process_name])
            time.sleep(2)  # 等待进程启动
        return self.test_process

    def test_process_detection(self):
        """测试进程检测"""
        # 确保记事本未运行
        if self.is_process_running(self.test_process_name):
            print(f"⚠ {self.test_process_name}已在运行，跳过启动测试")
            pid = self.find_pid_by_name(self.test_process_name)
            self.assertIsNotNone(pid)
            print("✓ 进程检测测试通过（使用已运行进程）")
            return

        # 启动测试进程
        self.start_test_process()

        # 测试进程检测
        self.assertTrue(self.is_process_running(self.test_process_name))

        # 测试PID查找
        pid = self.find_pid_by_name(self.test_process_name)
        self.assertIsNotNone(pid)
        self.assertGreater(pid, 0)

        print("✓ 进程检测测试通过")

    @unittest.skipIf(not HAS_WIN32, "需要pywin32进行窗口测试")
    def test_window_detection(self):
        """测试窗口查找"""
        self.start_test_process()

        pid = self.find_pid_by_name(self.test_process_name)
        self.assertIsNotNone(pid, "未找到进程PID")

        # 测试窗口查找
        windows = self.find_windows_by_pid(pid)
        self.assertIsInstance(windows, list)

        if windows:
            # 测试主窗口查找
            main_hwnd = self.find_main_window(pid)
            self.assertIsNotNone(main_hwnd)
            self.assertIn(main_hwnd, windows)

            # 测试窗口属性
            try:
                title = win32gui.GetWindowText(main_hwnd)
                self.assertIsInstance(title, str)
                print(f"  找到窗口: hwnd={main_hwnd}, title='{title}'")
            except Exception as e:
                print(f"  获取窗口标题失败: {e}")

        print("✓ 窗口查找测试通过")

    @unittest.skipIf(not HAS_WIN32, "需要pywin32进行窗口测试")
    def test_export_dialog_detection(self):
        """测试导出窗口检测"""
        self.start_test_process()

        pid = self.find_pid_by_name(self.test_process_name)
        self.assertIsNotNone(pid)

        # 测试关键词匹配
        keywords = ["导出", "Export", "Save", "另存为"]

        # 查找包含关键词的窗口
        export_hwnd = self.check_export_dialog(pid, keywords)

        # 注意：记事本可能没有导出窗口，所以结果可能为None
        # 这里主要测试函数不崩溃
        if export_hwnd:
            print(f"  找到导出窗口: hwnd={export_hwnd}")

        print("✓ 导出窗口检测测试通过")

    @unittest.skipIf(not HAS_WIN32, "需要pywin32进行窗口锁定测试")
    def test_window_lock_unlock(self):
        """测试窗口锁定和解锁"""
        self.start_test_process()

        pid = self.find_pid_by_name(self.test_process_name)
        self.assertIsNotNone(pid)

        main_hwnd = self.find_main_window(pid)
        if not main_hwnd:
            self.skipTest("未找到主窗口，跳过锁定测试")

        # 测试禁用窗口
        disable_result = self.disable_window(main_hwnd)
        self.assertTrue(disable_result, "窗口禁用失败")

        # 验证窗口被禁用
        try:
            enabled = win32gui.IsWindowEnabled(main_hwnd)
            self.assertFalse(enabled, "窗口应被禁用")
            print("  窗口已禁用")
        except Exception as e:
            print(f"  验证窗口状态失败: {e}")

        # 等待一下
        time.sleep(1)

        # 测试启用窗口
        enable_result = self.enable_window(main_hwnd)
        self.assertTrue(enable_result, "窗口启用失败")

        # 验证窗口被启用
        try:
            enabled = win32gui.IsWindowEnabled(main_hwnd)
            self.assertTrue(enabled, "窗口应被启用")
            print("  窗口已启用")
        except Exception as e:
            print(f"  验证窗口状态失败: {e}")

        print("✓ 窗口锁定/解锁测试通过")

    def test_nonexistent_process(self):
        """测试不存在的进程"""
        nonexistent_name = "ThisProcessDoesNotExist12345.exe"

        # 测试进程检测
        self.assertFalse(self.is_process_running(nonexistent_name))

        # 测试PID查找
        pid = self.find_pid_by_name(nonexistent_name)
        self.assertIsNone(pid)

        print("✓ 不存在进程测试通过")

    @unittest.skipIf(not HAS_WIN32, "需要pywin32进行无效窗口测试")
    def test_invalid_window_handle(self):
        """测试无效窗口句柄"""
        invalid_hwnd = 0  # 无效句柄

        # 测试禁用无效窗口
        disable_result = self.disable_window(invalid_hwnd)
        self.assertFalse(disable_result, "禁用无效窗口应失败")

        # 测试启用无效窗口
        enable_result = self.enable_window(invalid_hwnd)
        self.assertFalse(enable_result, "启用无效窗口应失败")

        print("✓ 无效窗口句柄测试通过")

    def test_recover_process_windows_uses_known_handles(self):
        """即使进程查找不到，也应解锁显式传入的窗口句柄。"""
        with mock.patch("process_monitor.find_pid_by_name", return_value=None), \
             mock.patch("process_monitor.enable_window", side_effect=lambda hwnd: hwnd != 0) as mock_enable:
            restored = self.recover_process_windows("pixcake.exe", hwnds=[101, 0, 202, 101])

        self.assertEqual(restored, [101, 202])
        self.assertEqual(mock_enable.call_count, 2)

    def test_get_new_export_worker_pids_ignores_existing_workers(self):
        """启动前已存在的 export worker 不应被当成新导出。"""
        from process_monitor import get_new_export_worker_pids

        self.assertEqual(get_new_export_worker_pids({39552}, {39552}), set())
        self.assertEqual(get_new_export_worker_pids({39552, 42000}, {39552}), {42000})

    def test_startup_guard_window(self):
        """启动保护时间窗内应返回 True，超时后应返回 False。"""
        from process_monitor import is_within_guard_window

        self.assertTrue(is_within_guard_window(12.0, 10.0, 3.0))
        self.assertFalse(is_within_guard_window(14.5, 10.0, 3.0))
        self.assertFalse(is_within_guard_window(12.0, None, 3.0))

    def test_debounce_helper(self):
        """防抖辅助函数应正确判断持续时间是否达标。"""
        from process_monitor import is_debounce_satisfied

        self.assertFalse(is_debounce_satisfied(None, 10.0, 0.8))
        self.assertFalse(is_debounce_satisfied(10.0, 10.5, 0.8))
        self.assertTrue(is_debounce_satisfied(10.0, 10.8, 0.8))

    def test_strong_export_signal_helper(self):
        """新导出 worker 或标题命中窗口都应视为强信号。"""
        from process_monitor import is_strong_export_signal

        self.assertTrue(is_strong_export_signal(None, 39340))
        self.assertTrue(is_strong_export_signal(12345, None))
        self.assertTrue(is_strong_export_signal(None, None, True))
        self.assertFalse(is_strong_export_signal(None, None))

    def test_extract_export_image_count_from_text(self):
        """OCR 文本中应能提取导出张数。"""
        from process_monitor import (
            contains_export_page_context,
            contains_export_button_text,
            extract_export_count_from_variant_text,
            extract_export_image_count_from_text,
            extract_export_summary_count_from_text,
            normalize_ocr_text,
        )

        self.assertEqual(
            extract_export_image_count_from_text("快 速 导 出\n导 出 12 张 图 片"),
            12,
        )
        self.assertEqual(
            extract_export_image_count_from_text("精 修 效 果 图 （ 2 ） 免费 效 果 图 （ 1 ） 原 图 （ 0 ）"),
            3,
        )
        self.assertTrue(contains_export_page_context("快速导出 导出至 指定文件夹"))
        self.assertTrue(contains_export_button_text("导 出"))
        self.assertFalse(contains_export_button_text("导 入"))
        self.assertEqual(extract_export_image_count_from_text("快速导出 2"), 2)
        self.assertEqual(
            extract_export_summary_count_from_text("导出2张图片，其中1张是未编辑图片"),
            2,
        )
        self.assertEqual(
            extract_export_summary_count_from_text("2图片效图2效图0原图0"),
            2,
        )
        self.assertEqual(
            extract_export_summary_count_from_text("H2图片效图2效图0"),
            2,
        )
        self.assertEqual(
            extract_export_summary_count_from_text("2ͼƬЧͼ2Чͼ0ԭͼ0"),
            2,
        )
        self.assertEqual(
            extract_export_summary_count_from_text("H2ͼƬЧͼ2Чͼ0"),
            2,
        )
        self.assertIsNone(extract_export_summary_count_from_text("2选图前图"))
        self.assertIsNone(
            extract_export_summary_count_from_text("2选图原图01模支图片原始前图图22原图3图0")
        )
        self.assertIsNone(
            extract_export_summary_count_from_text("2ѡͼԭͼ01ģ֧ͼƬԭʼǰͼͼ22ԭͼ3ͼ0")
        )
        self.assertEqual(
            normalize_ocr_text("2ѡͼԭͼ01ģ֧ͼƬԭʼǰͼͼ22ԭͼ3ͼȡФ"),
            "2选图原图01模支图片原始当前图22原图3图取消",
        )
        self.assertFalse(
            contains_export_page_context("2ѡͼԭͼ01ģ֧ͼƬԭʼǰͼͼ22ԭͼ3ͼȡФ")
        )
        self.assertIsNone(extract_export_image_count_from_text("42"))
        self.assertEqual(
            extract_export_count_from_variant_text("summary-rgb2x", "µј іц 2 ХЕ Нј Ж¬"),
            2,
        )
        self.assertIsNone(
            extract_export_count_from_variant_text(
                "summary-rgb2x", "O0一00user100027042026/4/201832牛"
            )
        )
        self.assertIsNone(
            extract_export_count_from_variant_text(
                "summary_wide-rgb2x", "0|077抓Free液Free图FreeFree图New一预O效"
            )
        )
        self.assertEqual(
            extract_export_count_from_variant_text(
                "type_counts-rgb2x", "精修效果图(1) 免费效果图(1) 原图(0)"
            ),
            2,
        )
        self.assertIsNone(
            extract_export_count_from_variant_text(
                "type_counts-rgb2x", "1图片1未图片"
            )
        )
        self.assertIsNone(extract_export_image_count_from_text("未检测到导出数量"))

    def test_window_matches_keywords_only_uses_title(self):
        """Qt SaveBits 这类类名命中不应再被误判为导出窗口。"""
        from process_monitor import window_matches_keywords

        with mock.patch("process_monitor.get_window_title", return_value=""), \
             mock.patch("process_monitor.get_window_class", return_value="Qt5152QWindowToolTipSaveBits"):
            self.assertFalse(window_matches_keywords(12345, ["save"]))

    def test_window_matches_keywords_ignores_delete_progress_confirmation(self):
        """删除导出进度确认框不应再被识别成收费触发窗口。"""
        from process_monitor import window_matches_keywords

        with mock.patch(
            "process_monitor.get_window_title", return_value="确认删除该导出进度"
        ):
            self.assertFalse(window_matches_keywords(12345, ["导出", "export"]))

    def test_check_export_dialog_ignores_non_family_keyword_window(self):
        """文件资源管理器等非目标进程家族窗口即使标题带导出，也不应被当成导出框。"""
        with mock.patch("process_monitor.HAS_WIN32", True), \
             mock.patch("process_monitor.get_process_family_pids", return_value={100}), \
             mock.patch("process_monitor.find_windows_by_pids", return_value=[]), \
             mock.patch("process_monitor.enumerate_visible_windows", return_value=[200]), \
             mock.patch("process_monitor.get_window_owner_hwnd", return_value=None), \
             mock.patch("process_monitor.get_window_pid", side_effect=lambda hwnd: {200: 31376}.get(hwnd)), \
             mock.patch("process_monitor.window_matches_keywords", return_value=True), \
             mock.patch("process_monitor.win32gui.GetForegroundWindow", return_value=0):
            export_hwnd = self.check_export_dialog(100, ["导出"])

        self.assertIsNone(export_hwnd)

    def test_suspend_and_resume_process_helpers(self):
        """挂起/恢复进程辅助函数应返回成功处理的 PID。"""
        from process_monitor import suspend_processes, resume_processes

        class FakeProcess:
            def __init__(self, pid):
                self.pid = pid

            def suspend(self):
                return None

            def resume(self):
                return None

        with mock.patch("process_monitor.psutil.Process", side_effect=lambda pid: FakeProcess(pid)):
            self.assertEqual(suspend_processes({3, 1, 2}), [3, 2, 1])
            self.assertEqual(resume_processes({3, 1, 2}), [1, 2, 3])

    def test_monitor_consumes_export_button_click_inside_bounds(self):
        """只有点击黄色导出按钮区域时，才应视为导出操作。"""
        from process_monitor import ProcessMonitor
        from config_manager import ConfigManager

        monitor = ProcessMonitor(ConfigManager())
        button_bounds = (600, 500, 760, 580)

        with mock.patch("process_monitor.HAS_WIN32", True), \
             mock.patch("process_monitor.win32api.GetAsyncKeyState", return_value=0x8000), \
             mock.patch("process_monitor.win32api.GetCursorPos", return_value=(750, 650)), \
             mock.patch("process_monitor.win32gui.GetWindowRect", return_value=(100, 100, 1100, 900)):
            self.assertTrue(monitor._consume_export_button_click(200, button_bounds))

        with mock.patch("process_monitor.HAS_WIN32", True), \
             mock.patch("process_monitor.win32api.GetAsyncKeyState", return_value=0x8000), \
             mock.patch("process_monitor.win32api.GetCursorPos", return_value=(300, 300)), \
             mock.patch("process_monitor.win32gui.GetWindowRect", return_value=(100, 100, 1100, 900)):
            self.assertFalse(monitor._consume_export_button_click(200, button_bounds))

    def test_get_preferred_capture_hwnd_prefers_foreground_family_window(self):
        """截图应优先抓取当前前台的像素蛋糕进程家族窗口。"""
        from process_monitor import get_preferred_capture_hwnd

        with mock.patch("process_monitor.HAS_WIN32", True), \
             mock.patch("process_monitor.get_process_family_pids", return_value={100, 101}), \
             mock.patch("process_monitor.win32gui.GetForegroundWindow", return_value=300), \
             mock.patch("process_monitor.get_window_pid", side_effect=lambda hwnd: {300: 101}.get(hwnd)), \
             mock.patch("process_monitor.win32gui.IsWindow", return_value=True):
            self.assertEqual(get_preferred_capture_hwnd(100, 200), 300)

    def test_get_preferred_capture_hwnd_prefers_export_dialog(self):
        """导出对话框存在时，应优先抓取导出对话框而不是主窗口。"""
        from process_monitor import get_preferred_capture_hwnd

        with mock.patch("process_monitor.HAS_WIN32", True), \
             mock.patch("process_monitor.get_process_family_pids", return_value={100}), \
             mock.patch("process_monitor.win32gui.GetForegroundWindow", return_value=0), \
             mock.patch("process_monitor.win32gui.IsWindow", side_effect=lambda hwnd: hwnd == 400), \
             mock.patch("process_monitor.get_window_pid", return_value=100):
            self.assertEqual(get_preferred_capture_hwnd(100, 200, 400), 400)

    def test_capture_window_image_prefers_printwindow(self):
        """只要 PrintWindow 能抓到窗口内容，就不应再依赖屏幕截图。"""
        from process_monitor import capture_window_image

        fake_image = Image.new("RGB", (960, 808), (45, 47, 52))
        with mock.patch("process_monitor.HAS_WIN32", True), \
             mock.patch("process_monitor.win32gui.IsWindow", return_value=True), \
             mock.patch("process_monitor.win32gui.GetWindowRect", return_value=(0, 0, 960, 808)), \
             mock.patch("process_monitor._capture_window_image_printwindow", return_value=fake_image), \
             mock.patch("process_monitor.ImageGrab.grab") as mock_grab:
            captured = capture_window_image(12345)

        self.assertIs(captured, fake_image)
        mock_grab.assert_not_called()

    def test_capture_window_image_falls_back_to_imagegrab(self):
        """PrintWindow 失败时，仍应回退到原来的屏幕截图路径。"""
        from process_monitor import capture_window_image

        fake_image = Image.new("RGB", (960, 808), (45, 47, 52))
        with mock.patch("process_monitor.HAS_WIN32", True), \
             mock.patch("process_monitor.HAS_IMAGE_GRAB", True), \
             mock.patch("process_monitor.win32gui.IsWindow", return_value=True), \
             mock.patch("process_monitor.win32gui.GetWindowRect", return_value=(0, 0, 960, 808)), \
             mock.patch("process_monitor._capture_window_image_printwindow", return_value=None), \
             mock.patch("process_monitor.ImageGrab.grab", return_value=fake_image) as mock_grab:
            captured = capture_window_image(12345)

        self.assertIs(captured, fake_image)
        mock_grab.assert_called_once()

    def test_prepare_export_variants_include_centered_summary_regions(self):
        """普通导出页不是全屏时，也应准备居中小面板的摘要裁剪区域。"""
        from process_monitor import _prepare_export_count_ocr_variants

        fake_image = Image.new("RGB", (1200, 800), (45, 47, 52))
        labels = [label for label, _ in _prepare_export_count_ocr_variants(fake_image)]

        self.assertIn("summary_popup_title-rgb2x", labels)
        self.assertIn("summary_popup_title_wide-rgb2x", labels)
        self.assertIn("summary_center-rgb2x", labels)
        self.assertIn("summary_wide_center-rgb2x", labels)

    def test_prepare_export_variants_include_button_anchored_summary_regions(self):
        """识别到黄色导出按钮后，应额外生成按钮锚定的摘要裁剪区域。"""
        from process_monitor import _prepare_export_count_ocr_variants

        fake_image = Image.new("RGB", (1200, 800), (45, 47, 52))
        labels = [
            label
            for label, _ in _prepare_export_count_ocr_variants(
                fake_image, button_bounds=(820, 690, 980, 760)
            )
        ]

        self.assertIn("summary_anchor-rgb2x", labels)
        self.assertIn("summary_anchor_wide-rgb2x", labels)


class TestProcessMonitorThread(unittest.TestCase):
    """测试进程监控线程"""

    @classmethod
    def setUpClass(cls):
        """类级别设置"""
        from PyQt5.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_monitor_thread_creation(self):
        """测试监控线程创建"""
        from process_monitor import ProcessMonitor
        from config_manager import ConfigManager

        # 创建配置
        config = ConfigManager()

        # 创建监控线程
        monitor = ProcessMonitor(config)

        # 测试线程属性
        self.assertFalse(monitor.isRunning())
        self.assertIsNone(monitor.current_pid)
        self.assertIsNone(monitor.main_hwnd)
        self.assertFalse(monitor.is_process_running)

        print("✓ 监控线程创建测试通过")

    def test_post_payment_clear_debounce_switch(self):
        """付款确认后应切换到更长的导出结束判定窗口。"""
        from process_monitor import (
            EXPORT_CLEAR_DEBOUNCE_SECONDS,
            POST_PAYMENT_EXPORT_CLEAR_DEBOUNCE_SECONDS,
            ProcessMonitor,
        )
        from config_manager import ConfigManager

        monitor = ProcessMonitor(ConfigManager())

        self.assertEqual(monitor._get_export_clear_debounce_seconds(), EXPORT_CLEAR_DEBOUNCE_SECONDS)

        monitor._export_clear_candidate_since = 1.0
        monitor.set_post_payment_pending(True)
        self.assertTrue(monitor.get_runtime_snapshot()["post_payment_pending"])
        self.assertIsNone(monitor._export_clear_candidate_since)
        self.assertEqual(
            monitor._get_export_clear_debounce_seconds(),
            POST_PAYMENT_EXPORT_CLEAR_DEBOUNCE_SECONDS,
        )

        monitor.set_post_payment_pending(False)
        self.assertEqual(monitor._get_export_clear_debounce_seconds(), EXPORT_CLEAR_DEBOUNCE_SECONDS)

    def test_recent_export_count_cache(self):
        """导出页缓存张数应在有效期内可复用。"""
        from process_monitor import ProcessMonitor
        from config_manager import ConfigManager

        monitor = ProcessMonitor(ConfigManager())
        monitor._remember_export_count(6, observed_at=100.0)

        with mock.patch("process_monitor.time.monotonic", return_value=105.0):
            self.assertEqual(monitor.get_recent_export_count(max_age_seconds=10.0), 6)

        with mock.patch("process_monitor.time.monotonic", return_value=140.0):
            self.assertIsNone(monitor.get_recent_export_count(max_age_seconds=10.0))

    def test_refresh_export_count_cache_uses_cache_mode_ocr(self):
        """导出页预缓存应走轻量 OCR，并在命中后写入缓存。"""
        from process_monitor import ProcessMonitor
        from config_manager import ConfigManager

        monitor = ProcessMonitor(ConfigManager())
        monitor._debug_export_capture_enabled = True
        fake_image = Image.new("RGB", (960, 800), (45, 47, 52))

        with mock.patch(
            "process_monitor.detect_export_image_count_from_image", return_value=2
        ) as mock_detect:
            detected = monitor._refresh_export_count_cache(10.0, fake_image)

        self.assertEqual(detected, 2)
        mock_detect.assert_called_once_with(
            fake_image,
            cache_mode=True,
            explicit_only=True,
            dialog_mode=False,
            button_bounds=None,
        )
        self.assertEqual(monitor._cached_export_count, 2)
        self.assertEqual(monitor._cached_export_count_at, 10.0)

    def test_refresh_export_count_cache_supports_dialog_mode(self):
        """本地导出对话框预缓存时，应切到对话框版裁剪区域。"""
        from process_monitor import ProcessMonitor
        from config_manager import ConfigManager

        monitor = ProcessMonitor(ConfigManager())
        monitor._debug_export_capture_enabled = True
        fake_image = Image.new("RGB", (960, 800), (45, 47, 52))

        with mock.patch(
            "process_monitor.detect_export_image_count_from_image", return_value=1
        ) as mock_detect:
            detected = monitor._refresh_export_count_cache(
                10.0, fake_image, dialog_mode=True
            )

        self.assertEqual(detected, 1)
        mock_detect.assert_called_once_with(
            fake_image,
            cache_mode=True,
            explicit_only=True,
            dialog_mode=True,
            button_bounds=None,
        )

    def test_refresh_export_page_context_requires_export_button_text(self):
        """即使页面 OCR 命中，上下文也必须配合“导出”按钮文字才算导出页。"""
        from process_monitor import ProcessMonitor
        from config_manager import ConfigManager

        monitor = ProcessMonitor(ConfigManager())
        monitor._debug_export_capture_enabled = True
        fake_image = Image.new("RGB", (960, 800), (45, 47, 52))

        with mock.patch(
            "process_monitor.detect_export_page_context_from_image", return_value=True
        ), mock.patch(
            "process_monitor.detect_export_button_text_from_image", return_value=False
        ):
            self.assertFalse(
                monitor._refresh_export_page_context(
                    10.0, 12345, fake_image, (700, 700, 900, 780)
                )
            )

    def test_dump_export_debug_bundle_saves_artifacts(self):
        """导出调试包应落盘主截图、OCR 结果和元数据，方便现场排查。"""
        from process_monitor import ProcessMonitor
        from config_manager import ConfigManager

        monitor = ProcessMonitor(ConfigManager())
        monitor._debug_export_capture_enabled = True
        fake_image = Image.new("RGB", (960, 800), (45, 47, 52))

        with tempfile.TemporaryDirectory() as temp_dir:
            monitor._debug_export_dir = temp_dir
            with mock.patch(
                "process_monitor.run_windows_ocr_on_image",
                side_effect=lambda *args, **kwargs: "导出2张图片",
            ):
                bundle_dir = monitor._dump_export_debug_bundle(
                    10.0,
                    12345,
                    fake_image,
                    (700, 650, 860, 730),
                    "unit_test",
                )

            self.assertIsNotNone(bundle_dir)
            self.assertTrue(os.path.isdir(bundle_dir))
            self.assertTrue(os.path.exists(os.path.join(bundle_dir, "00_main.png")))
            self.assertTrue(os.path.exists(os.path.join(bundle_dir, "meta.json")))
            self.assertTrue(os.path.exists(os.path.join(bundle_dir, "ocr_results.json")))

    def test_dump_export_debug_bundle_is_throttled(self):
        """导出调试包应节流，避免监控循环频繁写满磁盘。"""
        from process_monitor import ProcessMonitor
        from config_manager import ConfigManager

        monitor = ProcessMonitor(ConfigManager())
        monitor._debug_export_capture_enabled = True
        fake_image = Image.new("RGB", (960, 800), (45, 47, 52))

        with tempfile.TemporaryDirectory() as temp_dir:
            monitor._debug_export_dir = temp_dir
            with mock.patch(
                "process_monitor.run_windows_ocr_on_image",
                return_value="导出1张图片",
            ):
                first_bundle = monitor._dump_export_debug_bundle(
                    10.0,
                    12345,
                    fake_image,
                    None,
                    "throttle_probe",
                )
                second_bundle = monitor._dump_export_debug_bundle(
                    12.0,
                    12345,
                    fake_image,
                    None,
                    "throttle_probe",
                )

        self.assertIsNotNone(first_bundle)
        self.assertIsNone(second_bundle)

    def test_cleanup_debug_export_artifacts_when_disabled(self):
        """默认关闭调试时，应清理残留的导出调试包目录。"""
        from process_monitor import ProcessMonitor
        from config_manager import ConfigManager

        monitor = ProcessMonitor(ConfigManager())

        with tempfile.TemporaryDirectory() as temp_dir:
            old_bundle = os.path.join(temp_dir, "20260421_000000_001_pre_export_probe")
            os.makedirs(old_bundle, exist_ok=True)
            with open(os.path.join(old_bundle, "00_main.png"), "wb") as handle:
                handle.write(b"debug")

            monitor._debug_export_capture_enabled = False
            monitor._debug_export_dir = temp_dir
            monitor._cleanup_debug_export_artifacts_if_disabled()

            self.assertFalse(os.path.exists(old_bundle))

    def test_probe_export_summary_count_remembers_count(self):
        """摘要预判命中后，应立刻写入最近导出张数缓存。"""
        from process_monitor import ProcessMonitor
        from config_manager import ConfigManager

        monitor = ProcessMonitor(ConfigManager())
        monitor._debug_export_capture_enabled = True
        fake_image = Image.new("RGB", (960, 800), (45, 47, 52))

        with mock.patch(
            "process_monitor.detect_export_summary_count_from_image", return_value=2
        ):
            detected = monitor._probe_export_summary_count(
                10.0,
                fake_image,
                dialog_mode=False,
                button_bounds=(700, 650, 860, 730),
            )

        self.assertEqual(detected, 2)
        self.assertEqual(monitor._cached_export_count, 2)
        self.assertEqual(monitor._cached_export_count_at, 10.0)

    def test_monitor_confirms_immediately_when_summary_probe_hits(self):
        """摘要快速命中后，应直接确认导出，不再等待后续慢 OCR。"""
        from process_monitor import ProcessMonitor
        from config_manager import ConfigManager

        monitor = ProcessMonitor(ConfigManager())
        fake_image = Image.new("RGB", (960, 800), (45, 47, 52))
        signal_hits = []
        monitor.export_detected.connect(lambda: signal_hits.append("hit"))

        with mock.patch.object(monitor, "_remember_export_capture") as mock_capture:
            monitor._confirm_export_detected(
                10.0,
                fake_image,
                12345,
                None,
                None,
                True,
                False,
            )

        mock_capture.assert_called_once()
        self.assertTrue(monitor._was_exporting)
        self.assertEqual(signal_hits, ["hit"])

    def test_probe_export_summary_count_is_throttled(self):
        """摘要预判应节流，避免每轮监控都重复 OCR。"""
        from process_monitor import ProcessMonitor
        from config_manager import ConfigManager

        monitor = ProcessMonitor(ConfigManager())
        fake_image = Image.new("RGB", (960, 800), (45, 47, 52))

        with mock.patch(
            "process_monitor.detect_export_summary_count_from_image", return_value=2
        ) as mock_detect:
            first = monitor._probe_export_summary_count(
                10.0,
                fake_image,
                dialog_mode=False,
                button_bounds=(700, 650, 860, 730),
            )
            second = monitor._probe_export_summary_count(
                10.2,
                fake_image,
                dialog_mode=False,
                button_bounds=(700, 650, 860, 730),
            )

        self.assertEqual(first, 2)
        self.assertIsNone(second)
        self.assertEqual(mock_detect.call_count, 1)

    def test_detect_export_image_count_requires_multi_variant_consensus_for_fallback(self):
        """单个宽区域脏读数字不应直接被当成导出张数。"""
        from process_monitor import detect_export_image_count_from_image

        fake_image = Image.new("RGB", (960, 800), (45, 47, 52))
        fake_variants = [
            ("summary-rgb2x", fake_image),
            ("summary-gray2x", fake_image),
            ("summary_wide-rgb2x", fake_image),
        ]
        ocr_side_effect = [
            "3图片",
            "3张图片",
            "0|077抓Free液Free图FreeFree图New一预O效",
        ]

        with mock.patch(
            "process_monitor._prepare_export_count_ocr_variants",
            return_value=fake_variants,
        ), mock.patch(
            "process_monitor.run_windows_ocr", side_effect=ocr_side_effect
        ):
            self.assertEqual(detect_export_image_count_from_image(fake_image), 3)

    def test_detect_export_image_count_dialog_mode_omits_type_counts_noise(self):
        """本地导出对话框识别时，不应再吃到下方路径/表单区域的噪声。"""
        from process_monitor import detect_export_image_count_from_image

        fake_image = Image.new("RGB", (960, 800), (45, 47, 52))
        fake_variants = [
            ("summary-rgb2x", fake_image),
            ("summary-gray2x", fake_image),
        ]
        ocr_side_effect = [
            "导出 2 张图片，其中 1 张是未编辑图片",
            "导出 2 张图片",
        ]

        with mock.patch(
            "process_monitor._prepare_export_count_ocr_variants",
            return_value=fake_variants,
        ), mock.patch(
            "process_monitor.run_windows_ocr", side_effect=ocr_side_effect
        ):
            self.assertEqual(
                detect_export_image_count_from_image(fake_image, dialog_mode=True), 2
            )

    def test_detect_export_summary_count_from_image_prefers_left_top_summary(self):
        """只要左上角摘要能读到张数，就应直接采用它。"""
        from process_monitor import detect_export_summary_count_from_image

        fake_image = Image.new("RGB", (960, 800), (45, 47, 52))
        fake_variants = [
            ("summary-rgb2x", fake_image),
            ("summary-gray2x", fake_image),
        ]
        ocr_side_effect = [
            "导出2张图片，其中1张是未编辑图片",
            "导出2张图片",
        ]

        with mock.patch(
            "process_monitor._prepare_export_count_ocr_variants",
            return_value=fake_variants,
        ), mock.patch(
            "process_monitor.run_windows_ocr", side_effect=ocr_side_effect
        ):
            self.assertEqual(detect_export_summary_count_from_image(fake_image), 2)

    def test_detect_export_summary_count_from_image_uses_button_anchor(self):
        """普通导出页不是全屏时，应能借助按钮位置反推出摘要区。"""
        from process_monitor import detect_export_summary_count_from_image

        fake_image = Image.new("RGB", (1200, 800), (45, 47, 52))
        fake_variants = [
            ("summary_anchor-rgb2x", fake_image),
            ("summary-rgb2x", fake_image),
        ]
        ocr_side_effect = [
            "导出2张图片",
            "",
        ]

        with mock.patch(
            "process_monitor._prepare_export_count_ocr_variants",
            return_value=fake_variants,
        ), mock.patch(
            "process_monitor.run_windows_ocr", side_effect=ocr_side_effect
        ):
            self.assertEqual(
                detect_export_summary_count_from_image(
                    fake_image, button_bounds=(820, 690, 980, 760)
                ),
                2,
            )

    def test_detect_export_summary_count_from_image_fast_mode_prefers_anchor_variants(self):
        """快速预判应优先尝试按钮锚定摘要区，并使用短超时。"""
        from process_monitor import detect_export_summary_count_from_image

        fake_image = Image.new("RGB", (1200, 800), (45, 47, 52))
        fake_variants = [
            ("summary-gray2x", fake_image),
            ("summary_anchor_wide-rgb2x", fake_image),
            ("summary_anchor-rgb2x", fake_image),
            ("summary_popup_title-rgb2x", fake_image),
            ("summary_popup_title_wide-rgb2x", fake_image),
        ]

        with mock.patch(
            "process_monitor._prepare_export_count_ocr_variants",
            return_value=fake_variants,
        ), mock.patch(
            "process_monitor.run_windows_ocr",
            side_effect=["导出2张图片"],
        ) as mock_ocr:
            self.assertEqual(
                detect_export_summary_count_from_image(
                    fake_image,
                    button_bounds=(820, 690, 980, 760),
                    fast_mode=True,
                ),
                2,
            )

        self.assertEqual(mock_ocr.call_count, 1)
        self.assertEqual(mock_ocr.call_args.kwargs.get("timeout_seconds"), 0.9)

    def test_monitor_reuses_last_export_capture_image(self):
        """导出触发瞬间的截图应该能被主流程复用。"""
        from process_monitor import ProcessMonitor
        from config_manager import ConfigManager

        monitor = ProcessMonitor(ConfigManager())
        fake_image = Image.new("RGB", (320, 200), (45, 47, 52))
        monitor._remember_export_capture(fake_image, 10.0, 23456, dialog_mode=True)

        with mock.patch("process_monitor.time.monotonic", return_value=12.0):
            cached_image = monitor.get_last_export_capture_image()
            self.assertIsNotNone(cached_image)
            self.assertEqual(cached_image.size, fake_image.size)
            self.assertTrue(monitor.get_last_export_capture_dialog_mode())

        with mock.patch("process_monitor.time.monotonic", return_value=20.5):
            self.assertIsNone(monitor.get_last_export_capture_image(max_age_seconds=5.0))
            self.assertFalse(
                monitor.get_last_export_capture_dialog_mode(max_age_seconds=5.0)
            )

    def test_capture_main_window_image_reuses_cached_frame_when_suspended(self):
        """目标进程已挂起时，不应再走实时截图，避免窗口抓取卡死。"""
        from process_monitor import ProcessMonitor
        from config_manager import ConfigManager

        monitor = ProcessMonitor(ConfigManager())
        fake_image = Image.new("RGB", (320, 200), (45, 47, 52))
        monitor._remember_export_capture(fake_image, 10.0, 23456, dialog_mode=True)
        monitor._suspended_pids = {123}

        with mock.patch("process_monitor.time.monotonic", return_value=12.0), \
             mock.patch("process_monitor.capture_window_image") as mock_capture:
            cached_image = monitor.capture_main_window_image()

        self.assertIsNotNone(cached_image)
        self.assertEqual(cached_image.size, fake_image.size)
        mock_capture.assert_not_called()

    def test_monitor_signals(self):
        """测试监控线程信号"""
        from process_monitor import ProcessMonitor
        from config_manager import ConfigManager

        config = ConfigManager()
        monitor = ProcessMonitor(config)

        # 信号计数器
        self.signals_received = {
            "process_started": 0,
            "process_stopped": 0,
            "export_detected": 0,
            "export_cancelled": 0,
        }

        # 连接信号
        monitor.process_started.connect(lambda: self._count_signal("process_started"))
        monitor.process_stopped.connect(lambda: self._count_signal("process_stopped"))
        monitor.export_detected.connect(lambda: self._count_signal("export_detected"))
        monitor.export_cancelled.connect(lambda: self._count_signal("export_cancelled"))

        # 启动线程
        monitor.start()
        self.assertTrue(monitor.isRunning())

        # 等待一下
        time.sleep(1)

        # 停止线程
        monitor.stop()
        monitor.wait(3000)
        self.assertFalse(monitor.isRunning())

        print("✓ 监控线程信号测试通过")

    def _count_signal(self, signal_name):
        """计数信号"""
        self.signals_received[signal_name] += 1


class TestProcessMonitorVisualDetection(unittest.TestCase):
    """测试基于截图的导出页视觉识别。"""

    def test_export_visual_positive(self):
        from process_monitor import image_matches_export_visual_state

        image = Image.new("RGB", (960, 800), (45, 47, 52))
        draw = ImageDraw.Draw(image)
        draw.rectangle((752, 712, 911, 775), fill=(244, 206, 74))

        self.assertTrue(image_matches_export_visual_state(image))

    def test_export_visual_negative(self):
        from process_monitor import image_matches_export_visual_state

        image = Image.new("RGB", (960, 800), (45, 47, 52))
        draw = ImageDraw.Draw(image)
        draw.rectangle((80, 80, 160, 120), fill=(244, 206, 74))

        self.assertFalse(image_matches_export_visual_state(image))


def run_process_monitor_tests():
    """运行进程监控测试"""
    print("=" * 60)
    print("进程监控模块测试")
    print("=" * 60)

    if not HAS_WIN32:
        print("⚠ pywin32未安装，跳过窗口相关测试")

    # 创建测试套件
    suite = unittest.TestLoader().loadTestsFromTestCase(TestProcessMonitor)
    suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestProcessMonitorThread)
    )

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_process_monitor_tests()
    sys.exit(0 if success else 1)
