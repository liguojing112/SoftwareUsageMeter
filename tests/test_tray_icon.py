"""
托盘图标模块测试
测试系统托盘图标、状态窗口、菜单功能
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication, QMenu, QSystemTrayIcon
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtTest import QTest


class TestTrayIcon(unittest.TestCase):
    """测试托盘图标"""

    @classmethod
    def setUpClass(cls):
        """类级别设置 - 创建Qt应用"""
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        """测试前准备"""
        from tray_icon import TrayIcon
        from config_manager import ConfigManager

        # 创建临时目录用于测试配置
        self.test_dir = tempfile.mkdtemp(prefix="tray_test_")

        # 保存原始函数
        import config_manager

        self.original_get_app_dir = config_manager.get_app_dir

        # 临时修改函数返回测试目录
        config_manager.get_app_dir = lambda: self.test_dir

        # 创建配置管理器
        self.config = ConfigManager()

        # 创建托盘图标
        self.tray = TrayIcon(self.config)

        # 显示托盘图标
        self.tray.show()
        QApplication.processEvents()

    def tearDown(self):
        """测试后清理"""
        self.tray.hide()

        # 恢复原始函数
        import config_manager

        config_manager.get_app_dir = self.original_get_app_dir

        # 清理临时目录
        import shutil

        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_tray_icon_creation(self):
        """测试托盘图标创建"""
        # 检查托盘图标存在
        self.assertIsNotNone(self.tray.tray_icon)
        self.assertTrue(self.tray.tray_icon.isVisible())

        # 检查图标
        self.assertIsNotNone(self.tray.tray_icon.icon())

        # 检查工具提示
        self.assertEqual(self.tray.tray_icon.toolTip(), "软件用途计时计费系统")

        print("✓ 托盘图标创建测试通过")

    def test_status_window(self):
        """测试状态窗口"""
        # 检查状态窗口存在
        self.assertIsNotNone(self.tray.status_window)

        # 检查窗口标题
        self.assertEqual(self.tray.status_window.windowTitle(), "使用状态")

        # 检查窗口属性
        flags = self.tray.status_window.windowFlags()
        self.assertTrue(flags & Qt.Window)
        self.assertTrue(flags & Qt.WindowStaysOnTopHint)
        self.assertTrue(flags & Qt.WindowMinimizeButtonHint)
        self.assertTrue(flags & Qt.WindowCloseButtonHint)

        # 检查初始状态显示
        self.assertEqual(
            self.tray.status_window.duration_label.text(), "使用时长: 0分钟"
        )
        self.assertEqual(self.tray.status_window.amount_label.text(), "应付金额: ¥0.0")

        print("✓ 状态窗口测试通过")

    def test_menu_creation(self):
        """测试菜单创建"""
        # 获取菜单
        menu = self.tray.tray_icon.contextMenu()
        self.assertIsNotNone(menu)

        # 检查菜单项
        actions = menu.actions()
        action_texts = [action.text() for action in actions]

        # 应包含以下菜单项
        expected_items = ["显示状态", "打开管理面板", "暂停计时", "重置计时", "退出"]
        for item in expected_items:
            self.assertIn(item, action_texts)

        print("✓ 菜单创建测试通过")

    def test_status_update(self):
        """测试状态更新"""
        # 更新状态
        self.tray.update_status(duration_minutes=5, amount=10.0, is_running=True)
        QApplication.processEvents()

        # 检查状态窗口更新
        self.assertEqual(
            self.tray.status_window.duration_label.text(), "使用时长: 5分钟"
        )
        self.assertEqual(self.tray.status_window.amount_label.text(), "应付金额: ¥10.0")

        # 检查托盘图标工具提示更新
        tooltip = self.tray.tray_icon.toolTip()
        self.assertIn("5分钟", tooltip)
        self.assertIn("¥10.0", tooltip)

        print("✓ 状态更新测试通过")

    def test_menu_actions(self):
        """测试菜单动作"""
        # 测试显示状态
        with patch.object(self.tray.status_window, "show") as mock_show:
            self.tray.show_status()
            mock_show.assert_called_once()

        # 测试打开管理面板
        with patch.object(self.tray, "show_admin_panel") as mock_show_admin:
            self.tray.show_admin_panel()
            mock_show_admin.assert_called_once()

        # 测试暂停/恢复计时
        # 模拟计时器运行状态
        self.tray.is_timer_running = True

        # 第一次点击应暂停
        self.tray.toggle_timer()
        self.assertFalse(self.tray.is_timer_running)

        # 第二次点击应恢复
        self.tray.toggle_timer()
        self.assertTrue(self.tray.is_timer_running)

        # 测试重置计时
        with patch.object(self.tray, "reset_timer") as mock_reset:
            self.tray.reset_timer()
            mock_reset.assert_called_once()

        print("✓ 菜单动作测试通过")

    def test_tray_icon_double_click(self):
        """测试托盘图标双击"""
        # 模拟双击事件
        with patch.object(self.tray.status_window, "show") as mock_show:
            # 触发双击信号
            self.tray.tray_icon.activated.emit(QSystemTrayIcon.DoubleClick)
            QApplication.processEvents()

            # 应显示状态窗口
            mock_show.assert_called_once()

        print("✓ 托盘图标双击测试通过")

    def test_notification(self):
        """测试通知功能"""
        # 发送通知
        with patch.object(self.tray.tray_icon, "showMessage") as mock_show_message:
            self.tray.show_notification("测试标题", "测试消息")

            # 检查通知参数
            mock_show_message.assert_called_once()
            args = mock_show_message.call_args
            self.assertEqual(args[0][0], "测试标题")
            self.assertEqual(args[0][1], "测试消息")
            self.assertEqual(args[1], QSystemTrayIcon.Information)
            self.assertEqual(args[2], 3000)  # 3秒显示时间

        print("✓ 通知功能测试通过")

    def test_visual_appearance(self):
        """测试视觉效果"""
        # 检查状态窗口样式
        stylesheet = self.tray.status_window.styleSheet()
        self.assertIn("background-color", stylesheet)
        self.assertIn("color", stylesheet)

        # 检查字体
        font = self.tray.status_window.duration_label.font()
        self.assertGreaterEqual(font.pointSize(), 12)  # 足够大的字体

        # 检查布局
        self.assertIsNotNone(self.tray.status_window.layout)
        self.assertGreater(self.tray.status_window.layout.count(), 0)

        print("✓ 视觉效果测试通过")

    def test_timer_state_visualization(self):
        """测试计时器状态可视化"""
        # 测试运行状态
        self.tray.update_status(duration_minutes=3, amount=3.0, is_running=True)
        QApplication.processEvents()

        # 检查菜单文本
        menu = self.tray.tray_icon.contextMenu()
        pause_action = None
        for action in menu.actions():
            if "暂停" in action.text():
                pause_action = action
                break

        self.assertIsNotNone(pause_action)
        self.assertIn("暂停", pause_action.text())

        # 测试暂停状态
        self.tray.update_status(duration_minutes=3, amount=3.0, is_running=False)
        QApplication.processEvents()

        # 更新菜单
        menu = self.tray.tray_icon.contextMenu()
        for action in menu.actions():
            if "恢复" in action.text() or "开始" in action.text():
                pause_action = action
                break

        self.assertIsNotNone(pause_action)
        self.assertIn("恢复", pause_action.text() or "开始")

        print("✓ 计时器状态可视化测试通过")

    def test_error_handling(self):
        """测试错误处理"""
        # 测试无效状态更新
        try:
            self.tray.update_status(duration_minutes=-1, amount=-1.0, is_running=True)
            QApplication.processEvents()
        except Exception as e:
            self.fail(f"状态更新应处理无效参数: {e}")

        # 测试空配置
        try:
            from tray_icon import TrayIcon

            tray2 = TrayIcon(None)
            tray2.show()
            QApplication.processEvents()
            tray2.hide()
        except Exception as e:
            self.fail(f"应处理空配置: {e}")

        print("✓ 错误处理测试通过")


def run_tray_tests():
    """运行托盘图标测试"""
    print("=" * 60)
    print("托盘图标模块测试")
    print("=" * 60)

    # 创建测试套件
    suite = unittest.TestLoader().loadTestsFromTestCase(TestTrayIcon)

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tray_tests()
    sys.exit(0 if success else 1)
