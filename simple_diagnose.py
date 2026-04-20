#!/usr/bin/env python3
"""
简单诊断脚本 - 测试OCR和截图功能
"""

import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("简单诊断脚本 - 测试OCR和截图功能")
print("=" * 60)

# 1. 检查依赖
print("\n1. 检查依赖...")
try:
    from PIL import Image

    print("   [OK] Python Pillow 已安装")
except ImportError:
    print("   [ERROR] Python Pillow 未安装")
    sys.exit(1)

try:
    import win32gui
    import win32con

    print("   [OK] pywin32 已安装")
except ImportError:
    print("   [ERROR] pywin32 未安装")
    sys.exit(1)

# 2. 测试Windows OCR
print("\n2. 测试Windows OCR引擎...")
try:
    from process_monitor import run_windows_ocr

    # 创建测试图像
    img = Image.new("RGB", (400, 200), color="white")
    from PIL import ImageDraw, ImageFont

    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("msyh.ttc", 24)
    except:
        font = ImageFont.load_default()

    test_text = "测试OCR 导出5张"
    draw.text((50, 80), test_text, fill="black", font=font)

    with tempfile.NamedTemporaryFile(
        prefix="ocr_test_", suffix=".png", delete=False
    ) as f:
        temp_path = f.name
        img.save(temp_path, format="PNG")

    print(f"   创建测试图像: {temp_path}")

    ocr_text = run_windows_ocr(temp_path)
    print(f"   OCR结果: '{ocr_text}'")

    os.unlink(temp_path)

    if ocr_text and (test_text in ocr_text or "导出" in ocr_text or "5" in ocr_text):
        print("   [OK] Windows OCR引擎工作正常")
    else:
        print("   [WARNING] OCR结果不理想，但引擎在工作")

except Exception as e:
    print(f"   [ERROR] OCR测试失败: {e}")
    import traceback

    traceback.print_exc()

# 3. 测试截图功能
print("\n3. 测试截图功能...")
try:
    from process_monitor import (
        capture_window_image,
        find_main_window,
        get_process_pid_by_name,
    )

    pid = get_process_pid_by_name("PixCake.exe")
    if pid:
        print(f"   找到PixCake.exe进程: PID={pid}")

        main_hwnd = find_main_window(pid)
        if main_hwnd:
            print(f"   找到主窗口: HWND={main_hwnd}")

            # 尝试截图
            image = capture_window_image(main_hwnd)
            if image:
                width, height = image.size
                print(f"   截图成功: {width}x{height}")

                # 保存截图
                screenshot_path = "test_screenshot.png"
                image.save(screenshot_path)
                print(f"   截图已保存: {screenshot_path}")

                # 检查图像内容
                from PIL import ImageStat

                stat = ImageStat.Stat(image)
                print(f"   图像亮度: 均值={stat.mean[0]:.1f}")

                if stat.mean[0] < 10:
                    print("   [WARNING] 图像可能太暗或全黑")
                elif stat.mean[0] > 240:
                    print("   [WARNING] 图像可能太亮或全白")
                else:
                    print("   [OK] 图像亮度正常")
            else:
                print("   [ERROR] 截图返回None")
        else:
            print("   [WARNING] 未找到主窗口，可能窗口被最小化或隐藏")
    else:
        print("   [INFO] PixCake.exe未运行，跳过截图测试")

except Exception as e:
    print(f"   [ERROR] 截图测试失败: {e}")
    import traceback

    traceback.print_exc()

# 4. 检查导出窗口关键词
print("\n4. 检查导出窗口关键词配置...")
try:
    from config_manager import ConfigManager

    config = ConfigManager()
    keywords = config.get("export_window_keywords", ["导出", "Export"])
    print(f"   导出窗口关键词: {keywords}")
    print("   [OK] 配置加载正常")
except Exception as e:
    print(f"   [ERROR] 配置检查失败: {e}")

print("\n" + "=" * 60)
print("诊断完成")
print("=" * 60)
print("\n建议:")
print("1. 检查 test_screenshot.png 文件，确认截图是否正确")
print("2. 如果OCR失败，尝试:")
print("   - 确保Windows OCR功能已启用")
print("   - 检查控制面板 > 轻松使用 > 语音识别")
print("3. 如果问题持续，考虑实现手动输入导出张数功能")
