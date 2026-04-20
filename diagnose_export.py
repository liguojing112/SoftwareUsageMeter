#!/usr/bin/env python3
"""
导出张数识别诊断脚本
用于诊断为什么OCR无法识别导出张数
"""

import sys
import os
import logging
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 设置详细日志
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("diagnose_export.log", encoding="utf-8"),
    ],
)

logger = logging.getLogger("DiagnoseExport")


def test_capture_and_ocr():
    """测试截图和OCR功能"""
    try:
        from process_monitor import (
            capture_window_image,
            run_windows_ocr,
            detect_export_image_count,
            find_main_window,
            get_process_pid_by_name,
        )

        print("=" * 60)
        print("导出张数识别诊断")
        print("=" * 60)

        # 1. 查找目标进程
        print("\n1. 查找目标进程...")
        pid = get_process_pid_by_name("PixCake.exe")
        if pid:
            print(f"   找到进程 PID: {pid}")
        else:
            print("   ❌ 未找到 PixCake.exe 进程")
            return False

        # 2. 查找主窗口
        print("\n2. 查找主窗口...")
        main_hwnd = find_main_window(pid)
        if main_hwnd:
            print(f"   找到主窗口句柄: {main_hwnd}")
        else:
            print("   ❌ 未找到主窗口")
            return False

        # 3. 测试截图
        print("\n3. 测试截图...")
        try:
            from PIL import Image

            image = capture_window_image(main_hwnd)
            if image:
                width, height = image.size
                print(f"   截图成功: {width}x{height}")

                # 保存截图供检查
                screenshot_path = "debug_screenshot.png"
                image.save(screenshot_path)
                print(f"   截图已保存到: {screenshot_path}")

                # 显示图像信息
                print(f"   图像模式: {image.mode}")
                print(
                    f"   图像格式: {image.format if hasattr(image, 'format') else 'N/A'}"
                )

                # 检查图像是否全黑/全白
                from PIL import ImageStat

                stat = ImageStat.Stat(image)
                print(
                    f"   图像亮度统计: 均值={stat.mean[0]:.1f}, 标准差={stat.stddev[0]:.1f}"
                )
            else:
                print("   ❌ 截图失败: 返回 None")
                return False
        except Exception as e:
            print(f"   ❌ 截图异常: {e}")
            import traceback

            traceback.print_exc()
            return False

        # 4. 测试OCR
        print("\n4. 测试OCR...")
        try:
            # 保存临时图像文件
            with tempfile.NamedTemporaryFile(
                prefix="ocr_test_", suffix=".png", delete=False
            ) as f:
                temp_path = f.name
                image.save(temp_path, format="PNG")

            print(f"   临时图像文件: {temp_path}")

            # 运行OCR
            ocr_text = run_windows_ocr(temp_path)
            print(f"   OCR结果: '{ocr_text}'")
            print(f"   OCR文本长度: {len(ocr_text)}")

            # 清理临时文件
            os.unlink(temp_path)

            if ocr_text:
                print("   ✅ OCR成功获取文本")
            else:
                print("   ❌ OCR返回空文本")
                return False

        except Exception as e:
            print(f"   ❌ OCR异常: {e}")
            import traceback

            traceback.print_exc()
            return False

        # 5. 测试完整的导出张数识别
        print("\n5. 测试完整的导出张数识别...")
        try:
            export_count = detect_export_image_count(main_hwnd)
            print(f"   识别到的导出张数: {export_count}")

            if export_count is not None:
                print(f"   ✅ 成功识别导出张数: {export_count}")
                return True
            else:
                print("   ❌ 未识别到导出张数")
                return False

        except Exception as e:
            print(f"   ❌ 导出张数识别异常: {e}")
            import traceback

            traceback.print_exc()
            return False

    except ImportError as e:
        print(f"❌ 导入模块失败: {e}")
        return False


