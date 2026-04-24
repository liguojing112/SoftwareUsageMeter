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
import sys

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPixmap, QPainter, QColor
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
    QFrame,
    QGraphicsDropShadowEffect,
)

ENABLE_UI_SHADOWS = not getattr(sys, "frozen", False)

from config_manager import hash_password, verify_password

# 管理面板表单行：统一增高输入行，避免控件显得过扁过挤
_FORM_INPUT_MIN_HEIGHT = 90
_FORM_LABEL_MIN_WIDTH = 220  # 增加标签宽度
_FORM_FONT = QFont("Microsoft YaHei", 14)
_WINDOW_FALLBACK_BG = "#16202a"
_CARD_BG = "rgba(248, 250, 252, 204)"
_CARD_BORDER = "rgba(255, 255, 255, 110)"


def _primary_button_css() -> str:
    return """
        QPushButton {
            background-color: #f6b03d;
            color: #1a2432;
            border: none;
            border-radius: 12px;
            padding: 14px 28px;
            font-weight: 700;
        }
        QPushButton:hover { background-color: #ffc45b; }
        QPushButton:pressed { background-color: #e0a23c; }
    """


def _secondary_button_css() -> str:
    return """
        QPushButton {
            background-color: rgba(15, 23, 42, 0.06);
            color: #2d3c4d;
            border: 1px solid rgba(61, 90, 128, 0.18);
            border-radius: 12px;
            padding: 12px 22px;
        }
        QPushButton:hover { background-color: rgba(15, 23, 42, 0.1); }
        QPushButton:pressed { background-color: rgba(15, 23, 42, 0.16); }
    """


def _apply_card_shadow(widget: QWidget) -> None:
    if not ENABLE_UI_SHADOWS:
        return
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(30)
    shadow.setOffset(0, 14)
    shadow.setColor(QColor(0, 0, 0, 54))
    widget.setGraphicsEffect(shadow)


def _load_wallpaper_pixmap(path: str) -> QPixmap | None:
    """安全加载壁纸图片，失败时返回 None。"""
    if not path or not os.path.exists(path):
        return None
    pixmap = QPixmap(path)
    if pixmap.isNull():
        return None
    return pixmap


def _create_wallpaper_label(parent: QWidget) -> QLabel:
    """创建只负责绘制背景、不参与事件处理的壁纸层。"""
    label = QLabel(parent)
    label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    label.setScaledContents(False)
    label.lower()
    label.hide()
    return label


