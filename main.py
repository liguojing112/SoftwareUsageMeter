"""
主程序入口 - 应用初始化与信号连接
功能：
1. 初始化所有模块
2. 连接信号/槽
3. 单实例检测
4. 应用生命周期管理
"""

import sys
import os
import logging

from PyQt5.QtWidgets import QApplication, QMessageBox

from config_manager import ConfigManager
from process_monitor import ProcessMonitor
from timer_manager import TimerManager
from payment_overlay import PaymentOverlay
from admin_panel import PasswordDialog, AdminPanel
from tray_icon import TrayIconManager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.log"),
            encoding='utf-8'
        )
    ]
)
logger = logging.getLogger("SoftwareUsageMeter")


class Application:
    """主应用程序类"""

    def __init__(self):
        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)  # 关闭窗口不退出应用

        # 初始化配置
        self._config = ConfigManager()

        # 初始化模块
        self._timer = TimerManager()
        self._monitor = ProcessMonitor(self._config)
        self._overlay = PaymentOverlay(self._config)
        self._tray = TrayIconManager(self._config)

        # 状态
        self._is_exporting = False
        self._payment_confirmed = False

        # 连接信号
        self._connect_signals()

        # 初始化状态显示
        self._tray.update_process_name(self._config.process_name)

        logger.info("应用初始化完成")

    def _connect_signals(self):
        """连接所有信号/槽"""
        # 进程监控信号
        self._monitor.process_started.connect(self._on_process_started)
        self._monitor.process_stopped.connect(self._on_process_stopped)
        self._monitor.export_detected.connect(self._on_export_detected)
        self._monitor.export_cancelled.connect(self._on_export_cancelled)

        # 计时器信号
        self._timer.tick.connect(self._on_timer_tick)
        self._timer.minute_tick.connect(self._on_minute_tick)

        # 收费弹窗
        self._overlay.confirm_button.clicked.connect(self._on_payment_confirmed)

        # 托盘菜单
        self._tray.show_action.triggered.connect(self._on_show_status)
        self._tray.admin_action.triggered.connect(self._on_admin_panel)
        self._tray.manual_trigger_action.triggered.connect(self._on_manual_trigger)
        self._tray.quit_action.triggered.connect(self._on_quit)

    def _on_process_started(self):
        """目标程序启动"""
        if self._is_exporting:
            logger.info("目标程序已启动，但当前仍处于导出结算流程，暂不开始新计时")
            self._tray.set_running_state(False)
            return

        logger.info("目标程序已启动，开始计时")
        self._timer.start()
        self._tray.set_running_state(True)
        self._tray.show_notification(
            "计时开始",
            f"检测到 {self._config.process_name}，已开始计时"
        )

    def _on_process_stopped(self):
        """目标程序退出"""
        logger.info("目标程序已退出，暂停计时")
        # 如果正在显示收费弹窗，先关闭
        if self._overlay.isVisible():
            self._overlay.close_payment()
        self._timer.pause()
        self._tray.set_running_state(False)
        self._is_exporting = False
        self._payment_confirmed = False
        self._tray.show_notification(
            "计时暂停",
            f"{self._config.process_name} 已退出，计时暂停"
        )

    def _on_export_detected(self):
        """检测到导出行为"""
        if self._is_exporting:
            return  # 防止重复触发

        self._is_exporting = True
        self._payment_confirmed = False
        logger.info("检测到导出行为，停止计时并显示收费弹窗")

        # 停止计时
        self._timer.pause()
        self._tray.set_running_state(False)

        # 获取计费信息
        minutes = self._timer.get_elapsed_minutes()
        rate = self._config.rate

        # 显示收费弹窗
        self._overlay.show_payment(
            minutes,
            rate,
            hwnd=self._monitor.main_hwnd,
            lock_targets=self._monitor.lock_target_hwnds,
        )

    def _on_export_cancelled(self):
        """导出窗口关闭（取消导出或导出完成）"""
        if not self._is_exporting:
            return

        if self._payment_confirmed:
            logger.info("导出已结束，进入下一次计时周期")
            self._finish_export_cycle()
            return

        logger.info("导出在付款前被取消，关闭收费弹窗并恢复计时")
        if self._overlay.isVisible():
            self._overlay.close_payment()
        self._is_exporting = False
        self._payment_confirmed = False
        if self._monitor.is_process_running:
            self._timer.start()
            self._tray.set_running_state(True)
            self._tray.show_notification("恢复计时", "导出已取消，继续当前计时")

    def _on_timer_tick(self, seconds: int):
        """每秒更新计时显示"""
        time_str = self._timer.format_elapsed()
        minutes = self._timer.get_elapsed_minutes()
        rate = self._config.rate
        self._tray.update_timing(time_str, minutes, rate)

    def _on_minute_tick(self, minutes: int):
        """每分钟更新一次费用"""
        rate = self._config.rate
        self._tray.update_timing(self._timer.format_elapsed(), minutes, rate)

    def _on_payment_confirmed(self):
        """管理员确认收款"""
        logger.info("确认收款，关闭弹窗并等待本次导出结束")
        self._overlay.close_payment()
        self._timer.reset()
        self._tray.reset()
        self._is_exporting = True
        self._payment_confirmed = True

        # 手动触发收费等场景下可能没有导出窗口，直接进入下一轮
        if not self._monitor.is_export_dialog_visible:
            self._finish_export_cycle()
            return

        self._tray.show_notification("已确认收款", "已解锁导出，导出完成后将开始下一轮计时")

    def _on_show_status(self):
        """显示状态窗口"""
        self._tray.status_widget.show()
        self._tray.status_widget.raise_()
        self._tray.status_widget.activateWindow()

    def _on_admin_panel(self):
        """打开管理设置面板"""
        # 先验证密码
        pwd_dialog = PasswordDialog(self._config)
        if pwd_dialog.exec_() != PasswordDialog.Accepted:
            return
        if not pwd_dialog.authenticated:
            return

        # 显示设置面板
        admin_panel = AdminPanel(self._config)
        admin_panel.exec_()

        # 设置可能已更新，刷新状态
        self._tray.update_process_name(self._config.process_name)
        self._tray.status_widget.update_process(self._config.process_name)

        # 如果监控正在运行，需要重启以应用新的进程名/关键词
        if self._monitor.isRunning():
            self._monitor.stop()
            self._monitor = ProcessMonitor(self._config)
            self._monitor.process_started.connect(self._on_process_started)
            self._monitor.process_stopped.connect(self._on_process_stopped)
            self._monitor.export_detected.connect(self._on_export_detected)
            self._monitor.export_cancelled.connect(self._on_export_cancelled)
            self._monitor.start()
            logger.info("监控已重启以应用新设置")

    def _on_manual_trigger(self):
        """手动触发收费"""
        if not self._timer.is_running and self._timer.get_elapsed_seconds() == 0:
            QMessageBox.information(
                None, "提示",
                "当前没有使用记录，无法触发收费。"
            )
            return

        # 需要管理员密码确认
        pwd_dialog = PasswordDialog(self._config)
        if pwd_dialog.exec_() != PasswordDialog.Accepted:
            return
        if not pwd_dialog.authenticated:
            return

        # 停止计时并显示收费
        self._timer.pause()
        self._tray.set_running_state(False)
        minutes = self._timer.get_elapsed_minutes()
        rate = self._config.rate
        self._is_exporting = True
        self._payment_confirmed = False
        self._overlay.show_payment(
            minutes,
            rate,
            hwnd=self._monitor.main_hwnd,
            lock_targets=self._monitor.lock_target_hwnds,
        )

    def _finish_export_cycle(self):
        """当前收费流程结束，准备进入下一轮计时。"""
        self._is_exporting = False
        self._payment_confirmed = False
        if self._monitor.is_process_running:
            self._timer.start()
            self._tray.set_running_state(True)
            self._tray.show_notification("开始新一轮计时", "本次导出已结束，已进入下一轮计时")

    def _on_quit(self):
        """退出应用"""
        self._monitor.stop()
        self._timer.pause()
        self._overlay.close_payment()
        QApplication.quit()
        logger.info("应用已退出")

    def run(self) -> int:
        """启动应用"""
        # 显示托盘图标
        self._tray.show()

        # 启动监控线程
        self._monitor.start()

        logger.info("应用已启动，正在监控目标程序...")

        return self._app.exec_()


def check_single_instance():
    """检查是否已有实例在运行（通过互斥体）"""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        mutex = kernel32.CreateMutexW(None, False, "SoftwareUsageMeter_SingleInstance")
        last_error = kernel32.GetLastError()
        if last_error == 183:  # ERROR_ALREADY_EXISTS
            return False
        return True
    except Exception:
        return True


def main():
    """主入口"""
    # 单实例检测
    if not check_single_instance():
        QMessageBox.warning(
            None, "提示",
            "程序已在运行中，请勿重复启动！\n如需操作，请在系统托盘查找图标。"
        )
        sys.exit(1)

    app = Application()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
