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

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QDialogButtonBox,
    QWidget,
    QScrollArea,
)

from config_manager import hash_password, verify_password

# 管理面板表单行：统一增高输入行，避免控件显得过扁过挤
_FORM_INPUT_MIN_HEIGHT = 90
_FORM_LABEL_MIN_WIDTH = 220  # 增加标签宽度
_FORM_FONT = QFont("Microsoft YaHei", 14)


def _form_row_label(text: str) -> QLabel:
    """表单左侧标签：与输入框同高，留出足够列宽，避免整行显得过窄。"""
    label = QLabel(text)
    label.setFont(QFont("Microsoft YaHei", 14))
    label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    label.setMinimumHeight(_FORM_INPUT_MIN_HEIGHT)
    label.setMinimumWidth(_FORM_LABEL_MIN_WIDTH)
    label.setStyleSheet("color: #37474f; padding: 8px 14px 8px 8px;")
    return label


def _apply_form_control_style(widget: QWidget) -> None:
    """为单行输入类控件设置最小高度与内边距。"""
    widget.setMinimumHeight(_FORM_INPUT_MIN_HEIGHT)
    widget.setStyleSheet("padding: 8px 14px; border-radius: 6px;")


class _RateInputAdapter:
    """兼容旧测试与调试代码，用文本方式读写费率输入。"""

    def __init__(self, spin_box: QDoubleSpinBox):
        self._spin_box = spin_box
        self._raw_text = None

    def setText(self, text: str):
        self._raw_text = text
        self._spin_box.lineEdit().setText(text)

    def text(self) -> str:
        raw = self.consume_text()
        try:
            return str(float(raw))
        except ValueError:
            return raw

    def consume_text(self) -> str:
        if self._raw_text is not None:
            return self._raw_text.strip()
        return str(self._spin_box.value())

    def clear(self):
        self._raw_text = None


