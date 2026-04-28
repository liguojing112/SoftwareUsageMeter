import time
from types import SimpleNamespace

import main
import process_monitor
from main import Application


class FakeOverlay:
    def __init__(self, visible=False):
        self._visible = visible
        self.closed = False
        self.counting_statuses = []
        self.manual_required_values = []
        self.display_updates = []
        self.payment_shows = []
        self.pause_keep_on_top_calls = 0
        self.resume_keep_on_top_calls = 0
        self.reset_confirmation_calls = 0
        self.manual_required = False
        self.current_count = 0

    def isVisible(self):
        return self._visible

    def close_payment(self):
        self.closed = True
        self._visible = False

    def set_counting_status(self, counting):
        self.counting_statuses.append(bool(counting))

    def set_manual_export_count_required(self, required):
        self.manual_required_values.append(bool(required))
        self.manual_required = bool(required)

    def update_display(self, *args, **kwargs):
        self.display_updates.append((args, kwargs))
        if "export_count" in kwargs:
            self.current_count = kwargs["export_count"]

    def show_payment(self, *args, **kwargs):
        self.payment_shows.append((args, kwargs))
        self._visible = True

    def pause_keep_on_top(self):
        self.pause_keep_on_top_calls += 1

    def resume_keep_on_top(self):
        self.resume_keep_on_top_calls += 1

    def reset_payment_confirmation(self):
        self.reset_confirmation_calls += 1

    def is_manual_export_count_required(self):
        return self.manual_required

    def current_export_count(self):
        return self.current_count


class FakeWaitOverlay:
    def __init__(self, visible=False):
        self._visible = visible

    def isVisible(self):
        return self._visible


class FakeMonitor:
    def __init__(self):
        self.hold_values = []
        self.post_payment_values = []
        self.restore_calls = 0
        self.suspend_calls = 0
        self.capture_calls = 0
        self.is_process_running = True
        self.export_dialog_visible = False
        self.assumed_reasons = []
        self.assumed_targets = []
        self.cached_export_count = None
        self.live_summary_count = None
        self.live_image_count = None
        self.clear_cache_reasons = []
        self.events = []
        self.paid_retry_calls = 0

    def set_export_state_hold(self, hold):
        self.hold_values.append(hold)

    def clear_export_count_cache(self, reason=""):
        self.clear_cache_reasons.append(reason)
        self.cached_export_count = None

    def assume_export_in_progress(self, reason="", main_hwnd=None):
        self.assumed_reasons.append(reason)
        self.assumed_targets.append(main_hwnd)
        self.export_dialog_visible = True

    def set_post_payment_pending(self, active):
        self.post_payment_values.append(active)

    def restore_target_interaction(self):
        self.restore_calls += 1
        return {"restored": True}

    def prepare_paid_export_retry(self):
        self.paid_retry_calls += 1
        self.post_payment_values.append(True)
        self.hold_values.append(False)
        return {"restored": True, "paid_retry": True}

    def suspend_target_processes(self):
        self.events.append("suspend")
        self.suspend_calls += 1

    def snapshot_current_export_capture(self, reason=""):
        self.events.append("snapshot")
        return True

    def get_recent_export_count(self, max_age_seconds=30.0):
        return self.cached_export_count

    def get_last_export_capture_image(self, max_age_seconds=5.0):
        return None

    def get_last_export_capture_dialog_mode(self, max_age_seconds=5.0):
        return False

    def capture_main_window_image(self):
        self.capture_calls += 1
        return object()

    def detect_export_summary_count_from_image(self, image, dialog_mode=False):
        return self.live_summary_count

    def detect_export_image_count_from_image(self, image, dialog_mode=False):
        return self.live_image_count

    def detect_export_summary_count(self):
        return None

    def detect_export_image_count(self):
        return None

    @property
    def main_hwnd(self):
        return None

    @property
    def export_hwnd(self):
        return None

    @property
    def is_export_dialog_visible(self):
        return self.export_dialog_visible

    @property
    def lock_target_hwnds(self):
        return []


class FakeTimer:
    def __init__(self, minutes=7):
        self.minutes = minutes
        self.paused = False
        self.started = False
        self.reset_called = False

    def pause(self):
        self.paused = True

    def start(self):
        self.started = True

    def get_elapsed_minutes(self):
        return self.minutes

    def reset(self):
        self.reset_called = True


