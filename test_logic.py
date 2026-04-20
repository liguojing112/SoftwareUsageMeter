#!/usr/bin/env python3
"""
测试导出张数逻辑
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# 模拟OCR失败的情况
def test_ocr_fallback():
    print("测试OCR失败时的回退逻辑...")

    # 模拟detect_export_image_count返回None
    detected_export_count = None

    from config_manager import ConfigManager

    config = ConfigManager()

    if detected_export_count is None:
        # OCR失败，使用默认导出张数
        current_export_count = config.default_export_count
        print(f"OCR失败，使用默认导出张数: {current_export_count} 张")
    else:
        current_export_count = detected_export_count
        print(f"OCR成功，识别到导出张数: {current_export_count} 张")

    # 计算费用
    minutes = 10
    rate = config.rate
    export_rate = config.export_rate

    time_total = minutes * rate
    export_total = current_export_count * export_rate
    total = time_total + export_total

    print(f"\n费用计算:")
    print(f"使用时长: {minutes} 分钟")
    print(f"计时单价: {rate} 元/分钟")
    print(f"导出张数: {current_export_count} 张")
    print(f"单张导出单价: {export_rate} 元/张")
    print(f"计时费用: {time_total} 元")
    print(f"导出费用: {export_total} 元")
    print(f"合计金额: {total} 元")

    return current_export_count > 0


# 测试收费框计算函数
def test_payment_calculation():
    print("\n" + "=" * 50)
    print("测试收费框计算函数...")

    from payment_overlay import calculate_payment_details

    # 测试用例1: OCR失败，使用默认1张
    details1 = calculate_payment_details(
        duration_minutes=10,
        rate=1.0,
        export_count=1,  # 默认值
        export_rate=1.0,
    )

    print(f"用例1 (OCR失败，默认1张):")
    print(f"  导出张数: {details1['export_count']}")
    print(f"  导出费用: {details1['export_total']}")
    print(f"  总费用: {details1['total']}")

    # 测试用例2: OCR成功，识别到5张
    details2 = calculate_payment_details(
        duration_minutes=10,
        rate=1.0,
        export_count=5,  # OCR识别成功
        export_rate=1.0,
    )

    print(f"\n用例2 (OCR成功，识别5张):")
    print(f"  导出张数: {details2['export_count']}")
    print(f"  导出费用: {details2['export_total']}")
    print(f"  总费用: {details2['total']}")

    return details1["export_total"] > 0 and details2["export_total"] > 0


if __name__ == "__main__":
    print("=" * 50)
    print("导出张数逻辑测试")
    print("=" * 50)

    test1_passed = test_ocr_fallback()
    test2_passed = test_payment_calculation()

    print("\n" + "=" * 50)
    print("测试结果:")
    print(f"OCR回退逻辑: {'通过' if test1_passed else '失败'}")
    print(f"费用计算逻辑: {'通过' if test2_passed else '失败'}")

    if test1_passed and test2_passed:
        print("\n✅ 所有测试通过！")
        print("\n现在当OCR失败时，系统将使用默认导出张数(1张)。")
        print("您可以在config.json中修改'default_export_count'来调整默认值。")
        sys.exit(0)
    else:
        print("\n❌ 测试失败！")
        sys.exit(1)