def test_windows_ocr_directly():
    """直接测试Windows OCR引擎"""
    print("\n" + "=" * 60)
    print("直接测试Windows OCR引擎")
    print("=" * 60)

    try:
        from process_monitor import run_windows_ocr

        # 创建一个简单的测试图像
        from PIL import Image, ImageDraw, ImageFont
        import tempfile

        # 创建测试图像
        img = Image.new("RGB", (400, 200), color="white")
        draw = ImageDraw.Draw(img)

        try:
            # 尝试使用系统字体
            font = ImageFont.truetype("msyh.ttc", 24)  # 微软雅黑
        except:
            font = ImageFont.load_default()

        # 在图像上写测试文本
        test_text = "导出 5 张图片"
        draw.text((50, 80), test_text, fill="black", font=font)

        # 保存并测试OCR
        with tempfile.NamedTemporaryFile(
            prefix="ocr_test_", suffix=".png", delete=False
        ) as f:
            temp_path = f.name
            img.save(temp_path, format="PNG")

        print(f"   创建测试图像: {temp_path}")
        print(f"   图像内容: '{test_text}'")

        # 运行OCR
        ocr_text = run_windows_ocr(temp_path)
        print(f"   OCR结果: '{ocr_text}'")

        # 清理
        os.unlink(temp_path)

        if test_text in ocr_text or "导出" in ocr_text or "5" in ocr_text:
            print("   ✅ Windows OCR引擎工作正常")
            return True
        else:
            print("   ❌ Windows OCR引擎可能有问题")
            return False

    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def check_system_requirements():
    """检查系统要求"""
    print("\n" + "=" * 60)
    print("系统要求检查")
    print("=" * 60)

    requirements = {
        "Python Pillow": False,
        "Windows OCR支持": False,
        "pywin32": False,
    }

    try:
        from PIL import Image

        requirements["Python Pillow"] = True
        print("   ✅ Python Pillow 已安装")
    except ImportError:
        print("   ❌ Python Pillow 未安装")

    try:
        import win32gui
        import win32con

        requirements["pywin32"] = True
        print("   ✅ pywin32 已安装")
    except ImportError:
        print("   ❌ pywin32 未安装")

    # 检查Windows版本（Windows 10+ 有内置OCR）
    import platform

    win_version = platform.version()
    print(f"   Windows版本: {win_version}")

    if int(win_version.split(".")[0]) >= 10:
        requirements["Windows OCR支持"] = True
        print("   ✅ Windows 10+ (支持内置OCR)")
    else:
        print("   ❌ Windows版本可能不支持内置OCR")

    return all(requirements.values())


if __name__ == "__main__":
    print("开始导出张数识别诊断...")

    # 检查系统要求
    system_ok = check_system_requirements()

    if not system_ok:
        print("\n❌ 系统要求不满足，请先安装缺失的依赖")
        sys.exit(1)

    # 测试Windows OCR引擎
    ocr_ok = test_windows_ocr_directly()

    if not ocr_ok:
        print("\n❌ Windows OCR引擎测试失败")
        print("建议: 检查Windows OCR功能是否启用")
        print("      控制面板 > 轻松使用 > 语音识别 > 文本到语音")
        sys.exit(1)

    # 测试完整的截图和OCR流程
    capture_ok = test_capture_and_ocr()

    if capture_ok:
        print("\n✅ 诊断完成: 所有测试通过")
        print("\n建议下一步:")
        print("1. 检查 debug_screenshot.png 文件，确认截图是否正确")
        print("2. 如果截图正确但OCR失败，可能是导出窗口文本格式问题")
        print("3. 考虑添加手动导出张数输入功能作为备选方案")
    else:
        print("\n❌ 诊断失败: 发现问题")
        print("\n可能的原因:")
        print("1. 目标窗口可能被遮挡或最小化")
        print("2. 截图功能可能有问题")
        print("3. 导出窗口可能没有显示预期的文本")
        print("\n建议:")
        print("1. 确保像素蛋糕导出窗口完全可见")
        print("2. 检查 debug_screenshot.png 文件")
        print("3. 考虑实现手动导出张数输入功能")

    sys.exit(0 if capture_ok else 1)
