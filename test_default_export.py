#!/usr/bin/env python3
"""
测试默认导出张数功能
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_manager import ConfigManager

print("测试默认导出张数配置...")
config = ConfigManager()

print(f"导出费率: {config.export_rate}")
print(f"默认导出张数: {config.default_export_count}")
print(f"配置文件路径: {config._config_path}")

# 计算示例费用
minutes = 5
export_count = config.default_export_count
rate = config.rate
export_rate = config.export_rate

time_total = minutes * rate
export_total = export_count * export_rate
total = time_total + export_total

print(f"\n示例计算:")
print(f"使用时长: {minutes} 分钟")
print(f"计时单价: ¥{rate:.2f}/分钟")
print(f"导出张数: {export_count} 张")
print(f"单张导出单价: ¥{export_rate:.2f}/张")
print(f"计时费用: ¥{time_total:.2f}")
print(f"导出费用: ¥{export_total:.2f}")
print(f"合计金额: ¥{total:.2f}")

print("\n✅ 配置加载成功！")
