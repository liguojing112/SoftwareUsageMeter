"""
管理员设置面板 - 密码保护的配置界面
功能：
1. 密码验证入口
2. 计时单价设置
3. 管理员密码修改
4. 收款码图片更换
5. 进程名配置
6. 导出检测关键词配置
"""

import os

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QDoubleSpinBox,
    QFileDialog, QMessageBox, QGroupBox, QCheckBox,
    QListWidget, QDialogButtonBox, QApplication
)

from config_manager import hash_password, verify_password


class PasswordDialog(QDialog):
    """管理员密码验证对话框"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._authenticated = False
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("管理员验证")
        self.setFixedSize(400, 200)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(20)

        # 图标/标题
        title = QLabel("🔐 请输入管理员密码")
        title.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 密码输入
        self._password_input = QLineEdit()
        self._password_input.setEchoMode(QLineEdit.Password)
        self._password_input.setPlaceholderText("请输入密码")
        self._password_input.setFont(QFont("Microsoft YaHei", 14))
        self._password_input.returnPressed.connect(self._verify)
        layout.addWidget(self._password_input)

        # 按钮
        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        cancel_btn.setFont(QFont("Microsoft YaHei", 12))
        cancel_btn.clicked.connect(self.reject)

        confirm_btn = QPushButton("确认")
        confirm_btn.setFont(QFont("Microsoft YaHei", 12))
        confirm_btn.setDefault(True)
        confirm_btn.setStyleSheet("""
            QPushButton { background-color: #4CAF50; color: white; 
                         border: none; border-radius: 5px; padding: 8px 24px; }
            QPushButton:hover { background-color: #45a049; }
        """)
        confirm_btn.clicked.connect(self._verify)

        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(confirm_btn)
        layout.addLayout(btn_layout)

    def _verify(self):
        """验证密码"""
        password = self._password_input.text()
        if verify_password(password, self._config.admin_password):
            self._authenticated = True
            self.accept()
        else:
            self._password_input.clear()
            QMessageBox.warning(self, "验证失败", "密码错误，请重试！")

    @property
    def authenticated(self) -> bool:
        return self._authenticated


class AdminPanel(QDialog):
    """管理员设置面板"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._init_ui()
        self._load_config()

    def _init_ui(self):
        self.setWindowTitle("管理设置")
        self.setFixedSize(550, 620)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # === 计费设置 ===
        billing_group = QGroupBox("计费设置")
        billing_group.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        billing_layout = QFormLayout()
        billing_layout.setSpacing(12)

        self._rate_spin = QDoubleSpinBox()
        self._rate_spin.setRange(0.01, 999.99)
        self._rate_spin.setDecimals(2)
        self._rate_spin.setSuffix(" 元/分钟")
        self._rate_spin.setFont(QFont("Microsoft YaHei", 12))
        self._rate_spin.setSingleStep(0.5)
        billing_layout.addRow("计时单价：", self._rate_spin)

        billing_group.setLayout(billing_layout)
        layout.addWidget(billing_group)

        # === 监控设置 ===
        monitor_group = QGroupBox("监控设置")
        monitor_group.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        monitor_layout = QFormLayout()
        monitor_layout.setSpacing(12)

        self._process_input = QLineEdit()
        self._process_input.setFont(QFont("Microsoft YaHei", 12))
        self._process_input.setPlaceholderText("如：PixCake.exe")
        monitor_layout.addRow("进程名称：", self._process_input)

        self._keywords_input = QLineEdit()
        self._keywords_input.setFont(QFont("Microsoft YaHei", 12))
        self._keywords_input.setPlaceholderText("如：导出,Export（逗号分隔）")
        monitor_layout.addRow("导出关键词：", self._keywords_input)

        self._interval_spin = QDoubleSpinBox()
        self._interval_spin.setRange(0.5, 10.0)
        self._interval_spin.setDecimals(1)
        self._interval_spin.setSuffix(" 秒")
        self._interval_spin.setFont(QFont("Microsoft YaHei", 12))
        self._interval_spin.setSingleStep(0.5)
        monitor_layout.addRow("检测间隔：", self._interval_spin)

        monitor_group.setLayout(monitor_layout)
        layout.addWidget(monitor_group)

        # === 收款码设置 ===
        qr_group = QGroupBox("收款码设置")
        qr_group.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        qr_layout = QVBoxLayout()
        qr_layout.setSpacing(10)

        qr_path_layout = QHBoxLayout()
        self._qr_path_input = QLineEdit()
        self._qr_path_input.setFont(QFont("Microsoft YaHei", 12))
        self._qr_path_input.setPlaceholderText("选择收款码图片文件")
        self._qr_path_input.setReadOnly(True)
        qr_path_layout.addWidget(self._qr_path_input)

        browse_btn = QPushButton("浏览...")
        browse_btn.setFont(QFont("Microsoft YaHei", 12))
        browse_btn.clicked.connect(self._browse_qr_code)
        qr_path_layout.addWidget(browse_btn)
        qr_layout.addLayout(qr_path_layout)

        self._qr_preview = QLabel()
        self._qr_preview.setFixedSize(120, 120)
        self._qr_preview.setStyleSheet("border: 1px solid #ccc; background: #f5f5f5;")
        self._qr_preview.setAlignment(Qt.AlignCenter)
        self._qr_preview.setScaledContents(True)
        qr_layout.addWidget(self._qr_preview, alignment=Qt.AlignCenter)

        qr_group.setLayout(qr_layout)
        layout.addWidget(qr_group)

        # === 密码修改 ===
        pwd_group = QGroupBox("修改管理员密码")
        pwd_group.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        pwd_layout = QFormLayout()
        pwd_layout.setSpacing(10)

        self._old_pwd = QLineEdit()
        self._old_pwd.setEchoMode(QLineEdit.Password)
        self._old_pwd.setFont(QFont("Microsoft YaHei", 12))
        self._old_pwd.setPlaceholderText("输入当前密码")
        pwd_layout.addRow("当前密码：", self._old_pwd)

        self._new_pwd = QLineEdit()
        self._new_pwd.setEchoMode(QLineEdit.Password)
        self._new_pwd.setFont(QFont("Microsoft YaHei", 12))
        self._new_pwd.setPlaceholderText("输入新密码")
        pwd_layout.addRow("新密码：", self._new_pwd)

        self._confirm_pwd = QLineEdit()
        self._confirm_pwd.setEchoMode(QLineEdit.Password)
        self._confirm_pwd.setFont(QFont("Microsoft YaHei", 12))
        self._confirm_pwd.setPlaceholderText("再次输入新密码")
        pwd_layout.addRow("确认密码：", self._confirm_pwd)

        pwd_group.setLayout(pwd_layout)
        layout.addWidget(pwd_group)

        # === 底部按钮 ===
        btn_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        btn_box.setFont(QFont("Microsoft YaHei", 12))
        btn_box.accepted.connect(self._save)
        btn_box.rejected.connect(self.reject)

        # 设置保存按钮样式
        save_btn = btn_box.button(QDialogButtonBox.Save)
        save_btn.setText("保存设置")
        save_btn.setStyleSheet("""
            QPushButton { background-color: #4CAF50; color: white;
                         border: none; border-radius: 5px; padding: 8px 24px; }
            QPushButton:hover { background-color: #45a049; }
        """)

        layout.addWidget(btn_box)

    def _load_config(self):
        """从配置加载到界面"""
        self._rate_spin.setValue(self._config.rate)
        self._process_input.setText(self._config.process_name)
        self._keywords_input.setText(",".join(self._config.export_window_keywords))
        self._interval_spin.setValue(self._config.monitor_interval_ms / 1000.0)

        qr_path = self._config.qr_code_path
        if qr_path:
            self._qr_path_input.setText(qr_path)
            self._preview_qr(qr_path)

    def _browse_qr_code(self):
        """浏览选择收款码图片"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择收款码图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp);;所有文件 (*.*)"
        )
        if file_path:
            self._qr_path_input.setText(file_path)
            self._preview_qr(file_path)

    def _preview_qr(self, path: str):
        """预览收款码图片"""
        from PyQt5.QtGui import QPixmap
        if os.path.exists(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(110, 110, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self._qr_preview.setPixmap(scaled)
                return
        self._qr_preview.clear()
        self._qr_preview.setText("预览失败")

    def _save(self):
        """保存设置"""
        # 验证密码修改（如果填写了）
        old_pwd = self._old_pwd.text()
        new_pwd = self._new_pwd.text()
        confirm_pwd = self._confirm_pwd.text()

        if old_pwd or new_pwd or confirm_pwd:
            if not old_pwd:
                QMessageBox.warning(self, "提示", "请输入当前密码！")
                return
            if not verify_password(old_pwd, self._config.admin_password):
                QMessageBox.warning(self, "提示", "当前密码错误！")
                return
            if not new_pwd:
                QMessageBox.warning(self, "提示", "请输入新密码！")
                return
            if new_pwd != confirm_pwd:
                QMessageBox.warning(self, "提示", "两次输入的新密码不一致！")
                return
            if len(new_pwd) < 4:
                QMessageBox.warning(self, "提示", "新密码长度不能少于4位！")
                return

        # 保存所有设置
        updates = {
            "rate": self._rate_spin.value(),
            "process_name": self._process_input.text().strip(),
            "export_window_keywords": [
                kw.strip() for kw in self._keywords_input.text().split(",")
                if kw.strip()
            ],
            "monitor_interval_ms": int(self._interval_spin.value() * 1000),
        }

        # 收款码路径
        qr_path = self._qr_path_input.text().strip()
        if qr_path and not os.path.exists(qr_path):
            QMessageBox.warning(self, "提示", "收款码图片路径不存在！")
            return
        updates["qr_code_path"] = qr_path

        # 密码修改
        if new_pwd:
            updates["admin_password"] = hash_password(new_pwd)

        # 进程名检查
        if not updates["process_name"]:
            QMessageBox.warning(self, "提示", "进程名称不能为空！")
            return

        # 关键词检查
        if not updates["export_window_keywords"]:
            QMessageBox.warning(self, "提示", "导出关键词不能为空！")
            return

        self._config.update(updates)
        QMessageBox.information(self, "提示", "设置已保存！")
        self.accept()
