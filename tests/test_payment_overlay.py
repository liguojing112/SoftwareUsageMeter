"""
收费弹窗模块测试
测试全屏置顶显示、信息更新、交互功能
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication, QLabel
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap


class TestPaymentOverlay(unittest.TestCase):
    """测试收费弹窗"""

    @classmethod
    def setUpClass(cls):
        """类级别设置 - 创建Qt应用"""
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        """测试前准备"""
        from payment_overlay import PaymentOverlay

        # 创建临时目录用于测试图片
        self.test_dir = tempfile.mkdtemp(prefix="payment_test_")
        self.test_qr_path = os.path.join(self.test_dir, "test_qr.png")

        # 创建测试图片
        pixmap = QPixmap(200, 200)
        pixmap.fill(Qt.white)
        pixmap.save(self.test_qr_path)

        # 创建弹窗实例
        self.overlay = PaymentOverlay(qr_code_path=self.test_qr_path)

        # 模拟信号
        self.payment_completed = False
        self.overlay.payment_completed.connect(lambda: self._on_payment_completed())

    def _on_payment_completed(self):
        """支付完成信号处理"""
        self.payment_completed = True

    def tearDown(self):
        """测试后清理"""
        self.overlay.close()

        # 清理临时目录
        import shutil

        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_window_properties(self):
        """测试窗口属性"""
        # 检查窗口标志
        flags = self.overlay.windowFlags()

        # 应包含全屏和置顶标志
        self.assertTrue(flags & Qt.Window)
        self.assertTrue(flags & Qt.FramelessWindowHint)
        self.assertTrue(flags & Qt.WindowStaysOnTopHint)
        self.assertTrue(flags & Qt.Tool)

        # 检查透明度
        self.assertTrue(self.overlay.testAttribute(Qt.WA_TranslucentBackground))

        print("✓ 窗口属性测试通过")

    def test_initial_display(self):
        """测试初始显示"""
        # 检查初始文本
        self.assertEqual(self.overlay.duration_label.text(), "使用时长: 0分钟")
        self.assertEqual(self.overlay.rate_label.text(), "单价: ¥1.0/分钟")
        self.assertEqual(self.overlay.amount_label.text(), "应付金额: ¥0.0")

        # 检查支付按钮文本
        self.assertEqual(self.overlay.pay_button.text(), "已支付")

        # 检查收款码显示
        self.assertIsNotNone(self.overlay.qr_label.pixmap())

        print("✓ 初始显示测试通过")

    def test_update_display(self):
        """测试信息更新"""
        # 更新时长和费率
        self.overlay.update_display(duration_minutes=5, rate=2.0)

        # 检查更新后的文本
        self.assertEqual(self.overlay.duration_label.text(), "使用时长: 5分钟")
        self.assertEqual(self.overlay.rate_label.text(), "单价: ¥2.0/分钟")
        self.assertEqual(self.overlay.amount_label.text(), "应付金额: ¥10.0")

        print("✓ 信息更新测试通过")

    def test_payment_button(self):
        """测试支付按钮"""
        # 初始状态
        self.assertFalse(self.payment_completed)

        # 模拟点击支付按钮
        self.overlay.pay_button.click()

        # 处理事件
        QApplication.processEvents()

        # 应触发支付完成信号
        self.assertTrue(self.payment_completed)

        print("✓ 支付按钮测试通过")

    def test_keyboard_shortcuts(self):
        """测试键盘快捷键"""
        # 测试ESC键关闭
        with patch.object(self.overlay, "close") as mock_close:
            event = Mock(key=lambda: Qt.Key_Escape)
            self.overlay.keyPressEvent(event)
            mock_close.assert_called_once()

        # 测试Enter键支付
        with patch.object(self.overlay.pay_button, "click") as mock_click:
            event = Mock(key=lambda: Qt.Key_Return)
            self.overlay.keyPressEvent(event)
            mock_click.assert_called_once()

        print("✓ 键盘快捷键测试通过")

    def test_close_event(self):
        """测试关闭事件"""
        # 模拟关闭事件
        event = Mock()
        event.accept = Mock()

        # 调用关闭事件处理
        self.overlay.closeEvent(event)

        # 应阻止关闭
        event.ignore.assert_called_once()

        print("✓ 关闭事件测试通过")

    def test_qr_code_loading(self):
        """测试收款码加载"""
        # 测试有效图片加载
        overlay = PaymentOverlay(qr_code_path=self.test_qr_path)
        self.assertIsNotNone(overlay.qr_label.pixmap())
        overlay.close()

        # 测试无效图片路径（应使用默认占位图）
        overlay2 = PaymentOverlay(qr_code_path="nonexistent.png")
        self.assertIsNotNone(overlay2.qr_label.pixmap())
        overlay2.close()

        print("✓ 收款码加载测试通过")

    def test_visual_appearance(self):
        """测试视觉效果"""
        # 检查字体大小
        font = self.overlay.duration_label.font()
        self.assertGreaterEqual(font.pointSize(), 20)  # 大字体

        # 检查颜色
        stylesheet = self.overlay.styleSheet()
        self.assertIn("background-color", stylesheet)
        self.assertIn("color", stylesheet)

        # 检查布局
        self.assertIsNotNone(self.overlay.central_layout)
        self.assertEqual(
            self.overlay.central_layout.count(), 5
        )  # 标题 + 时长 + 单价 + 金额 + 按钮 + 二维码

        print("✓ 视觉效果测试通过")

    def test_fullscreen_display(self):
        """测试全屏显示"""
        # 显示窗口
        self.overlay.show()
        QApplication.processEvents()

        # 检查窗口大小
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        self.assertEqual(self.overlay.geometry(), screen_geometry)

        # 检查置顶
        self.assertTrue(self.overlay.isTopLevel())

        print("✓ 全屏显示测试通过")


def run_payment_tests():
    """运行收费弹窗测试"""
    print("=" * 60)
    print("收费弹窗模块测试")
    print("=" * 60)

    # 创建测试套件
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPaymentOverlay)

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_payment_tests()
    sys.exit(0 if success else 1)
