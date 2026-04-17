"""
配置管理模块 - 基于 JSON 的配置持久化
支持：计时单价、管理员密码（哈希）、收款码图片路径、进程名、导出检测关键词
"""

import json
import hashlib
import os
import sys


def get_app_dir():
    """获取应用所在目录（兼容 PyInstaller 打包后的路径）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def hash_password(password: str) -> str:
    """对密码进行 SHA-256 哈希"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    """验证密码是否匹配"""
    return hash_password(password) == hashed


DEFAULT_CONFIG = {
    "rate": 1.0,                    # 计时单价（元/分钟）
    "admin_password": hash_password("admin"),  # 默认密码: admin
    "qr_code_path": "",             # 收款码图片路径
    "process_name": "PixCake.exe",  # 像素蛋糕进程名
    "export_window_keywords": ["导出", "Export"],  # 导出窗口关键词
    "monitor_interval_ms": 2000,    # 进程监控间隔（毫秒）
}


class ConfigManager:
    """配置管理器，负责读取和保存配置"""

    def __init__(self):
        self._config_path = os.path.join(get_app_dir(), "config.json")
        self._config = {}
        self.load()

    def load(self):
        """从文件加载配置，不存在则使用默认值"""
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                # 合并：已保存的值覆盖默认值，新增字段使用默认值
                self._config = {**DEFAULT_CONFIG, **saved}
            except (json.JSONDecodeError, IOError):
                self._config = DEFAULT_CONFIG.copy()
        else:
            self._config = DEFAULT_CONFIG.copy()

    def save(self):
        """保存配置到文件"""
        with open(self._config_path, 'w', encoding='utf-8') as f:
            json.dump(self._config, f, ensure_ascii=False, indent=2)

    def get(self, key, default=None):
        """获取配置值"""
        return self._config.get(key, default)

    def set(self, key, value):
        """设置配置值并自动保存"""
        self._config[key] = value
        self.save()

    def update(self, data: dict):
        """批量更新配置并保存"""
        self._config.update(data)
        self.save()

    @property
    def rate(self) -> float:
        return float(self._config.get("rate", 1.0))

    @property
    def admin_password(self) -> str:
        return self._config.get("admin_password", hash_password("admin"))

    @property
    def qr_code_path(self) -> str:
        return self._config.get("qr_code_path", "")

    @property
    def process_name(self) -> str:
        return self._config.get("process_name", "PixCake.exe")

    @property
    def export_window_keywords(self) -> list:
        return self._config.get("export_window_keywords", ["导出", "Export"])

    @property
    def monitor_interval_ms(self) -> int:
        return int(self._config.get("monitor_interval_ms", 2000))
