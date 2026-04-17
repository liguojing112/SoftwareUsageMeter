#!/usr/bin/env python3
"""
简单测试脚本 - 避免Unicode编码问题
"""

import os
import sys
import json
import tempfile
import shutil

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_manager import hash_password, verify_password, ConfigManager


def test_password_functions():
    """测试密码功能"""
    print("测试密码哈希和验证...")
    
    # 测试哈希
    hashed = hash_password("test123")
    assert len(hashed) == 64, "哈希长度应为64字符"
    
    # 测试相同密码产生相同哈希
    hashed2 = hash_password("test123")
    assert hashed == hashed2, "相同密码应产生相同哈希"
    
    # 测试不同密码产生不同哈希
    hashed3 = hash_password("different")
    assert hashed != hashed3, "不同密码应产生不同哈希"
    
    # 测试验证
    assert verify_password("test123", hashed), "正确密码应验证通过"
    assert not verify_password("wrong", hashed), "错误密码应验证失败"
    assert not verify_password("", hashed), "空密码应验证失败"
    
    print("  [PASS] 密码功能测试通过")
    return True


def test_config_manager():
    """测试配置管理器"""
    print("测试配置管理器...")
    
    # 创建临时目录
    test_dir = tempfile.mkdtemp(prefix="config_test_")
    
    try:
        # 保存原始函数
        import config_manager
        original_get_app_dir = config_manager.get_app_dir
        
        # 临时修改函数返回测试目录
        config_manager.get_app_dir = lambda: test_dir
        
        # 测试默认配置
        config = ConfigManager()
        assert config.rate == 1.0, "默认费率应为1.0"
        assert config.process_name == "PixCake.exe", "默认进程名应为PixCake.exe"
        assert "导出" in config.export_window_keywords, "应包含中文导出关键词"
        assert "Export" in config.export_window_keywords, "应包含英文导出关键词"
        assert config.monitor_interval_ms == 2000, "默认监控间隔应为2000ms"
        
        print("  [PASS] 默认配置测试通过")
        
        # 测试配置保存和加载
        config.update({
            "rate": 2.5,
            "process_name": "TestApp.exe",
            "export_window_keywords": ["保存", "Save"],
            "monitor_interval_ms": 3000,
        })
        
        assert config.rate == 2.5, "费率更新失败"
        assert config.process_name == "TestApp.exe", "进程名更新失败"
        assert "保存" in config.export_window_keywords, "关键词更新失败"
        assert config.monitor_interval_ms == 3000, "监控间隔更新失败"
        
        # 验证配置文件存在
        config_path = os.path.join(test_dir, "config.json")
        assert os.path.exists(config_path), "配置文件未创建"
        
        # 重新加载配置验证持久化
        config2 = ConfigManager()
        assert config2.rate == 2.5, "配置持久化失败"
        assert config2.process_name == "TestApp.exe", "进程名持久化失败"
        
        print("  [PASS] 配置保存加载测试通过")
        
        # 测试部分更新
        config.update({"rate": 3.0})
        assert config.rate == 3.0, "部分更新失败"
        assert config.process_name == "TestApp.exe", "未更新字段应保持不变"
        
        print("  [PASS] 部分配置更新测试通过")
        
        # 测试配置文件损坏处理
        with open(config_path, "w", encoding="utf-8") as f:
            f.write("{ invalid json }")
        
        config3 = ConfigManager()
        assert config3.rate == 1.0, "损坏文件应加载默认配置"
        
        print("  [PASS] 配置文件损坏处理测试通过")
        
        return True
        
    finally:
        # 恢复原始函数
        import config_manager
        config_manager.get_app_dir = original_get_app_dir
        
        # 清理临时目录
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir, ignore_errors=True)


def main():
    """主测试函数"""
    print("=" * 60)
    print("软件用途计时计费系统 - 简单测试")
    print("=" * 60)
    
    tests = [
        ("密码功能", test_password_functions),
        ("配置管理", test_config_manager),
    ]
    
    results = []
    for name, test_func in tests:
        print(f"\n执行测试: {name}")
        try:
            success = test_func()
            results.append((name, success))
            print(f"  [{'PASS' if success else 'FAIL'}] {name}")
        except Exception as e:
            print(f"  [FAIL] {name} - 错误: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("测试结果:")
    print("=" * 60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "通过" if success else "失败"
        print(f"{name}: {status}")
    
    print(f"\n通过率: {passed}/{total} ({passed/total*100:.1f}%)")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)