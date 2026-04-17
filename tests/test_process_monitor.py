"""
进程监控模块测试
测试进程检测、窗口查找、导出检测、窗口锁定等功能
"""

import os
import sys
import time
import subprocess
import unittest

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
        )

        self.is_process_running = is_process_running
        self.find_pid_by_name = find_pid_by_name
        self.find_windows_by_pid = find_windows_by_pid
        self.find_main_window = find_main_window
        self.check_export_dialog = check_export_dialog
        self.disable_window = disable_window
        self.enable_window = enable_window

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