def _update_wallpaper_label(
    label: QLabel, pixmap: QPixmap | None, width: int, height: int
) -> None:
    """更新壁纸层尺寸与缩放结果。"""
    label.setGeometry(0, 0, width, height)
    if pixmap is None or pixmap.isNull() or width <= 0 or height <= 0:
        label.clear()
        label.hide()
        return
    label.setPixmap(
        pixmap.scaled(
            width,
            height,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
    )
    label.show()


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
    widget.setStyleSheet(
        """
        padding: 8px 14px;
        border-radius: 12px;
        border: 1px solid rgba(69, 90, 100, 0.18);
        background-color: rgba(255, 255, 255, 0.78);
        selection-background-color: #2c7be5;
        """
    )


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
        self._wallpaper_pixmap = None
        self._wallpaper_label = None
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("管理员验证")
        self.setFixedSize(700, 560)  # 继续增加垂直空间，避免标题和按钮区域过挤
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.setObjectName("PasswordDialogRoot")
        self.setStyleSheet(
            f"""
            QDialog#PasswordDialogRoot {{
                background-color: {_WINDOW_FALLBACK_BG};
            }}
            QFrame#PasswordDialogCard {{
                background-color: {_CARD_BG};
                border: 1px solid {_CARD_BORDER};
                border-radius: 20px;
            }}
            """
        )

        self._wallpaper_label = _create_wallpaper_label(self)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(28, 24, 28, 34)

        card = QFrame(self)
        card.setObjectName("PasswordDialogCard")
        _apply_card_shadow(card)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(20)
        card_layout.setContentsMargins(38, 34, 38, 42)

        eyebrow = QLabel("ADMIN ACCESS")
        eyebrow.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        eyebrow.setAlignment(Qt.AlignCenter)
        eyebrow.setStyleSheet("color: #5d8cd8; letter-spacing: 1px;")
        card_layout.addWidget(eyebrow)

        title = QLabel("请输入管理员密码")
        title.setFont(QFont("Microsoft YaHei", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        title.setMinimumHeight(92)
        title.setStyleSheet("padding: 12px 0 10px 0; color: #1d2a38;")
        card_layout.addWidget(title)

        subtitle = QLabel("验证通过后才能进入管理设置。")
        subtitle.setFont(QFont("Microsoft YaHei", 12))
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setMinimumHeight(44)
        subtitle.setStyleSheet("color: #607080; padding: 0 0 10px 0;")
        card_layout.addWidget(subtitle)

        # 密码输入
        self._password_input = QLineEdit()
        self._password_input.setEchoMode(QLineEdit.Password)
        self._password_input.setPlaceholderText("请输入密码")
        self._password_input.setFont(QFont("Microsoft YaHei", 14))
        self._password_input.setMinimumHeight(98)
        self._password_input.setStyleSheet(
            """
            padding: 14px 20px;
            border-radius: 12px;
            border: 1px solid rgba(69, 90, 100, 0.18);
            background-color: rgba(255, 255, 255, 0.72);
            """
        )
        self._password_input.returnPressed.connect(self._verify)
        card_layout.addWidget(self._password_input)

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
        self._status_label.setMinimumHeight(80)  # 确保错误提示出现时仍不挤压按钮
        card_layout.addWidget(self._status_label)

        card_layout.addSpacing(4)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(22)
        btn_layout.setContentsMargins(0, 16, 0, 18)
        cancel_btn = QPushButton("取消")
        cancel_btn.setFont(QFont("Microsoft YaHei", 14))
        cancel_btn.setMinimumHeight(70)
        cancel_btn.setMinimumWidth(150)
        cancel_btn.setStyleSheet(_secondary_button_css())
        cancel_btn.clicked.connect(self.reject)

        confirm_btn = QPushButton("确认")
        confirm_btn.setFont(QFont("Microsoft YaHei", 14))
        confirm_btn.setMinimumHeight(70)
        confirm_btn.setMinimumWidth(150)
        confirm_btn.setDefault(True)
        confirm_btn.setStyleSheet(_primary_button_css())
        confirm_btn.clicked.connect(self._verify)

        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(confirm_btn)
        card_layout.addLayout(btn_layout)

        layout.addWidget(card)
        self._apply_wallpaper_background()

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

    def _apply_wallpaper_background(self):
        self._wallpaper_pixmap = _load_wallpaper_pixmap(
            getattr(self._config, "wallpaper_path", "")
        )
        _update_wallpaper_label(
            self._wallpaper_label, self._wallpaper_pixmap, self.width(), self.height()
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        _update_wallpaper_label(
            self._wallpaper_label, self._wallpaper_pixmap, self.width(), self.height()
        )

    @property
    def authenticated(self) -> bool:
        return self._authenticated


class AdminPanel(QDialog):
    """管理员设置面板"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._rate_input_adapter: _RateInputAdapter | None = None
        self._export_rate_input_adapter: _RateInputAdapter | None = None
        self._wallpaper_pixmap = None
        self._wallpaper_label = None
        self._init_ui()
        self._load_config()

    def _init_ui(self):
        self.setWindowTitle("管理设置")
        self.resize(1200, 820)
        self.setMinimumSize(1100, 720)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.setObjectName("AdminPanelRoot")
        self.setStyleSheet(
            f"""
            QDialog#AdminPanelRoot {{
                background-color: {_WINDOW_FALLBACK_BG};
            }}
            QFrame#AdminPanelCard {{
                background-color: {_CARD_BG};
                border: 1px solid {_CARD_BORDER};
                border-radius: 20px;
            }}
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QGroupBox {{
                background-color: rgba(255, 255, 255, 0.56);
                border: 1px solid rgba(207, 216, 220, 0.7);
                border-radius: 16px;
                margin-top: 14px;
                padding-top: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 16px;
                padding: 0 8px;
                color: #263238;
            }}
            QLineEdit, QDoubleSpinBox {{
                color: #25313f;
            }}
            """
        )

        self._wallpaper_label = _create_wallpaper_label(self)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 16, 18, 16)
        root_layout.setSpacing(0)

        card = QFrame(self)
        card.setObjectName("AdminPanelCard")
        _apply_card_shadow(card)
        main_layout = QVBoxLayout(card)
        main_layout.setContentsMargins(22, 22, 22, 18)
        main_layout.setSpacing(14)
        root_layout.addWidget(card)

        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.NoFrame)

        # 创建内容部件
        content_widget = QWidget()
        content_widget.setAttribute(Qt.WA_StyledBackground, True)
        content_widget.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(25)  # 减少间距，让布局更紧凑
        layout.setContentsMargins(30, 32, 30, 32)

        scroll_area.setWidget(content_widget)

        main_layout.addWidget(scroll_area)

        # 将按钮放在滚动区域之外，确保始终可见
        self._setup_bottom_buttons(main_layout)

        eyebrow = QLabel("ADMIN CONSOLE")
        eyebrow.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        eyebrow.setStyleSheet("color: #5d8cd8; letter-spacing: 1px;")
        layout.addWidget(eyebrow)

        title = QLabel("门店计时计费管理设置")
        title.setFont(QFont("Microsoft YaHei", 26, QFont.Bold))
        title.setStyleSheet("color: #1d2a38;")
        layout.addWidget(title)

        summary = QLabel("设置会自动保存到本地配置文件，重启软件后继续生效。")
        summary.setFont(QFont("Microsoft YaHei", 13))
        summary.setStyleSheet("color: #607d8b; padding: 4px 0 18px 0;")
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

        qr_hint = QLabel("支持分别上传微信和支付宝收款码；若只配置一张，收费弹窗会自动复用。")
        qr_hint.setFont(QFont("Microsoft YaHei", 12))
        qr_hint.setStyleSheet("color: #5d6c7b;")
        qr_hint.setWordWrap(True)
        qr_layout.addWidget(qr_hint)

        wechat_title = QLabel("微信收款码")
        wechat_title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        wechat_title.setStyleSheet("color: #1f7a4d;")
        qr_layout.addWidget(wechat_title)

        wechat_path_layout = QHBoxLayout()
        wechat_path_layout.setSpacing(12)
        self._wechat_qr_path_input = QLineEdit()
        self._wechat_qr_path_input.setFont(_FORM_FONT)
        self._wechat_qr_path_input.setPlaceholderText("选择微信收款码图片文件")
        self._wechat_qr_path_input.setReadOnly(True)
        _apply_form_control_style(self._wechat_qr_path_input)
        wechat_path_layout.addWidget(self._wechat_qr_path_input)

        wechat_browse_btn = QPushButton("浏览...")
        wechat_browse_btn.setFont(_FORM_FONT)
        wechat_browse_btn.setMinimumHeight(_FORM_INPUT_MIN_HEIGHT)
        wechat_browse_btn.setStyleSheet(_secondary_button_css())
        wechat_browse_btn.clicked.connect(lambda: self._browse_qr_code("wechat"))
        wechat_path_layout.addWidget(wechat_browse_btn)
        qr_layout.addLayout(wechat_path_layout)

        self._wechat_qr_preview = QLabel()
        self._wechat_qr_preview.setFixedSize(120, 120)
        self._wechat_qr_preview.setStyleSheet(
            "border: 1px solid rgba(69, 90, 100, 0.18); background: rgba(255,255,255,0.72); border-radius: 16px;"
        )
        self._wechat_qr_preview.setAlignment(Qt.AlignCenter)
        self._wechat_qr_preview.setScaledContents(True)
        qr_layout.addWidget(self._wechat_qr_preview, alignment=Qt.AlignCenter)

        alipay_title = QLabel("支付宝收款码")
        alipay_title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        alipay_title.setStyleSheet("color: #2166d1;")
        qr_layout.addWidget(alipay_title)

        alipay_path_layout = QHBoxLayout()
        alipay_path_layout.setSpacing(12)
        self._alipay_qr_path_input = QLineEdit()
        self._alipay_qr_path_input.setFont(_FORM_FONT)
        self._alipay_qr_path_input.setPlaceholderText("选择支付宝收款码图片文件")
        self._alipay_qr_path_input.setReadOnly(True)
        _apply_form_control_style(self._alipay_qr_path_input)
        alipay_path_layout.addWidget(self._alipay_qr_path_input)

        alipay_browse_btn = QPushButton("浏览...")
        alipay_browse_btn.setFont(_FORM_FONT)
        alipay_browse_btn.setMinimumHeight(_FORM_INPUT_MIN_HEIGHT)
        alipay_browse_btn.setStyleSheet(_secondary_button_css())
        alipay_browse_btn.clicked.connect(lambda: self._browse_qr_code("alipay"))
        alipay_path_layout.addWidget(alipay_browse_btn)
        qr_layout.addLayout(alipay_path_layout)

        self._alipay_qr_preview = QLabel()
        self._alipay_qr_preview.setFixedSize(120, 120)
        self._alipay_qr_preview.setStyleSheet(
            "border: 1px solid rgba(69, 90, 100, 0.18); background: rgba(255,255,255,0.72); border-radius: 16px;"
        )
        self._alipay_qr_preview.setAlignment(Qt.AlignCenter)
        self._alipay_qr_preview.setScaledContents(True)
        qr_layout.addWidget(self._alipay_qr_preview, alignment=Qt.AlignCenter)

        qr_clear_btn = QPushButton("清除全部收款码（恢复默认显示）")
        qr_clear_btn.setFont(QFont("Microsoft YaHei", 14))
        qr_clear_btn.setMinimumHeight(_FORM_INPUT_MIN_HEIGHT)
        qr_clear_btn.setStyleSheet(_secondary_button_css())
        qr_clear_btn.clicked.connect(self._clear_qr_code)
        qr_layout.addWidget(qr_clear_btn)

        self._qr_path_input = self._wechat_qr_path_input
        self._qr_preview = self._wechat_qr_preview

        qr_group.setLayout(qr_layout)
        layout.addWidget(qr_group)

        # === 壁纸设置 ===
        wp_group = QGroupBox("壁纸设置")
        wp_group.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        wp_layout = QVBoxLayout()
        wp_layout.setSpacing(40)
        wp_layout.setContentsMargins(12, 30, 12, 26)

        wp_path_layout = QHBoxLayout()
        wp_path_layout.setSpacing(12)
        self._wp_path_input = QLineEdit()
        self._wp_path_input.setFont(_FORM_FONT)
        self._wp_path_input.setPlaceholderText("选择壁纸图片文件（留空则使用纯色背景）")
        self._wp_path_input.setReadOnly(True)
        _apply_form_control_style(self._wp_path_input)
        wp_path_layout.addWidget(self._wp_path_input)

        wp_browse_btn = QPushButton("浏览...")
        wp_browse_btn.setFont(_FORM_FONT)
        wp_browse_btn.setMinimumHeight(_FORM_INPUT_MIN_HEIGHT)
        wp_browse_btn.setStyleSheet(_secondary_button_css())
        wp_browse_btn.clicked.connect(self._browse_wallpaper)
        wp_path_layout.addWidget(wp_browse_btn)
        wp_layout.addLayout(wp_path_layout)

        # 清除壁纸按钮
        wp_clear_btn = QPushButton("清除壁纸（恢复默认背景）")
        wp_clear_btn.setFont(QFont("Microsoft YaHei", 14))
        wp_clear_btn.setMinimumHeight(_FORM_INPUT_MIN_HEIGHT)
        wp_clear_btn.setStyleSheet(_secondary_button_css())
        wp_clear_btn.clicked.connect(self._clear_wallpaper)
        wp_layout.addWidget(wp_clear_btn)

        # 壁纸预览
        self._wp_preview = QLabel()
        self._wp_preview.setFixedSize(200, 120)
        self._wp_preview.setStyleSheet(
            "border: 1px solid rgba(69, 90, 100, 0.18); background: rgba(255,255,255,0.88); border-radius: 16px;"
        )
        self._wp_preview.setAlignment(Qt.AlignCenter)
        self._wp_preview.setScaledContents(True)
        wp_layout.addWidget(self._wp_preview, alignment=Qt.AlignCenter)

        wp_group.setLayout(wp_layout)
        layout.addWidget(wp_group)

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
        self._apply_wallpaper_background()

    def _load_config(self):
        """从配置加载到界面"""
        self._rate_spin.setValue(self._config.rate)
        self.rate_input.clear()
        self._export_rate_spin.setValue(self._config.export_rate)
        self.export_rate_input.clear()
        self._process_input.setText(self._config.process_name)
        self._keywords_input.setText(",".join(self._config.export_window_keywords))
        self._interval_spin.setValue(self._config.monitor_interval_ms / 1000.0)

        wechat_qr_path = getattr(self._config, "wechat_qr_code_path", "") or self._config.qr_code_path
        if wechat_qr_path:
            self._wechat_qr_path_input.setText(wechat_qr_path)
            self._preview_qr_label(
                self._wechat_qr_preview, wechat_qr_path, "未选择\n微信收款码"
            )
        else:
            self._show_placeholder_qr_preview(
                self._wechat_qr_preview, "未选择\n微信收款码"
            )

        alipay_qr_path = getattr(self._config, "alipay_qr_code_path", "") or self._config.qr_code_path
        if alipay_qr_path:
            self._alipay_qr_path_input.setText(alipay_qr_path)
            self._preview_qr_label(
                self._alipay_qr_preview, alipay_qr_path, "未选择\n支付宝收款码"
            )
        else:
            self._show_placeholder_qr_preview(
                self._alipay_qr_preview, "未选择\n支付宝收款码"
            )

        # 加载壁纸
        wp_path = getattr(self._config, "wallpaper_path", "")
        if wp_path:
            self._wp_path_input.setText(wp_path)
            self._preview_wallpaper(wp_path)
        else:
            self._preview_wallpaper("")
        self._apply_wallpaper_background(wp_path)

    def _apply_wallpaper_background(self, path: str = ""):
        wallpaper_path = path or self._wp_path_input.text().strip()
        self._wallpaper_pixmap = _load_wallpaper_pixmap(wallpaper_path)
        _update_wallpaper_label(
            self._wallpaper_label, self._wallpaper_pixmap, self.width(), self.height()
        )

    def _browse_qr_code(self, qr_type: str = "wechat"):
        """浏览选择收款码图片"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择收款码图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp);;所有文件 (*.*)",
        )
        if file_path:
            if qr_type == "alipay":
                self._alipay_qr_path_input.setText(file_path)
                self._preview_qr_label(
                    self._alipay_qr_preview, file_path, "未选择\n支付宝收款码"
                )
                qr_name = "支付宝收款码"
            else:
                self._wechat_qr_path_input.setText(file_path)
                self._preview_qr_label(
                    self._wechat_qr_preview, file_path, "未选择\n微信收款码"
                )
                qr_name = "微信收款码"
            self._set_status(
                f"已选择{qr_name}：{os.path.basename(file_path)}", success=True
            )

    def _browse_wallpaper(self):
        """浏览选择壁纸图片"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择壁纸图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp);;所有文件 (*.*)",
        )
        if file_path:
            self._wp_path_input.setText(file_path)
            self._preview_wallpaper(file_path)
            self._apply_wallpaper_background(file_path)
            self._set_status(
                f"已选择壁纸：{os.path.basename(file_path)}", success=True
            )

    def _clear_wallpaper(self):
        """清除壁纸设置"""
        self._wp_path_input.clear()
        self._wp_preview.clear()
        placeholder = QPixmap(200, 120)
        placeholder.fill(QColor("#f5f5f5"))
        painter = QPainter(placeholder)
        painter.setPen(QColor("#9e9e9e"))
        painter.setFont(QFont("Microsoft YaHei", 12))
        painter.drawText(placeholder.rect(), Qt.AlignCenter, "无壁纸")
        painter.end()
        self._wp_preview.setPixmap(placeholder)
        self._apply_wallpaper_background("")
        self._set_status("已清除壁纸设置。", success=True)

    def _clear_qr_code(self):
        """清除收款码设置"""
        self._wechat_qr_path_input.clear()
        self._alipay_qr_path_input.clear()
        self._show_placeholder_qr_preview(
            self._wechat_qr_preview, "未选择\n微信收款码"
        )
        self._show_placeholder_qr_preview(
            self._alipay_qr_preview, "未选择\n支付宝收款码"
        )
        self._set_status("已清除收款码设置。", success=True)

    def _preview_qr(self, path: str):
        """预览收款码图片"""
        self._preview_qr_label(self._qr_preview, path, "未选择\n微信收款码")

    def _preview_qr_label(self, target_label: QLabel, path: str, empty_text: str):
        """按目标预览收款码图片。"""
        if os.path.exists(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    110, 110, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                target_label.setPixmap(scaled)
                return
        self._show_placeholder_qr_preview(target_label, empty_text)

    def _show_placeholder_qr_preview(
        self, target_label: QLabel, empty_text: str = "未选择\n微信收款码"
    ):
        """显示收款码占位图（管理面板预览用）"""
        target_label.clear()
        placeholder = QPixmap(110, 110)
        placeholder.fill(QColor("#f5f5f5"))
        painter = QPainter(placeholder)
        painter.setPen(QColor("#9e9e9e"))
        painter.drawText(placeholder.rect(), Qt.AlignCenter, empty_text)
        painter.end()
        target_label.setPixmap(placeholder)

    def _preview_wallpaper(self, path: str):
        """预览壁纸图片"""
        if os.path.exists(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    200, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                self._wp_preview.setPixmap(scaled)
                return
        # 无壁纸时显示占位
        self._wp_preview.clear()
        from PyQt5.QtGui import QPainter, QColor

        placeholder = QPixmap(200, 120)
        placeholder.fill(QColor("#f5f5f5"))
        painter = QPainter(placeholder)
        painter.setPen(QColor("#9e9e9e"))
        painter.setFont(QFont("Microsoft YaHei", 12))
        painter.drawText(placeholder.rect(), Qt.AlignCenter, "无壁纸")
        painter.end()
        self._wp_preview.setPixmap(placeholder)

    def _set_status(self, message: str, success: bool = False):
        if success:
            self._status_label.setStyleSheet(
                """
                color: #166534;
                background-color: rgba(34, 197, 94, 0.12);
                border: 1px solid rgba(34, 197, 94, 0.2);
                border-radius: 12px;
                padding: 12px 16px;
                """
            )
        else:
            self._status_label.setStyleSheet(
                """
                color: #b42318;
                background-color: rgba(255, 92, 92, 0.08);
                border: 1px solid rgba(255, 92, 92, 0.16);
                border-radius: 12px;
                padding: 12px 16px;
                """
            )
        self._status_label.setText(message)

    def _save(self):
        """保存设置"""
        rate_text = self.rate_input.consume_text()
        try:
            rate = float(rate_text)
        except ValueError:
            self._set_status("请输入有效的数字。")
            return

        export_rate_text = self.export_rate_input.consume_text()
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
        self.rate_input.clear()
        self._export_rate_spin.setValue(export_rate)
        self.export_rate_input.clear()

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
        wechat_qr_path = self._wechat_qr_path_input.text().strip()
        alipay_qr_path = self._alipay_qr_path_input.text().strip()
        if wechat_qr_path and not os.path.exists(wechat_qr_path):
            self._set_status("微信收款码图片路径不存在。")
            return
        if alipay_qr_path and not os.path.exists(alipay_qr_path):
            self._set_status("支付宝收款码图片路径不存在。")
            return
        updates["wechat_qr_code_path"] = wechat_qr_path
        updates["alipay_qr_code_path"] = alipay_qr_path
        updates["qr_code_path"] = wechat_qr_path or alipay_qr_path

        # 壁纸路径
        wp_path = self._wp_path_input.text().strip()
        if wp_path and not os.path.exists(wp_path):
            self._set_status("壁纸图片路径不存在。")
            return
        updates["wallpaper_path"] = wp_path

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
        self._apply_wallpaper_background(wp_path)
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
    def rate_input(self) -> _RateInputAdapter:
        if self._rate_input_adapter is None:
            raise RuntimeError("rate input adapter has not been initialized")
        return self._rate_input_adapter

    @property
    def export_rate_input(self) -> _RateInputAdapter:
        if self._export_rate_input_adapter is None:
            raise RuntimeError("export rate input adapter has not been initialized")
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        _update_wallpaper_label(
            self._wallpaper_label, self._wallpaper_pixmap, self.width(), self.height()
        )

    def _setup_bottom_buttons(self, main_layout):
        """设置底部按钮，确保始终可见"""
        # 状态标签
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setFont(QFont("Microsoft YaHei", 13))
        self._status_label.setStyleSheet(
            """
            color: #607d8b;
            background-color: rgba(15, 23, 42, 0.04);
            border: 1px dashed rgba(61, 90, 128, 0.18);
            border-radius: 12px;
            padding: 12px 16px;
            """
        )
        main_layout.addWidget(self._status_label)

        # 按钮
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.setFont(QFont("Microsoft YaHei", 14))
        btn_box.accepted.connect(self._save)
        btn_box.rejected.connect(self.reject)

        # 设置保存按钮样式
        save_btn = btn_box.button(QDialogButtonBox.Save)
        save_btn.setText("保存设置")
        save_btn.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
        save_btn.setMinimumHeight(102)
        save_btn.setMinimumWidth(190)
        save_btn.setStyleSheet(_primary_button_css())
        cancel_panel_btn = btn_box.button(QDialogButtonBox.Cancel)
        if cancel_panel_btn is not None:
            cancel_panel_btn.setText("取消设置")  # 设置按钮文本
            cancel_panel_btn.setFont(QFont("Microsoft YaHei", 18, QFont.Bold))
            cancel_panel_btn.setMinimumHeight(102)
            cancel_panel_btn.setMinimumWidth(190)
            cancel_panel_btn.setStyleSheet(_secondary_button_css())
        self._save_button = save_btn

        main_layout.addWidget(btn_box)
