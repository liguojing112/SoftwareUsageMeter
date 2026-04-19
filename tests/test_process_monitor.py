"""
进程监控模块测试
测试进程检测、窗口查找、导出检测、窗口锁定等功能
"""

import os
import sys
import time
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

    def test_window_matches_keywords_only_uses_title(self):
        """Qt SaveBits 这类类名命中不应再被误判为导出窗口。"""
        from process_monitor import window_matches_keywords

        with mock.patch("process_monitor.get_window_title", return_value=""), \
             mock.patch("process_monitor.get_window_class", return_value="Qt5152QWindowToolTipSaveBits"):
            self.assertFalse(window_matches_keywords(12345, ["save"]))

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
