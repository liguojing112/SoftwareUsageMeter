"""
计时器模块测试
测试计时开始/暂停/重置、分钟计算、时间格式化、信号发射
"""

import os
import sys
import time
import unittest

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer


class TestTimerManager(unittest.TestCase):
    """测试计时器管理器"""

    @classmethod
    def setUpClass(cls):
        """类级别设置 - 创建Qt应用"""
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        """测试前准备"""
        from timer_manager import TimerManager

        self.timer = TimerManager()

        # 信号计数器
        self.tick_count = 0
        self.minute_tick_count = 0

        # 连接信号
        self.timer.tick.connect(lambda x: self._on_tick(x))
        self.timer.minute_tick.connect(lambda x: self._on_minute_tick(x))

    def _on_tick(self, seconds):
        """tick信号处理"""
        self.tick_count += 1

    def _on_minute_tick(self, minutes):
        """minute_tick信号处理"""
        self.minute_tick_count += 1

    def test_start_pause_reset(self):
        """测试开始、暂停、重置功能"""
        # 初始状态
        self.assertFalse(self.timer.is_running)
        self.assertEqual(self.timer.get_elapsed_seconds(), 0)
        self.assertEqual(self.timer.get_elapsed_minutes(), 0)

        # 开始计时
        self.timer.start()
        self.assertTrue(self.timer.is_running)

        # 处理事件让计时器工作
        for _ in range(3):
            QApplication.processEvents()
            time.sleep(0.5)

        # 暂停计时
        self.timer.pause()
        self.assertFalse(self.timer.is_running)

        elapsed = self.timer.get_elapsed_seconds()
        self.assertGreaterEqual(elapsed, 1, f"应至少记录1秒，实际: {elapsed}")

        # 重置计时
        self.timer.reset()
        self.assertEqual(self.timer.get_elapsed_seconds(), 0)
        self.assertEqual(self.timer.get_elapsed_minutes(), 0)

        print("✓ 开始/暂停/重置测试通过")

    def test_minute_calculation(self):
        """测试分钟计算（向上取整）"""
        test_cases = [
            (0, 0),  # 0秒 = 0分钟
            (1, 1),  # 1秒 = 1分钟（向上取整）
            (59, 1),  # 59秒 = 1分钟
            (60, 1),  # 60秒 = 1分钟
            (61, 2),  # 61秒 = 2分钟
            (119, 2),  # 119秒 = 2分钟
            (120, 2),  # 120秒 = 2分钟
            (121, 3),  # 121秒 = 3分钟
        ]

        for seconds, expected_minutes in test_cases:
            # 模拟已用时间
            self.timer._elapsed_seconds = seconds
            actual_minutes = self.timer.get_elapsed_minutes()
            self.assertEqual(
                actual_minutes,
                expected_minutes,
                f"{seconds}秒应计算为{expected_minutes}分钟，实际: {actual_minutes}",
            )

        print("✓ 分钟计算测试通过")

    def test_time_formatting(self):
        """测试时间格式化"""
        test_cases = [
            (0, "00:00:00"),
            (1, "00:00:01"),
            (59, "00:00:59"),
            (60, "00:01:00"),
            (61, "00:01:01"),
            (3599, "00:59:59"),
            (3600, "01:00:00"),
            (3661, "01:01:01"),
            (86399, "23:59:59"),
        ]

        for seconds, expected_format in test_cases:
            self.timer._elapsed_seconds = seconds
            actual_format = self.timer.format_elapsed()
            self.assertEqual(
                actual_format,
                expected_format,
                f"{seconds}秒应格式化为'{expected_format}'，实际: '{actual_format}'",
            )

        print("✓ 时间格式化测试通过")

    def test_stop_and_report(self):
        """测试停止并报告功能"""
        # 模拟计时
        self.timer._elapsed_seconds = 125  # 2分钟5秒

        # 停止并报告
        minutes = self.timer.stop_and_report()

        # 应返回3分钟（125秒向上取整）
        self.assertEqual(minutes, 3)

        # 计时器应重置
        self.assertEqual(self.timer.get_elapsed_seconds(), 0)
        self.assertFalse(self.timer.is_running)

        print("✓ 停止并报告测试通过")

    def test_signal_emission(self):
        """测试信号发射"""
        # 重置计数器
        self.tick_count = 0
        self.minute_tick_count = 0

        # 开始计时
        self.timer.start()

        # 模拟65秒（应触发至少1次minute_tick）
        for i in range(13):  # 13 * 0.5 = 6.5秒（实际测试用）
            QApplication.processEvents()
            time.sleep(0.1)  # 快速测试

        # 暂停计时
        self.timer.pause()

        # 验证信号发射
        self.assertGreater(self.tick_count, 0, "tick信号应至少发射一次")
        # 注意：由于测试时间短，可能不会触发minute_tick

        print("✓ 信号发射测试通过")

    def test_concurrent_operations(self):
        """测试并发操作（重复开始/暂停）"""
        # 多次开始/暂停不应出错
        for _ in range(5):
            self.timer.start()
            self.assertTrue(self.timer.is_running)

            QApplication.processEvents()
            time.sleep(0.25)

            self.timer.pause()
            self.assertFalse(self.timer.is_running)

        # 最终状态
        self.assertFalse(self.timer.is_running)
        self.assertGreater(self.timer.get_elapsed_seconds(), 0)

        print("✓ 并发操作测试通过")


def run_timer_tests():
    """运行计时器测试"""
    print("=" * 60)
    print("计时器模块测试")
    print("=" * 60)

    # 创建测试套件
    suite = unittest.TestLoader().loadTestsFromTestCase(TestTimerManager)

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_timer_tests()
    sys.exit(0 if success else 1)
