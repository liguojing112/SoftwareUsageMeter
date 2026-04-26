from types import SimpleNamespace

from main import Application


class FakeOverlay:
    def __init__(self, visible=False):
        self._visible = visible
        self.closed = False
        self.counting_statuses = []
        self.manual_required_values = []
        self.display_updates = []

    def isVisible(self):
        return self._visible

    def close_payment(self):
        self.closed = True
        self._visible = False

    def set_counting_status(self, counting):
        self.counting_statuses.append(bool(counting))

    def set_manual_export_count_required(self, required):
        self.manual_required_values.append(bool(required))

    def update_display(self, *args, **kwargs):
        self.display_updates.append((args, kwargs))


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
        self.is_process_running = True

    def set_export_state_hold(self, hold):
        self.hold_values.append(hold)

    def set_post_payment_pending(self, active):
        self.post_payment_values.append(active)

    def restore_target_interaction(self):
        self.restore_calls += 1
        return {"restored": True}

    def suspend_target_processes(self):
        self.suspend_calls += 1

    @property
    def main_hwnd(self):
        return None

    @property
    def lock_target_hwnds(self):
        return []


class FakeTimer:
    def __init__(self, minutes=7):
        self.minutes = minutes
        self.paused = False
        self.started = False

    def pause(self):
        self.paused = True

    def start(self):
        self.started = True

    def get_elapsed_minutes(self):
        return self.minutes


class FakeTray:
    def __init__(self):
        self.running_states = []
        self.notifications = []

    def set_running_state(self, state):
        self.running_states.append(state)

    def show_notification(self, title, message):
        self.notifications.append((title, message))


def make_app():
    app = Application.__new__(Application)
    app._is_exporting = True
    app._payment_confirmed = False
    app._current_export_count = 3
    app._export_wait_overlay = None
    app._pending_wait_payment_args = None
    app._overlay = FakeOverlay()
    app._monitor = FakeMonitor()
    app._timer = FakeTimer()
    app._tray = FakeTray()
    app._config = SimpleNamespace(rate=2.5, export_rate=1.0)
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


def test_normal_export_refine_failure_does_not_enable_manual_input():
    app = make_app()
    app._overlay = FakeOverlay(visible=True)
    app._manual_export_count_fallback_allowed = False

    app._on_refine_result(None, "default", minutes=7, rate=2.5)

    assert app._overlay.manual_required_values == []
    assert app._overlay.counting_statuses[-1] is False


def test_creative_local_export_refine_failure_enables_manual_input():
    app = make_app()
    app._overlay = FakeOverlay(visible=True)
    app._manual_export_count_fallback_allowed = True

    app._on_refine_result(None, "default", minutes=7, rate=2.5)

    assert app._overlay.manual_required_values == [True]
    assert app._overlay.counting_statuses[-1] is False