class FakeTray:
    def __init__(self):
        self.running_states = []
        self.notifications = []
        self.reset_called = False

    def set_running_state(self, state):
        self.running_states.append(state)

    def show_notification(self, title, message):
        self.notifications.append((title, message))

    def reset(self):
        self.reset_called = True


def make_app():
    app = Application.__new__(Application)
    app._is_exporting = True
    app._payment_confirmed = False
    app._awaiting_process_close_after_paid_export = False
    app._current_export_count = 3
    app._export_wait_overlay = None
    app._pending_wait_payment_args = None
    app._overlay = FakeOverlay()
    app._monitor = FakeMonitor()
    app._timer = FakeTimer()
    app._tray = FakeTray()
    app._config = SimpleNamespace(
        rate=2.5,
        export_rate=1.0,
        default_export_count=1,
        process_name="PixCake.exe",
    )
    app._log_runtime_snapshot = lambda label: None
    app._show_export_wait_overlay_called = False

    def fake_show_export_wait_overlay(minutes=None, rate=None):
        app._show_export_wait_overlay_called = True
        app._pending_wait_payment_args = (minutes, rate)

    app._show_export_wait_overlay = fake_show_export_wait_overlay
    return app


def test_cancel_signal_does_not_close_visible_payment_before_confirmation():
    app = make_app()
    app._overlay = FakeOverlay(visible=True)

    app._on_export_cancelled()

    assert app._is_exporting is True
    assert app._payment_confirmed is False
    assert app._overlay.closed is False
    assert app._monitor.hold_values[-1] is True
    assert app._monitor.restore_calls == 0


def test_export_detected_coalesces_with_existing_wait_overlay():
    app = make_app()
    app._is_exporting = False
    app._overlay = FakeOverlay(visible=False)
    app._export_wait_overlay = FakeWaitOverlay(visible=True)

    app._on_export_detected()

    assert app._is_exporting is True
    assert app._payment_confirmed is False
    assert app._pending_wait_payment_args == (7, 2.5)
    assert app._timer.paused is True
    assert app._tray.running_states[-1] is False
    assert app._monitor.hold_values[-1] is True
    assert app._show_export_wait_overlay_called is False


def test_process_started_clears_export_count_cache_for_new_lifecycle():
    app = make_app()
    app._is_exporting = False

    app._on_process_started()

    assert app._monitor.clear_cache_reasons[-1] == "process_started"
    assert app._current_export_count == 0


def test_export_detected_shows_wait_overlay_before_redundant_suspend():
    app = make_app()
    app._is_exporting = False
    app._overlay = FakeOverlay(visible=False)
    app._export_wait_overlay = None
    call_order = []
    app._show_export_wait_overlay = (
        lambda minutes=None, rate=None: call_order.append("show_wait")
    )
    app._monitor.suspend_target_processes = lambda: call_order.append("suspend")
    app._prepare_export_count_fallback_policy = lambda: None

    app._on_export_detected()

    assert call_order[:2] == ["show_wait", "suspend"]


def test_normal_export_refine_failure_requires_manual_input():
    app = make_app()
    app._overlay = FakeOverlay(visible=True)
    app._manual_export_count_fallback_allowed = False

    app._on_refine_result(None, "default", minutes=7, rate=2.5)

    assert app._overlay.manual_required_values == [True]
    assert app._overlay.counting_statuses[-1] is False


def test_creative_local_export_refine_failure_enables_manual_input():
    app = make_app()
    app._overlay = FakeOverlay(visible=True)
    app._manual_export_count_fallback_allowed = True

    app._on_refine_result(None, "default", minutes=7, rate=2.5)

    assert app._overlay.manual_required_values == [True]
    assert app._overlay.counting_statuses[-1] is False


