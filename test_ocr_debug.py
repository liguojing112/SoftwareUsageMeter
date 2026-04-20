#!/usr/bin/env python3
"""
OCR调试脚本 - 用于测试导出张数识别功能
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging

logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

from process_monitor import extract_export_image_count_from_text


def test_ocr_patterns():
    """测试各种OCR文本模式"""
    test_cases = [
        ("快 速 导 出\n导 出 12 张 图 片", 12, "标准格式"),
        ("精 修 效 果 图 （ 2 ） 免费 效 果 图 （ 1 ） 原 图 （ 0 ）", 3, "分类统计"),
        ("导出5张", 5, "简单格式"),
        ("图片3张", 3, "倒序格式"),
        ("共8张图片", 8, "总计格式"),
        ("总计10张", 10, "总计格式2"),
        ("精修(2)免费(1)原图(0)", 3, "无空格分类"),
        ("导出 15 张", 15, "带空格"),
        ("15张图片", 15, "纯数字+张图片"),
        ("图片 20 张", 20, "图片+数字+张"),
        ("未检测到导出数量", None, "无数字"),
        ("", None, "空文本"),
    ]

    print("=" * 60)
    print("OCR模式匹配测试")
    print("=" * 60)

    all_passed = True
    for text, expected, description in test_cases:
        result = extract_export_image_count_from_text(text)
        passed = result == expected
        status = "✓" if passed else "✗"

        status_char = "PASS" if passed else "FAIL"
        print(f"{status_char} {description:20} | 输入: '{text[:30]}...'")
        print(f"  期望: {expected}, 实际: {result}")
        if not passed:
            all_passed = False
            print(f"  失败!")
        print()

    return all_passed


if __name__ == "__main__":
    print("开始OCR调试测试...")
    success = test_ocr_patterns()

    if success:
        print("所有测试通过！")
        sys.exit(0)
    else:
        print("部分测试失败！")
        sys.exit(1)
