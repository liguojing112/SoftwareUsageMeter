"""
集成测试
测试模块间的交互和完整业务流程
"""

import os
import sys
import time
import tempfile
import shutil
import unittest

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer, Qt


class MockProcessMonitor:
    """模拟进程监控器，用于集成测试"""

    def __init__(self):
        self.process_started = type("Signal", (), {"connect": lambda x: None})()
        self.process_stopped = type("Signal", (), {"connect": lambda x: None})()
        self.export_detected = type("Signal", (), {"connect": lambda x: None})()
        self.export_cancelled = type("Signal", (), {"connect": lambda x: None})()

        self._callbacks = {}
        self._running = False
        self._exporting = False

    def start(self):
        self._running = True

    def stop(self):
        self._running = False

    def isRunning(self):
        return self._running

    def connect_signal(self, signal_name, callback):
        """连接信号"""
        self._callbacks[signal_name] = callback

    def simulate_process_start(self):
        """模拟进程启动"""
        if "process_started" in self._callbacks:
            self._callbacks["process_started"]()

    def simulate_process_stop(self):
        """模拟进程退出"""
        if "process_stopped" in self._callbacks:
            self._callbacks["process_stopped"]()

    def simulate_export_detected(self):
        """模拟检测到导出"""
        if "export_detected" in self._callbacks:
            self._exporting = True
            self._callbacks["export_detected"]()

    def simulate_export_cancelled(self):
        """模拟导出取消"""
        if "export_cancelled" in self._callbacks:
            self._exporting = False
            self._callbacks["export_cancelled"]()


