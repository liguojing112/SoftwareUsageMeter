"""
运行所有测试
一键运行完整的测试套件
"""

import os
import sys
import subprocess
import time


def print_header(text):
    """打印标题"""
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)


def run_test(test_file, description):
    """运行单个测试文件"""
    print(f"\n▶ {description}")
    print(f"  文件: {test_file}")

    start_time = time.time()

    try:
        # 运行测试
        result = subprocess.run(
            [sys.executable, test_file],
            capture_output=True,
            text=True,
            timeout=30,  # 30秒超时
        )

        elapsed = time.time() - start_time

        if result.returncode == 0:
            print(f"  ✅ 通过 ({elapsed:.1f}秒)")
            return True
        else:
            print(f"  ❌ 失败 ({elapsed:.1f}秒)")
            print(f"  错误输出:\n{result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print(f"  ⏱ 超时 (30秒)")
        return False
    except Exception as e:
        print(f"  💥 异常: {e}")
        return False


def run_unit_tests():
    """运行单元测试"""
    print_header("单元测试")

    tests = [
        ("test_config_manager.py", "配置管理模块测试"),
        ("test_timer_manager.py", "计时器模块测试"),
        ("test_process_monitor.py", "进程监控模块测试"),
    ]

    passed = 0
    failed = 0

    for test_file, description in tests:
        test_path = os.path.join(os.path.dirname(__file__), test_file)
        if run_test(test_path, description):
            passed += 1
        else:
            failed += 1

    return passed, failed


def run_integration_tests():
    """运行集成测试"""
    print_header("集成测试")

    tests = [
        ("test_integration.py", "集成测试"),
    ]

    passed = 0
    failed = 0

    for test_file, description in tests:
        test_path = os.path.join(os.path.dirname(__file__), test_file)
        if run_test(test_path, description):
            passed += 1
        else:
            failed += 1

    return passed, failed


def run_quick_validation():
    """运行快速验证测试"""
    print_header("快速验证测试")

    print("\n1. 验证模块导入")
    try:
        import sys

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        modules = [
            ("config_manager", "ConfigManager"),
            ("timer_manager", "TimerManager"),
            ("process_monitor", "is_process_running"),
            ("payment_overlay", "PaymentOverlay"),
            ("admin_panel", "PasswordDialog"),
            ("tray_icon", "TrayIconManager"),
            ("main", "Application"),
        ]

        for module_name, class_name in modules:
            exec(f"from {module_name} import {class_name}")
            print(f"  ✅ {module_name}.{class_name}")

        print("  ✅ 所有模块导入成功")

    except ImportError as e:
        print(f"  ❌ 模块导入失败: {e}")
        return False

    print("\n2. 验证依赖安装")
    try:
        import PyQt5.QtCore
        import psutil
        import win32gui
        import PIL.Image

        print("  ✅ PyQt5 已安装")
        print("  ✅ psutil 已安装")
        print("  ✅ pywin32 已安装")
        print("  ✅ Pillow 已安装")

    except ImportError as e:
        print(f"  ⚠ 依赖缺失: {e}")
        print("  运行: pip install PyQt5 psutil pywin32 Pillow")

    print("\n3. 验证打包文件")
    exe_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "dist", "SoftwareUsageMeter.exe"
    )
    if os.path.exists(exe_path):
        size = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"  ✅ EXE文件存在: {exe_path}")
        print(f"    文件大小: {size:.1f} MB")
    else:
        print(f"  ⚠ EXE文件不存在")
        print("  运行: pyinstaller build.spec")

    return True


def create_test_summary(
    passed_unit, failed_unit, passed_integration, failed_integration
):
    """创建测试总结"""
    print_header("测试总结")

    total_passed = passed_unit + passed_integration
    total_failed = failed_unit + failed_integration
    total_tests = total_passed + total_failed

    print(f"\n📊 测试结果:")
    print(f"  单元测试: {passed_unit}通过, {failed_unit}失败")
    print(f"  集成测试: {passed_integration}通过, {failed_integration}失败")
    print(f"  总计: {total_passed}通过, {total_failed}失败")

    if total_failed == 0:
        print("\n🎉 所有测试通过！")
        return True
    else:
        print(f"\n⚠ 有 {total_failed} 个测试失败")
        return False


def main():
    """主函数"""
    print_header("计时计费系统 - 完整测试套件")
    print("版本: 1.0")
    print("日期:", time.strftime("%Y-%m-%d %H:%M:%S"))

    # 检查Python版本
    print(f"\nPython版本: {sys.version}")

    # 运行快速验证
    run_quick_validation()

    # 运行单元测试
    passed_unit, failed_unit = run_unit_tests()

    # 运行集成测试
    passed_integration, failed_integration = run_integration_tests()

    # 显示总结
    success = create_test_summary(
        passed_unit, failed_unit, passed_integration, failed_integration
    )

    # 提供下一步建议
    print_header("下一步")

    if success:
        print("\n✅ 所有测试通过，可以进行真实环境测试:")
        print("  1. 双击运行 dist\\SoftwareUsageMeter.exe")
        print("  2. 检查系统托盘图标")
        print("  3. 右键菜单 → '管理设置' (密码: admin)")
        print("  4. 配置实际参数:")
        print("     - 修改进程名为实际像素蛋糕进程名")
        print("     - 修改导出关键词")
        print("     - 上传收款码图片")
        print("  5. 启动像素蛋糕进行真实测试")
    else:
        print("\n⚠ 有测试失败，请先修复问题:")
        print("  1. 检查错误信息")
        print("  2. 确保所有依赖已安装")
        print("  3. 重新运行失败的具体测试")
        print("  4. 修复代码后重新测试")

    print("\n📋 测试文件位置:")
    print(f"  测试目录: {os.path.dirname(__file__)}")
    print(f"  项目目录: {os.path.dirname(os.path.dirname(__file__))}")

    return 0 if success else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试运行出错: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