class PasswordDialog(QDialog):
    """管理员密码验证对话框"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._authenticated = False
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("管理员验证")
        self.setFixedSize(650, 450)  # 协调宽度，与AdminPanel保持更好比例
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(36, 28, 36, 28)

        # 图标/标题
        title = QLabel("🔐 请输入管理员密码")
        title.setFont(QFont("Microsoft YaHei", 17, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("padding: 4px 0 10px 0;")
        layout.addWidget(title)

        # 密码输入
        self._password_input = QLineEdit()
        self._password_input.setEchoMode(QLineEdit.Password)
        self._password_input.setPlaceholderText("请输入密码")
        self._password_input.setFont(QFont("Microsoft YaHei", 14))
        self._password_input.setMinimumHeight(86)
        self._password_input.setStyleSheet("padding: 14px 20px; border-radius: 6px;")
        self._password_input.returnPressed.connect(self._verify)
        layout.addWidget(self._password_input)

        self._status_label = QLabel("")
        self._status_label.setFont(QFont("Microsoft YaHei", 13))  # 稍微增加字体大小
        self._status_label.setStyleSheet("""
            color: #d32f2f; 
            padding: 20px 0 20px 0;  /* 进一步增加内边距 */
            margin: 0;
            border: none;
            background: transparent;
        """)
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setMinimumHeight(75)  # 确保有足够空间
        layout.addWidget(self._status_label)

        layout.addSpacing(4)  # 减少间距，因为状态标签已有足够内边距

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(22)
        btn_layout.setContentsMargins(0, 14, 0, 4)
        cancel_btn = QPushButton("取消")
        cancel_btn.setFont(QFont("Microsoft YaHei", 14))
        cancel_btn.setMinimumHeight(64)
        cancel_btn.setMinimumWidth(132)
        cancel_btn.setStyleSheet("""
            QPushButton {
                padding: 12px 36px;
                border-radius: 6px;
                border: 1px solid #bdbdbd;
                background-color: #fafafa;
            }
            QPushButton:hover { background-color: #eeeeee; }
        """)
        cancel_btn.clicked.connect(self.reject)

        confirm_btn = QPushButton("确认")
        confirm_btn.setFont(QFont("Microsoft YaHei", 14))
        confirm_btn.setMinimumHeight(64)
        confirm_btn.setMinimumWidth(132)
        confirm_btn.setDefault(True)
        confirm_btn.setStyleSheet("""
            QPushButton { background-color: #4CAF50; color: white;
                         border: none; border-radius: 6px; padding: 12px 36px; }
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
            self._status_label.clear()
            self.accept()
        else:
            self._password_input.clear()
            self._status_label.setText("密码错误，请重试。")

    @property
    def authenticated(self) -> bool:
        return self._authenticated


class AdminPanel(QDialog):
    """管理员设置面板"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._rate_input_adapter = None
        self._export_rate_input_adapter = None
        self._init_ui()
        self._load_config()

    def _init_ui(self):
        self.setWindowTitle("管理设置")
        self.resize(1200, 700)  # 进一步减少高度
        self.setMinimumSize(1100, 600)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # 创建内容部件
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(25)  # 减少间距，让布局更紧凑
        layout.setContentsMargins(30, 32, 30, 32)

        scroll_area.setWidget(content_widget)

        # 设置主布局
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(scroll_area)

        # 将按钮放在滚动区域之外，确保始终可见
        self._setup_bottom_buttons(main_layout)

        summary = QLabel("设置会自动保存到本地配置文件，重启软件后继续生效。")
        summary.setFont(QFont("Microsoft YaHei", 13))
        summary.setStyleSheet("color: #607d8b; padding: 6px 0 12px 0;")
        layout.addWidget(summary)

        # === 计费设置 ===
        billing_group = QGroupBox("计费设置")
        billing_group.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        billing_layout = QFormLayout()
        billing_layout.setSpacing(40)  # 减少布局间距
        billing_layout.setVerticalSpacing(50)  # 减少行间垂直间距
        billing_layout.setHorizontalSpacing(24)
        billing_layout.setContentsMargins(12, 26, 12, 22)
        billing_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        billing_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._rate_spin = QDoubleSpinBox()
        self._rate_spin.setRange(0.01, 999.99)
        self._rate_spin.setDecimals(2)
        self._rate_spin.setSuffix(" 元/分钟")
        self._rate_spin.setFont(_FORM_FONT)
        self._rate_spin.setSingleStep(0.5)
        _apply_form_control_style(self._rate_spin)
        billing_layout.addRow(_form_row_label("计时单价："), self._rate_spin)
        self._rate_input_adapter = _RateInputAdapter(self._rate_spin)

        self._export_rate_spin = QDoubleSpinBox()
        self._export_rate_spin.setRange(0.0, 999.99)
        self._export_rate_spin.setDecimals(2)
        self._export_rate_spin.setSuffix(" 元/张")
        self._export_rate_spin.setFont(_FORM_FONT)
        self._export_rate_spin.setSingleStep(0.5)
        _apply_form_control_style(self._export_rate_spin)
        billing_layout.addRow(_form_row_label("单张导出单价："), self._export_rate_spin)
        self._export_rate_input_adapter = _RateInputAdapter(self._export_rate_spin)

        billing_group.setLayout(billing_layout)
        layout.addWidget(billing_group)

        # === 监控设置 ===
        monitor_group = QGroupBox("监控设置")
        monitor_group.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        monitor_layout = QFormLayout()
        monitor_layout.setSpacing(40)  # 减少布局间距
        monitor_layout.setVerticalSpacing(50)  # 减少行间垂直间距
        monitor_layout.setHorizontalSpacing(24)
        monitor_layout.setContentsMargins(12, 30, 12, 26)
        monitor_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        monitor_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._process_input = QLineEdit()
        self._process_input.setFont(_FORM_FONT)
        self._process_input.setPlaceholderText("如：PixCake.exe")
        _apply_form_control_style(self._process_input)
        monitor_layout.addRow(_form_row_label("进程名称："), self._process_input)

        self._keywords_input = QLineEdit()
        self._keywords_input.setFont(_FORM_FONT)
        self._keywords_input.setPlaceholderText("如：导出,Export（逗号分隔）")
        _apply_form_control_style(self._keywords_input)
        monitor_layout.addRow(_form_row_label("导出关键词："), self._keywords_input)

        self._interval_spin = QDoubleSpinBox()
        self._interval_spin.setRange(0.5, 10.0)
        self._interval_spin.setDecimals(1)
        self._interval_spin.setSuffix(" 秒")
        self._interval_spin.setFont(_FORM_FONT)
        self._interval_spin.setSingleStep(0.5)
        _apply_form_control_style(self._interval_spin)
        monitor_layout.addRow(_form_row_label("检测间隔："), self._interval_spin)

        monitor_group.setLayout(monitor_layout)
        layout.addWidget(monitor_group)

        # === 收款码设置 ===
        qr_group = QGroupBox("收款码设置")
        qr_group.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        qr_layout = QVBoxLayout()
        qr_layout.setSpacing(40)  # 减少垂直间距
        qr_layout.setContentsMargins(12, 30, 12, 26)

        qr_path_layout = QHBoxLayout()
        qr_path_layout.setSpacing(12)
        self._qr_path_input = QLineEdit()
        self._qr_path_input.setFont(_FORM_FONT)
        self._qr_path_input.setPlaceholderText("选择收款码图片文件")
        self._qr_path_input.setReadOnly(True)
        _apply_form_control_style(self._qr_path_input)
        qr_path_layout.addWidget(self._qr_path_input)

        browse_btn = QPushButton("浏览...")
        browse_btn.setFont(_FORM_FONT)
        browse_btn.setMinimumHeight(_FORM_INPUT_MIN_HEIGHT)
        browse_btn.setStyleSheet(
            "padding: 16px 24px; border-radius: 4px;"
        )  # 增加内边距
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
        pwd_group.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        pwd_layout = QFormLayout()
        pwd_layout.setSpacing(40)  # 减少布局间距
        pwd_layout.setVerticalSpacing(50)  # 减少行间垂直间距
        pwd_layout.setHorizontalSpacing(24)
        pwd_layout.setContentsMargins(12, 30, 12, 26)
        pwd_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        pwd_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._old_pwd = QLineEdit()
        self._old_pwd.setEchoMode(QLineEdit.Password)
        self._old_pwd.setFont(_FORM_FONT)
        self._old_pwd.setPlaceholderText("输入当前密码")
        _apply_form_control_style(self._old_pwd)
        pwd_layout.addRow(_form_row_label("当前密码："), self._old_pwd)

        self._new_pwd = QLineEdit()
        self._new_pwd.setEchoMode(QLineEdit.Password)
        self._new_pwd.setFont(_FORM_FONT)
        self._new_pwd.setPlaceholderText("输入新密码")
        _apply_form_control_style(self._new_pwd)
        pwd_layout.addRow(_form_row_label("新密码："), self._new_pwd)

        self._confirm_pwd = QLineEdit()
        self._confirm_pwd.setEchoMode(QLineEdit.Password)
        self._confirm_pwd.setFont(_FORM_FONT)
        self._confirm_pwd.setPlaceholderText("再次输入新密码")
        _apply_form_control_style(self._confirm_pwd)
        pwd_layout.addRow(_form_row_label("确认密码："), self._confirm_pwd)

        pwd_group.setLayout(pwd_layout)
        layout.addWidget(pwd_group)

    def _load_config(self):
        """从配置加载到界面"""
        self._rate_spin.setValue(self._config.rate)
        self._rate_input_adapter.clear()
        self._export_rate_spin.setValue(self._config.export_rate)
        self._export_rate_input_adapter.clear()
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
            self,
            "选择收款码图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp);;所有文件 (*.*)",
        )
        if file_path:
            self._qr_path_input.setText(file_path)
            self._preview_qr(file_path)
            self._set_status(
                f"已选择收款码：{os.path.basename(file_path)}", success=True
            )

    def _preview_qr(self, path: str):
        """预览收款码图片"""
        from PyQt5.QtGui import QPixmap

        if os.path.exists(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    110, 110, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                self._qr_preview.setPixmap(scaled)
                return
        self._qr_preview.clear()
        from PyQt5.QtGui import QPixmap, QPainter, QColor

        placeholder = QPixmap(110, 110)
        placeholder.fill(QColor("#f5f5f5"))
        painter = QPainter(placeholder)
        painter.setPen(QColor("#9e9e9e"))
        painter.drawText(placeholder.rect(), Qt.AlignCenter, "未选择\n收款码")
        painter.end()
        self._qr_preview.setPixmap(placeholder)

    def _set_status(self, message: str, success: bool = False):
        color = "green" if success else "#d32f2f"
        self._status_label.setStyleSheet(f"color: {color};")
        self._status_label.setText(message)

    def _save(self):
        """保存设置"""
        rate_text = self._rate_input_adapter.consume_text()
        try:
            rate = float(rate_text)
        except ValueError:
            self._set_status("请输入有效的数字。")
            return

        export_rate_text = self._export_rate_input_adapter.consume_text()
        try:
            export_rate = float(export_rate_text)
        except ValueError:
            self._set_status("请输入有效的单张导出单价。")
            return

        if rate <= 0:
            self._set_status("费率必须大于0。")
            return
        if export_rate < 0:
            self._set_status("单张导出单价不能小于0。")
            return
        self._rate_spin.setValue(rate)
        self._rate_input_adapter.clear()
        self._export_rate_spin.setValue(export_rate)
        self._export_rate_input_adapter.clear()

        # 验证密码修改（如果填写了）
        old_pwd = self._old_pwd.text()
        new_pwd = self._new_pwd.text()
        confirm_pwd = self._confirm_pwd.text()

        if old_pwd or new_pwd or confirm_pwd:
            if not old_pwd:
                self._set_status("请输入当前密码。")
                return
            if not verify_password(old_pwd, self._config.admin_password):
                self._set_status("当前密码错误。")
                return
            if not new_pwd:
                self._set_status("请输入新密码。")
                return
            if new_pwd != confirm_pwd:
                self._set_status("两次输入的新密码不一致。")
                return
            if len(new_pwd) < 4:
                self._set_status("新密码长度不能少于4位。")
                return

        # 保存所有设置
        updates = {
            "rate": rate,
            "export_rate": export_rate,
            "process_name": self._process_input.text().strip(),
            "export_window_keywords": [
                kw.strip()
                for kw in self._keywords_input.text().split(",")
                if kw.strip()
            ],
            "monitor_interval_ms": int(self._interval_spin.value() * 1000),
        }

        # 收款码路径
        qr_path = self._qr_path_input.text().strip()
        if qr_path and not os.path.exists(qr_path):
            self._set_status("收款码图片路径不存在。")
            return
        updates["qr_code_path"] = qr_path

        # 密码修改
        if new_pwd:
            updates["admin_password"] = hash_password(new_pwd)

        # 进程名检查
        if not updates["process_name"]:
            self._set_status("进程名不能为空。")
            return

        # 关键词检查
        if not updates["export_window_keywords"]:
            self._set_status("导出关键词不能为空。")
            return

        self._config.update(updates)
        self._set_status("配置已保存。", success=True)
        QTimer.singleShot(250, self.accept)

    def verify_password(self, password: str) -> bool:
        """兼容测试与调试场景的密码验证入口。"""
        return verify_password(password, self._config.admin_password)

    def change_password(self, new_password: str):
        """兼容测试与调试场景的密码修改入口。"""
        self._config.update({"admin_password": hash_password(new_password)})

    def on_qr_path_changed(self, path: str):
        self._preview_qr(path)

    @property
    def process_input(self) -> QLineEdit:
        return self._process_input

    @property
    def rate_input(self):
        return self._rate_input_adapter

    @property
    def export_rate_input(self):
        return self._export_rate_input_adapter

    @property
    def keywords_input(self) -> QLineEdit:
        return self._keywords_input

    @property
    def qr_path_input(self) -> QLineEdit:
        return self._qr_path_input

    @property
    def save_button(self) -> QPushButton:
        return self._save_button

    @property
    def status_label(self) -> QLabel:
        return self._status_label

    @property
    def qr_preview_label(self) -> QLabel:
        return self._qr_preview

    def _setup_bottom_buttons(self, main_layout):
        """设置底部按钮，确保始终可见"""
        # 状态标签
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setFont(QFont("Microsoft YaHei", 13))
        self._status_label.setStyleSheet("color: #607d8b; padding: 8px 0 4px 0;")
        main_layout.addWidget(self._status_label)

        # 按钮
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.setFont(QFont("Microsoft YaHei", 14))
        btn_box.accepted.connect(self._save)
        btn_box.rejected.connect(self.reject)

        # 设置保存按钮样式
        save_btn = btn_box.button(QDialogButtonBox.Save)
        save_btn.setText("保存设置")
        save_btn.setMinimumHeight(52)
        save_btn.setStyleSheet("""
            QPushButton { background-color: #4CAF50; color: white;
                         border: none; border-radius: 6px; padding: 14px 32px; }
            QPushButton:hover { background-color: #45a049; }
        """)
        cancel_panel_btn = btn_box.button(QDialogButtonBox.Cancel)
        if cancel_panel_btn is not None:
            cancel_panel_btn.setText("取消设置")  # 设置按钮文本
            cancel_panel_btn.setMinimumHeight(52)
            cancel_panel_btn.setStyleSheet("padding: 14px 28px; border-radius: 6px;")
        self._save_button = save_btn

        main_layout.addWidget(btn_box)
