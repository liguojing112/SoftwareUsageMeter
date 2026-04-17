"""
计时管理模块 - 精确到分钟的计时逻辑
支持：开始、暂停、重置、获取已计时时长
"""

from PyQt5.QtCore import QObject, QTimer, pyqtSignal


class TimerManager(QObject):
    """计时管理器，追踪使用时长"""

    # 信号：每秒触发一次（用于界面更新）
    tick = pyqtSignal(int)  # 参数：已使用的总秒数
    # 信号：每分钟触发一次（用于计费更新）
    minute_tick = pyqtSignal(int)  # 参数：已使用的总分钟数

    def __init__(self, parent=None):
        super().__init__(parent)
        self._elapsed_seconds = 0
        self._running = False

        # 每秒触发计时器
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)

    def start(self):
        """开始计时"""
        if not self._running:
            self._running = True
            self._timer.start()

    def pause(self):
        """暂停计时"""
        if self._running:
            self._running = False
            self._timer.stop()

    def reset(self):
        """重置计时器（清零）"""
        self._running = False
        self._timer.stop()
        self._elapsed_seconds = 0
        self.tick.emit(0)
        self.minute_tick.emit(0)

    def stop_and_report(self) -> int:
        """停止计时并返回使用的总分钟数，然后重置"""
        minutes = self.get_elapsed_minutes()
        self.reset()
        return minutes

    def _on_tick(self):
        """每秒回调"""
        self._elapsed_seconds += 1
        self.tick.emit(self._elapsed_seconds)

        # 每满一分钟触发 minute_tick
        if self._elapsed_seconds % 60 == 0:
            self.minute_tick.emit(self._elapsed_seconds // 60)

    @property
    def is_running(self) -> bool:
        return self._running

    def get_elapsed_seconds(self) -> int:
        """获取已计时的总秒数"""
        return self._elapsed_seconds

    def get_elapsed_minutes(self) -> int:
        """获取已计时的总分钟数（向上取整，不满1分钟按1分钟计）"""
        if self._elapsed_seconds == 0:
            return 0
        # 不满1分钟按1分钟计算（保障商家利益）
        return (self._elapsed_seconds + 59) // 60

    def format_elapsed(self) -> str:
        """格式化显示已计时时长（HH:MM:SS）"""
        total = self._elapsed_seconds
        hours = total // 3600
        minutes = (total % 3600) // 60
        seconds = total % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