def test_fast_export_hotzone_includes_true_top_right_button(monkeypatch):
    app = Application.__new__(Application)
    app._get_fast_export_target_hwnd = lambda cursor_x, cursor_y: 1001

    fake_win32gui = SimpleNamespace(
        IsWindow=lambda hwnd: True,
        IsWindowVisible=lambda hwnd: True,
        GetWindowRect=lambda hwnd: (0, 0, 1200, 800),
    )
    monkeypatch.setattr(main, "HAS_FAST_EXPORT_HOTZONE", True)
    monkeypatch.setattr(main, "win32gui", fake_win32gui)

    hotzone = app._get_fast_export_hotzone(1180, 28)

    assert hotzone is not None
    left, top, right, bottom = hotzone
    assert left <= 1180 <= right
    assert top <= 28 <= bottom


def test_fast_hotzone_release_marks_monitor_export_active(monkeypatch):
    app = make_app()
    app._is_exporting = False
    app._quit_requested = False
    app._fast_export_left_down = True
    app._last_fast_export_wait_at = 0.0
    app._fast_export_pending_click = {
        "at": time.monotonic(),
        "cursor": (1180, 28),
        "hotzone": (1000, 0, 1200, 100),
        "target_hwnd": 4242,
    }
    call_order = []
    app._prepare_export_count_fallback_policy = lambda: call_order.append("prepare")
    app._show_export_wait_overlay = (
        lambda minutes=None, rate=None: call_order.append("show_wait")
    )

    fake_win32api = SimpleNamespace(
        GetAsyncKeyState=lambda key: 0,
        GetCursorPos=lambda: (1180, 28),
    )
    fake_win32con = SimpleNamespace(VK_LBUTTON=1)
    monkeypatch.setattr(main, "HAS_FAST_EXPORT_HOTZONE", True)
    monkeypatch.setattr(main, "win32api", fake_win32api)
    monkeypatch.setattr(main, "win32con", fake_win32con)

    app._poll_fast_export_click_hotzone()

    assert call_order[:2] == ["show_wait", "prepare"]
    assert app._monitor.assumed_reasons == ["fast_hotzone"]
    assert app._monitor.assumed_targets == [4242]
    assert app._monitor.is_export_dialog_visible is True


def test_show_export_wait_overlay_flushes_ui_after_show(monkeypatch):
    app = Application.__new__(Application)
    app._pending_wait_payment_args = None
    app._export_wait_overlay = None
    call_order = []

    class FakeSignal:
        def connect(self, callback):
            call_order.append("connect")

    class FakeExportWaitOverlay:
        def __init__(self, seconds=5):
            self.finished = FakeSignal()

        def show_wait(self):
            call_order.append("show_wait")

    monkeypatch.setattr(main, "ExportWaitOverlay", FakeExportWaitOverlay)
    monkeypatch.setattr(
        main.QApplication,
        "processEvents",
        lambda: call_order.append("process_events"),
    )

    Application._show_export_wait_overlay(app, minutes=5, rate=2.5)

    assert call_order[-2:] == ["show_wait", "process_events"]


def test_titleless_pixcake_qt_window_is_valid_main_window(monkeypatch):
    fake_win32gui = SimpleNamespace(
        IsWindow=lambda hwnd: True,
        IsWindowVisible=lambda hwnd: True,
        GetWindowRect=lambda hwnd: (0, 0, 1600, 900),
    )
    monkeypatch.setattr(process_monitor, "HAS_WIN32", True)
    monkeypatch.setattr(process_monitor, "win32gui", fake_win32gui)
    monkeypatch.setattr(process_monitor, "get_window_title", lambda hwnd: "")
    monkeypatch.setattr(
        process_monitor, "get_window_class", lambda hwnd: "Qt5152QWindowIcon"
    )

    assert process_monitor.is_valid_target_main_window(2002) is True


class FakeImage:
    def copy(self):
        return self


def make_monitor_with_cached_lifecycle(pid=1001):
    monitor = process_monitor.ProcessMonitor.__new__(process_monitor.ProcessMonitor)
    monitor._current_pid = pid
    monitor._cached_export_count = None
    monitor._cached_export_count_at = None
    monitor._cached_export_count_pid = None
    monitor._last_export_capture_image = None
    monitor._last_export_capture_at = None
    monitor._last_export_capture_pid = None
    monitor._last_export_capture_dialog_mode = False
    return monitor


def test_export_count_cache_is_not_reused_after_pixcake_pid_changes():
    monitor = make_monitor_with_cached_lifecycle(pid=1001)
    monitor._cached_export_count = 1
    monitor._cached_export_count_at = time.monotonic()
    monitor._cached_export_count_pid = 1001
    monitor._current_pid = 2002

    assert monitor.get_recent_export_count() is None


