"""
配置管理模块测试
测试密码哈希、配置读写、持久化等功能
"""

import os
import json
import tempfile
import shutil
import sys
import unittest

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_manager import hash_password, verify_password, ConfigManager


class TestPasswordFunctions(unittest.TestCase):
    """测试密码哈希和验证功能"""

    def test_hash_password(self):
        """测试密码哈希"""
        # 测试哈希长度
        hashed = hash_password("test123")
        self.assertEqual(len(hashed), 64)  # SHA-256哈希是64字符十六进制

        # 测试相同密码产生相同哈希
        hashed2 = hash_password("test123")
        self.assertEqual(hashed, hashed2)

        # 测试不同密码产生不同哈希
        hashed3 = hash_password("different")
        self.assertNotEqual(hashed, hashed3)

        print("✓ 密码哈希测试通过")

    def test_verify_password(self):
        """测试密码验证"""
        password = "admin123"
        hashed = hash_password(password)

        # 测试正确密码
        self.assertTrue(verify_password(password, hashed))

        # 测试错误密码
        self.assertFalse(verify_password("wrong", hashed))

        # 测试空密码
        self.assertFalse(verify_password("", hashed))

        print("✓ 密码验证测试通过")


class TestConfigManager(unittest.TestCase):
    """测试配置管理器"""

    def setUp(self):
        """测试前准备"""
        # 创建临时目录
        self.test_dir = tempfile.mkdtemp(prefix="config_test_")
        self.config_path = os.path.join(self.test_dir, "config.json")

        # 保存原始函数
        import config_manager

        self.original_get_app_dir = config_manager.get_app_dir

        # 临时修改函数返回测试目录
        config_manager.get_app_dir = lambda: self.test_dir

        print(f"测试目录: {self.test_dir}")

    def tearDown(self):
        """测试后清理"""
        # 恢复原始函数
        import config_manager

        config_manager.get_app_dir = self.original_get_app_dir

        # 清理临时目录
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_default_config(self):
        """测试默认配置"""
        config = ConfigManager()

        # 检查默认值
        self.assertEqual(config.rate, 1.0)
        self.assertEqual(config.export_rate, 0.0)
        self.assertEqual(config.process_name, "PixCake.exe")
        self.assertIn("导出", config.export_window_keywords)
        self.assertIn("Export", config.export_window_keywords)
        self.assertEqual(config.monitor_interval_ms, 2000)

        print("✓ 默认配置测试通过")

    def test_config_save_load(self):
        """测试配置保存和加载"""
        config = ConfigManager()

        # 修改配置
        config.update(
            {
                "rate": 2.5,
                "export_rate": 3.0,
                "process_name": "TestApp.exe",
                "export_window_keywords": ["保存", "Save"],
                "monitor_interval_ms": 3000,
            }
        )

        # 验证修改生效
        self.assertEqual(config.rate, 2.5)
        self.assertEqual(config.export_rate, 3.0)
        self.assertEqual(config.process_name, "TestApp.exe")
        self.assertIn("保存", config.export_window_keywords)
        self.assertEqual(config.monitor_interval_ms, 3000)

        # 验证配置文件存在
        self.assertTrue(os.path.exists(self.config_path))

        # 重新加载配置验证持久化
        config2 = ConfigManager()
        self.assertEqual(config2.rate, 2.5)
        self.assertEqual(config2.export_rate, 3.0)
        self.assertEqual(config2.process_name, "TestApp.exe")

        print("✓ 配置保存加载测试通过")

    def test_config_partial_update(self):
        """测试部分更新配置"""
        config = ConfigManager()

        # 初始值
        initial_rate = config.rate
        initial_process = config.process_name

        # 只更新部分字段
        config.update({"rate": 3.0})

        # 验证更新字段
        self.assertEqual(config.rate, 3.0)
        # 验证未更新字段保持不变
        self.assertEqual(config.process_name, initial_process)

        print("✓ 部分配置更新测试通过")

    def test_config_file_corruption(self):
        """测试配置文件损坏处理"""
        # 创建损坏的配置文件
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write("{ invalid json }")

        # 应该能处理损坏文件并加载默认配置
        config = ConfigManager()
        self.assertEqual(config.rate, 1.0)  # 默认值

        print("✓ 配置文件损坏处理测试通过")


def run_config_tests():
    """运行配置管理测试"""
    print("=" * 60)
    print("配置管理模块测试")
    print("=" * 60)

    # 创建测试套件
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPasswordFunctions)
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestConfigManager))

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_config_tests()
    sys.exit(0 if success else 1)