class TestIntegration(unittest.TestCase):
    """集成测试"""

    @classmethod
    def setUpClass(cls):
        """类级别设置"""
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        """测试前准备"""
        # 创建临时目录
        self.test_dir = tempfile.mkdtemp(prefix="integration_test_")

        # 保存原始函数
        import config_manager

        self.original_get_app_dir = config_manager.get_app_dir

        # 临时修改函数返回测试目录
        config_manager.get_app_dir = lambda: self.test_dir

        # 创建测试配置
        self._create_test_config()

        # 导入模块
        from config_manager import ConfigManager
        from timer_manager import TimerManager
        from payment_overlay import PaymentOverlay

        # 初始化模块
        self.config = ConfigManager()
        self.timer = TimerManager()
        self.overlay = PaymentOverlay(self.config)

        # 创建模拟监控器
        self.monitor = MockProcessMonitor()

        # 状态跟踪
        self.timer_started = False
        self.timer_stopped = False
        self.overlay_shown = False
        self.overlay_closed = False
        self.timer_reset = False

        print(f"测试目录: {self.test_dir}")

    def tearDown(self):
        """测试后清理"""
        # 恢复原始函数
        import config_manager

        config_manager.get_app_dir = self.original_get_app_dir

        # 清理临时目录
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_test_config(self):
        """创建测试配置"""
        config_path = os.path.join(self.test_dir, "config.json")
        config = {
            "rate": 1.5,
            "admin_password": "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918",  # admin
            "qr_code_path": "",
            "process_name": "TestApp.exe",
            "export_window_keywords": ["导出", "Export"],
            "monitor_interval_ms": 1000,
        }

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

    def _connect_signals(self):
        """连接信号（模拟main.py中的连接）"""
        # 进程监控信号
        self.monitor.connect_signal("process_started", self._on_process_started)
        self.monitor.connect_signal("process_stopped", self._on_process_stopped)
        self.monitor.connect_signal("export_detected", self._on_export_detected)
        self.monitor.connect_signal("export_cancelled", self._on_export_cancelled)

        # 收费弹窗确认按钮
        self.overlay.confirm_button.clicked.connect(self._on_payment_confirmed)

    def _on_process_started(self):
        """模拟进程启动处理"""
        self.timer_started = True
        self.timer.start()
        print("  计时器启动")

    def _on_process_stopped(self):
        """模拟进程退出处理"""
        self.timer_stopped = True
        self.timer.pause()
        print("  计时器暂停")

    def _on_export_detected(self):
        """模拟导出检测处理"""
        # 停止计时
        self.timer.pause()

        # 获取计费信息
        minutes = self.timer.get_elapsed_minutes()
        rate = self.config.rate

        # 显示收费弹窗
        self.overlay.show_payment(minutes, rate, None)
        self.overlay_shown = True

        print(f"  显示收费弹窗: {minutes}分钟, ¥{minutes * rate:.2f}")

    def _on_export_cancelled(self):
        """模拟导出取消处理"""
        print("  导出取消")

    def _on_payment_confirmed(self):
        """模拟确认收款处理"""
        self.overlay.close_payment()
        self.overlay_closed = True
        self.timer.reset()
        self.timer_reset = True
        print("  确认收款，计时器重置")

    def test_complete_payment_flow(self):
        """测试完整收费流程"""
        print("\n测试完整收费流程:")

        # 连接信号
        self._connect_signals()

        # 1. 模拟进程启动
        print("1. 模拟进程启动")
        self.monitor.simulate_process_start()

        # 处理事件
        QApplication.processEvents()
        time.sleep(0.5)

        self.assertTrue(self.timer_started)
        self.assertTrue(self.timer.is_running)

        # 2. 模拟使用3分钟
        print("2. 模拟使用3分钟")
        for i in range(6):  # 6 * 0.5 = 3秒（模拟）
            QApplication.processEvents()
            time.sleep(0.1)

        elapsed = self.timer.get_elapsed_seconds()
        self.assertGreater(elapsed, 0)
        print(f"   已用时: {self.timer.format_elapsed()}")

        # 3. 模拟检测到导出
        print("3. 模拟检测到导出")
        self.monitor.simulate_export_detected()

        QApplication.processEvents()
        time.sleep(0.5)

        self.assertTrue(self.overlay_shown)
        self.assertTrue(self.overlay.isVisible())
        self.assertFalse(self.timer.is_running)  # 计时应暂停

        # 4. 模拟确认收款
        print("4. 模拟确认收款")
        # 模拟点击确认按钮
        self.overlay.confirm_button.click()

        QApplication.processEvents()
        time.sleep(0.5)

        self.assertTrue(self.overlay_closed)
        self.assertFalse(self.overlay.isVisible())
        self.assertTrue(self.timer_reset)
        self.assertEqual(self.timer.get_elapsed_seconds(), 0)

        print("✓ 完整收费流程测试通过")

    def test_export_cancel_flow(self):
        """测试导出取消流程"""
        print("\n测试导出取消流程:")

        # 重置状态
        self.timer_started = False
        self.overlay_shown = False

        # 连接信号
        self._connect_signals()

        # 1. 启动计时
        print("1. 启动计时")
        self.monitor.simulate_process_start()

        QApplication.processEvents()
        time.sleep(0.5)

        # 2. 模拟使用
        print("2. 模拟使用")
        for i in range(4):
            QApplication.processEvents()
            time.sleep(0.1)

        # 3. 检测到导出
        print("3. 检测到导出")
        self.monitor.simulate_export_detected()

        QApplication.processEvents()
        time.sleep(0.5)

        self.assertTrue(self.overlay_shown)
        self.assertTrue(self.overlay.isVisible())

        # 4. 模拟导出取消（不确认收款）
        print("4. 模拟导出取消")
        self.monitor.simulate_export_cancelled()

        QApplication.processEvents()
        time.sleep(0.5)

        # 弹窗应保持显示（只有确认收款才关闭）
        self.assertTrue(self.overlay.isVisible())

        # 计时器应保持暂停状态
        self.assertFalse(self.timer.is_running)

        print("✓ 导出取消流程测试通过")

    def test_process_stop_during_payment(self):
        """测试收费过程中进程退出"""
        print("\n测试收费过程中进程退出:")

        # 重置状态
        self.timer_started = False
        self.overlay_shown = False

        # 连接信号
        self._connect_signals()

        # 1. 启动计时并检测到导出
        print("1. 启动计时并检测到导出")
        self.monitor.simulate_process_start()
        self.monitor.simulate_export_detected()

        QApplication.processEvents()
        time.sleep(0.5)

        self.assertTrue(self.overlay_shown)
        self.assertTrue(self.overlay.isVisible())

        # 2. 模拟进程退出
        print("2. 模拟进程退出")
        self.monitor.simulate_process_stop()

        QApplication.processEvents()
        time.sleep(0.5)

        # 收费弹窗应关闭
        self.assertFalse(self.overlay.isVisible())

        # 计时器应暂停
        self.assertFalse(self.timer.is_running)

        print("✓ 收费过程中进程退出测试通过")

    def test_multiple_export_detections(self):
        """测试多次导出检测"""
        print("\n测试多次导出检测:")

        # 重置状态
        self.timer_started = False
        self.overlay_shown_count = 0

        # 修改回调以计数
        original_on_export = self._on_export_detected

        def counting_on_export():
            self.overlay_shown_count += 1
            original_on_export()

        self._on_export_detected = counting_on_export

        # 连接信号
        self._connect_signals()

        # 1. 启动计时
        print("1. 启动计时")
        self.monitor.simulate_process_start()

        QApplication.processEvents()
        time.sleep(0.5)

        # 2. 多次检测到导出（应只显示一次）
        print("2. 多次检测到导出")
        for i in range(3):
            self.monitor.simulate_export_detected()
            QApplication.processEvents()
            time.sleep(0.1)

        # 应只显示一次弹窗
        self.assertEqual(self.overlay_shown_count, 1)

        print("✓ 多次导出检测测试通过")


