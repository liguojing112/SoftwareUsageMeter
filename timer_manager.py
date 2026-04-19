"""
计时管理模块 - 精确到分钟的计时逻辑
支持：开始、暂停、重置、获取已计时时长
"""

import time

from PyQt5.QtCore import QObject, QTimer, pyqtSignal


class TimerManager(QObject):
    """计时管理器，追踪使用时长"""

    # 信号：每秒触发一次（用于界面更新）
    tick = pyqtSignal(int)  # 参数：已使用的总秒数
    # 信号：每分钟触发一次（用于计费更新）
    minute_tick = pyqtSignal(int)  # 参数：已使用的总分钟数

    def __init__(self, parent=None):
        super().__init__(parent)
        self._accumulated_seconds = 0.0
        self._session_started_at = None
        self._running = False
        self._last_emitted_seconds = 0
        self._last_full_minutes = 0

        # 用较短轮询周期配合 monotonic 时间，减少 GUI 卡顿带来的计时误差
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._on_tick)

    def start(self):
        """开始计时"""
        if not self._running:
            self._running = True
            self._session_started_at = time.monotonic()
            self._last_emitted_seconds = self.get_elapsed_seconds()
            self._last_full_minutes = self._last_emitted_seconds // 60
            self._timer.start()

    def pause(self):
        """暂停计时"""
        if self._running:
            self._accumulated_seconds = self._current_elapsed_seconds_float()
            self._session_started_at = None
            self._running = False
            self._timer.stop()

    def reset(self):
        """重置计时器（清零）"""
        self._running = False
        self._timer.stop()
        self._accumulated_seconds = 0.0
        self._session_started_at = None
        self._last_emitted_seconds = 0
        self._last_full_minutes = 0
        self.tick.emit(0)
        self.minute_tick.emit(0)

    def stop_and_report(self) -> int:
        """停止计时并返回使用的总分钟数，然后重置"""
        minutes = self.get_elapsed_minutes()
        self.reset()
        return minutes

    def _on_tick(self):
        """每秒回调"""
        elapsed_seconds = self.get_elapsed_seconds()
        if elapsed_seconds != self._last_emitted_seconds:
            self._last_emitted_seconds = elapsed_seconds
            self.tick.emit(elapsed_seconds)

            full_minutes = elapsed_seconds // 60
            if full_minutes != self._last_full_minutes:
                self._last_full_minutes = full_minutes
                self.minute_tick.emit(full_minutes)

    @property
    def is_running(self) -> bool:
        return self._running

    def _current_elapsed_seconds_float(self) -> float:
        """获取包含小数部分的累计秒数，用于暂停时无损结算。"""
        elapsed = self._accumulated_seconds
        if self._running and self._session_started_at is not None:
            elapsed += time.monotonic() - self._session_started_at
        return max(elapsed, 0.0)

    def get_elapsed_seconds(self) -> int:
        """获取已计时的总秒数"""
        return int(self._current_elapsed_seconds_float())

    def get_elapsed_minutes(self) -> int:
        """获取已计时的总分钟数（向上取整，不满1分钟按1分钟计）"""
        elapsed_seconds = self.get_elapsed_seconds()
        if elapsed_seconds == 0:
            return 0
        # 不满1分钟按1分钟计算（保障商家利益）
        return (elapsed_seconds + 59) // 60

    def format_elapsed(self) -> str:
        """格式化显示已计时时长（HH:MM:SS）"""
        total = self.get_elapsed_seconds()
        hours = total // 3600
        minutes = (total % 3600) // 60
        seconds = total % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    @property
    def _elapsed_seconds(self) -> int:
        """兼容旧测试代码直接读写 `_elapsed_seconds`。"""
        return self.get_elapsed_seconds()

    @_elapsed_seconds.setter
    def _elapsed_seconds(self, value: int):
        self._accumulated_seconds = max(float(value), 0.0)
        self._session_started_at = None
        self._running = False
        self._timer.stop()
        self._last_emitted_seconds = int(self._accumulated_seconds)
        self._last_full_minutes = int(self._accumulated_seconds) // 60
