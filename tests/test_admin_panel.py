"""
管理面板模块测试
测试密码验证、配置修改、界面功能
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication, QLineEdit, QPushButton
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest


class TestAdminPanel(unittest.TestCase):
    """测试管理面板"""

    @classmethod
    def setUpClass(cls):
        """类级别设置 - 创建Qt应用"""
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        """测试前准备"""
        from admin_panel import AdminPanel
        from config_manager import ConfigManager

        # 创建临时目录用于测试配置
        self.test_dir = tempfile.mkdtemp(prefix="admin_test_")

        # 保存原始函数
        import config_manager

        self.original_get_app_dir = config_manager.get_app_dir

        # 临时修改函数返回测试目录
        config_manager.get_app_dir = lambda: self.test_dir

        # 创建配置管理器
        self.config = ConfigManager()

        # 创建管理面板
        self.panel = AdminPanel(self.config)

        # 显示面板
        self.panel.show()
        QApplication.processEvents()

    def tearDown(self):
        """测试后清理"""
        self.panel.close()

        # 恢复原始函数
        import config_manager

        config_manager.get_app_dir = self.original_get_app_dir

        # 清理临时目录
        import shutil

        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_password_verification(self):
        """测试密码验证"""
        # 默认密码是"admin"的哈希
        from config_manager import hash_password

        default_password_hash = hash_password("admin")

        # 测试正确密码
        self.assertTrue(self.panel.verify_password("admin"))

        # 测试错误密码
        self.assertFalse(self.panel.verify_password("wrong"))

        # 测试空密码
        self.assertFalse(self.panel.verify_password(""))

        print("✓ 密码验证测试通过")

    def test_password_change(self):
        """测试密码修改"""
        # 修改密码
        new_password = "newpassword123"
        self.panel.change_password(new_password)

        # 验证新密码
        self.assertTrue(self.panel.verify_password(new_password))

        # 验证旧密码不再有效
        self.assertFalse(self.panel.verify_password("admin"))

        print("✓ 密码修改测试通过")

    def test_config_update(self):
        """测试配置更新"""
        # 获取初始值
        initial_rate = self.config.rate
        initial_process = self.config.process_name

        # 模拟界面输入
        self.panel.rate_input.setText("2.5")
        self.panel.export_rate_input.setText("3.5")
        self.panel.process_input.setText("TestApp.exe")
        self.panel.keywords_input.setText("保存,Save,导出")

        # 点击保存按钮
        QTest.mouseClick(self.panel.save_button, Qt.LeftButton)
        QApplication.processEvents()

        # 验证配置已更新
        self.assertEqual(self.config.rate, 2.5)
        self.assertEqual(self.config.export_rate, 3.5)
        self.assertEqual(self.config.process_name, "TestApp.exe")
        self.assertIn("保存", self.config.export_window_keywords)
        self.assertIn("Save", self.config.export_window_keywords)
        self.assertIn("导出", self.config.export_window_keywords)

        print("✓ 配置更新测试通过")

    def test_config_validation(self):
        """测试配置验证"""
        # 测试无效费率（负数）
        self.panel.rate_input.setText("-1.0")
        QTest.mouseClick(self.panel.save_button, Qt.LeftButton)
        QApplication.processEvents()

        # 应显示错误提示
        self.assertIn("费率必须大于0", self.panel.status_label.text())

        # 测试无效费率（非数字）
        self.panel.rate_input.setText("abc")
        QTest.mouseClick(self.panel.save_button, Qt.LeftButton)
        QApplication.processEvents()

        # 应显示错误提示
        self.assertIn("请输入有效的数字", self.panel.status_label.text())

        # 测试无效导出单价
        self.panel.rate_input.setText("1.0")
        self.panel.export_rate_input.setText("-2")
        QTest.mouseClick(self.panel.save_button, Qt.LeftButton)
        QApplication.processEvents()
        self.assertIn("单张导出单价不能小于0", self.panel.status_label.text())

        # 测试空进程名
        self.panel.rate_input.setText("1.0")  # 恢复有效费率
        self.panel.export_rate_input.setText("0")
        self.panel.process_input.setText("")
        QTest.mouseClick(self.panel.save_button, Qt.LeftButton)
        QApplication.processEvents()

        # 应显示错误提示
        self.assertIn("进程名不能为空", self.panel.status_label.text())

        print("✓ 配置验证测试通过")

    def test_ui_components(self):
        """测试UI组件"""
        # 检查所有组件都存在
        self.assertIsNotNone(self.panel.rate_input)
        self.assertIsNotNone(self.panel.export_rate_input)
        self.assertIsNotNone(self.panel.process_input)
        self.assertIsNotNone(self.panel.keywords_input)
        self.assertIsNotNone(self.panel.qr_path_input)
        self.assertIsNotNone(self.panel.save_button)
        self.assertIsNotNone(self.panel.status_label)
        self.assertIsNotNone(self.panel.qr_preview_label)

        # 检查初始值显示
        self.assertEqual(self.panel.rate_input.text(), "1.0")
        self.assertEqual(self.panel.export_rate_input.text(), "0.0")
        self.assertEqual(self.panel.process_input.text(), "PixCake.exe")
        self.assertEqual(self.panel.keywords_input.text(), "导出,Export")

        print("✓ UI组件测试通过")

    def test_qr_code_preview(self):
        """测试收款码预览"""
        # 创建测试图片
        test_qr_path = os.path.join(self.test_dir, "test_qr.png")
        from PyQt5.QtGui import QPixmap

        pixmap = QPixmap(200, 200)
        pixmap.fill(Qt.white)
        pixmap.save(test_qr_path)

        # 更新QR路径
        self.panel.qr_path_input.setText(test_qr_path)

        # 模拟路径变化
        self.panel.on_qr_path_changed(test_qr_path)
        QApplication.processEvents()

        # 检查预览更新
        self.assertIsNotNone(self.panel.qr_preview_label.pixmap())

        # 测试无效路径
        self.panel.on_qr_path_changed("nonexistent.png")
        QApplication.processEvents()

        # 应显示占位图
        self.assertIsNotNone(self.panel.qr_preview_label.pixmap())

        print("✓ 收款码预览测试通过")

    def test_window_properties(self):
        """测试窗口属性"""
        # 检查窗口标题
        self.assertEqual(self.panel.windowTitle(), "管理设置")

        # 检查窗口大小
        self.assertGreater(self.panel.width(), 400)
        self.assertGreater(self.panel.height(), 500)

        # 检查置顶标志
        flags = self.panel.windowFlags()
        self.assertTrue(flags & Qt.WindowStaysOnTopHint)

        print("✓ 窗口属性测试通过")

    def test_save_success_feedback(self):
        """测试保存成功反馈"""
        # 输入有效配置
        self.panel.rate_input.setText("3.0")
        self.panel.export_rate_input.setText("2.0")
        self.panel.process_input.setText("MyApp.exe")

        # 点击保存
        QTest.mouseClick(self.panel.save_button, Qt.LeftButton)
        QApplication.processEvents()

        # 检查成功提示
        self.assertIn("配置已保存", self.panel.status_label.text())

        # 检查状态标签样式
        stylesheet = self.panel.status_label.styleSheet()
        self.assertIn("color: green", stylesheet)

        print("✓ 保存成功反馈测试通过")

    def test_config_persistence(self):
        """测试配置持久化"""
        # 修改配置
        self.panel.rate_input.setText("4.5")
        self.panel.export_rate_input.setText("6.0")
        self.panel.process_input.setText("PersistentApp.exe")

        # 保存配置
        QTest.mouseClick(self.panel.save_button, Qt.LeftButton)
        QApplication.processEvents()

        # 关闭面板
        self.panel.close()

        # 重新创建面板和配置
        from admin_panel import AdminPanel
        from config_manager import ConfigManager

        config2 = ConfigManager()
        panel2 = AdminPanel(config2)

        # 验证配置已持久化
        self.assertEqual(config2.rate, 4.5)
        self.assertEqual(config2.export_rate, 6.0)
        self.assertEqual(config2.process_name, "PersistentApp.exe")

        panel2.close()

        print("✓ 配置持久化测试通过")


def run_admin_tests():
    """运行管理面板测试"""
    print("=" * 60)
    print("管理面板模块测试")
    print("=" * 60)

    # 创建测试套件
    suite = unittest.TestLoader().loadTestsFromTestCase(TestAdminPanel)

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_admin_tests()
    sys.exit(0 if success else 1)