class TestAdminIntegration(unittest.TestCase):
    """管理员功能集成测试"""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        # 创建临时目录
        self.test_dir = tempfile.mkdtemp(prefix="admin_test_")

        # 保存原始函数
        import config_manager

        self.original_get_app_dir = config_manager.get_app_dir
        config_manager.get_app_dir = lambda: self.test_dir

        # 创建测试配置
        self._create_test_config()

        from config_manager import ConfigManager

        self.config = ConfigManager()

    def tearDown(self):
        import config_manager

        config_manager.get_app_dir = self.original_get_app_dir

        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_test_config(self):
        config_path = os.path.join(self.test_dir, "config.json")
        config = {
            "rate": 1.0,
            "admin_password": "8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918",  # admin
            "qr_code_path": "",
            "process_name": "PixCake.exe",
            "export_window_keywords": ["导出", "Export"],
            "monitor_interval_ms": 2000,
        }

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

    def test_config_update_flow(self):
        """测试配置更新流程"""
        print("\n测试配置更新流程:")

        from admin_panel import AdminPanel

        # 初始配置
        initial_rate = self.config.rate
        initial_process = self.config.process_name

        print(f"初始配置: rate={initial_rate}, process={initial_process}")

        # 模拟配置更新（不实际打开UI）
        new_data = {
            "rate": 2.5,
            "process_name": "NewApp.exe",
            "export_window_keywords": ["保存", "Save As"],
            "monitor_interval_ms": 3000,
        }

        # 更新配置
        self.config.update(new_data)

        # 验证更新
        self.assertEqual(self.config.rate, 2.5)
        self.assertEqual(self.config.process_name, "NewApp.exe")
        self.assertIn("保存", self.config.export_window_keywords)
        self.assertEqual(self.config.monitor_interval_ms, 3000)

        print(
            f"更新后配置: rate={self.config.rate}, process={self.config.process_name}"
        )
        print("✓ 配置更新流程测试通过")


def run_integration_tests():
    """运行集成测试"""
    print("=" * 60)
    print("集成测试")
    print("=" * 60)

    # 创建测试套件
    suite = unittest.TestLoader().loadTestsFromTestCase(TestIntegration)
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestAdminIntegration))

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    import json  # 在顶部导入

    success = run_integration_tests()
    sys.exit(0 if success else 1)