def test_last_export_capture_is_not_reused_after_pixcake_pid_changes():
    monitor = make_monitor_with_cached_lifecycle(pid=1001)
    monitor._last_export_capture_image = FakeImage()
    monitor._last_export_capture_at = time.monotonic()
    monitor._last_export_capture_pid = 1001
    monitor._current_pid = 2002

    assert monitor.get_last_export_capture_image(max_age_seconds=30.0) is None


def test_expensive_export_count_resolution_prefers_live_count_over_stale_cache():
    app = make_app()
    app._monitor.cached_export_count = 1
    app._monitor.live_summary_count = 3

    count, source = app._resolve_export_count_for_payment(allow_expensive=True)

    assert (count, source) == (3, "live_capture")


def test_session_count_resolution_never_uses_cache_as_final_count():
    app = make_app()
    app._monitor.cached_export_count = 1
    app._monitor.live_summary_count = None
    app._monitor.live_image_count = None

    count, source = app._resolve_export_count_for_payment(
        allow_expensive=True,
        allow_cached=False,
    )

    assert count is None
    assert source == "default"


def test_cache_refine_result_requires_manual_input_instead_of_finalizing_one():
    app = make_app()
    app._overlay = FakeOverlay(visible=True)
    app._current_export_count = 0

    app._on_refine_result(1, "cache", minutes=7, rate=2.5)

    assert app._overlay.manual_required_values == [True]
    assert app._current_export_count == 0


def test_stale_refine_result_does_not_update_new_export_session():
    app = make_app()
    app._overlay = FakeOverlay(visible=True)
    app._active_export_session_id = 2
    app._current_export_count = 0

    app._on_refine_result(3, "live_capture", minutes=7, rate=2.5, session_id=1)

    assert app._current_export_count == 0
    assert app._overlay.display_updates == []


def test_wait_finished_shows_payment_before_expensive_counting(monkeypatch):
    app = make_app()
    app._overlay = FakeOverlay(visible=False)
    app._monitor.cached_export_count = 1
    app._monitor.live_summary_count = 3
    scheduled = []
    monkeypatch.setattr(
        main.QTimer,
        "singleShot",
        lambda delay_ms, callback: scheduled.append((delay_ms, callback)),
    )

    app._show_payment_overlay_after_wait(minutes=5, rate=2.5)

    assert app._monitor.capture_calls == 0
    assert app._overlay.payment_shows[0][1]["export_count"] == 0
    assert app._current_export_count == 0
    assert app._overlay.counting_statuses[-1] is True
    assert app._monitor.events[:2] == ["snapshot", "suspend"]
    assert scheduled


def test_manual_count_payment_confirmation_arms_paid_retry(monkeypatch):
    class AcceptedPasswordDialog:
        Accepted = 1

        def __init__(self, config, parent=None):
            self.authenticated = True

        def exec_(self):
            return self.Accepted

    app = make_app()
    app._overlay = FakeOverlay(visible=True)
    app._overlay.manual_required = True
    app._overlay.current_count = 3
    app._current_export_count = 0
    app._monitor.export_dialog_visible = True
    monkeypatch.setattr(main, "PasswordDialog", AcceptedPasswordDialog)

    app._on_payment_confirmed()

    assert app._current_export_count == 3
    assert app._payment_confirmed is True
    assert app._monitor.paid_retry_calls == 1
    assert app._monitor.restore_calls == 0
    assert app._monitor.post_payment_values[-1] is True
    assert app._monitor.hold_values[-1] is False


def test_paid_export_completion_waits_for_pixcake_exit_before_rearming():
    app = make_app()
    app._is_exporting = True
    app._payment_confirmed = True
    app._monitor.export_dialog_visible = True

    app._on_export_cancelled()

    assert app._awaiting_process_close_after_paid_export is True
    assert app._is_exporting is True
    assert app._payment_confirmed is True
    assert app._timer.started is False
    assert app._tray.running_states[-1] is False
    assert app._monitor.hold_values[-1] is True

    app._on_export_detected()

    assert app._show_export_wait_overlay_called is False
    assert app._overlay.payment_shows == []
