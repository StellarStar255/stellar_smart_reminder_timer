"""Native macOS notifications posted as the app itself.

The osascript route ('tell application "System Events" to display
notification') posts under System Events' identity: wrong name, wrong icon,
and the user can only allow/deny it for *every* script on the machine.
UNUserNotificationCenter posts as StellarPulse, but only works from a real
signed bundle with a bundle identifier — running `python main.py` from a
checkout it is unavailable, hence `is_available()` and the osascript
fallback in NotificationService.
"""

from typing import Callable, Optional
import itertools
import sys

IS_MACOS = sys.platform == "darwin"

# UNAuthorizationOptions / UNNotificationPresentationOptions are not exposed
# as constants by every pyobjc build; the raw bit values are stable API.
_AUTH_BADGE = 1 << 0
_AUTH_SOUND = 1 << 1
_AUTH_ALERT = 1 << 2
_PRESENT_LIST = 1 << 3
_PRESENT_BANNER = 1 << 4

_center = None            # UNUserNotificationCenter, resolved once
_delegate = None          # kept alive: the center holds only a weak delegate
_available: Optional[bool] = None
_ids = itertools.count(1)
_on_click: Optional[Callable[[], None]] = None


def _make_delegate_class():
    import objc
    from Foundation import NSObject

    class _NotificationDelegate(
        NSObject,
        protocols=[objc.protocolNamed("UNUserNotificationCenterDelegate")],
    ):
        def userNotificationCenter_willPresentNotification_withCompletionHandler_(
            self, center, notification, completion_handler
        ):
            # Without this the banner is suppressed whenever StellarPulse is
            # frontmost — which is exactly when a timer usually finishes.
            # Sound is left off: the alarm is played separately.
            completion_handler(_PRESENT_BANNER | _PRESENT_LIST)

        def userNotificationCenter_didReceiveNotificationResponse_withCompletionHandler_(
            self, center, response, completion_handler
        ):
            try:
                if _on_click is not None:
                    # Hop onto the Qt event loop instead of touching widgets
                    # from inside an ObjC callback.
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(0, _on_click)
            except Exception:
                pass
            completion_handler()

    return _NotificationDelegate


def is_available() -> bool:
    """True if UNUserNotificationCenter can be used in this process."""
    global _center, _delegate, _available
    if _available is not None:
        return _available
    _available = False
    if not IS_MACOS:
        return False
    try:
        from Foundation import NSBundle
        from UserNotifications import UNUserNotificationCenter

        # Outside a bundle (plain `python main.py`) the identifier is nil or
        # the interpreter's, and currentNotificationCenter() raises.
        bundle_id = NSBundle.mainBundle().bundleIdentifier()
        if not bundle_id or bundle_id.startswith("org.python"):
            return False

        _center = UNUserNotificationCenter.currentNotificationCenter()
        if _center is None:
            return False
        _delegate = _make_delegate_class().alloc().init()
        _center.setDelegate_(_delegate)
        _available = True
    except Exception:
        _center = None
        _delegate = None
        _available = False
    return _available


def request_authorization():
    """Ask for notification permission (first launch shows the system prompt)."""
    if not is_available():
        return
    try:
        _center.requestAuthorizationWithOptions_completionHandler_(
            _AUTH_ALERT | _AUTH_SOUND | _AUTH_BADGE,
            lambda granted, error: None,
        )
    except Exception:
        pass


def set_click_handler(handler: Optional[Callable[[], None]]):
    """Called on the Qt thread when the user clicks a delivered notification."""
    global _on_click
    _on_click = handler


def send(title: str, message: str) -> bool:
    """Post a notification. Returns False if it could not be delivered."""
    if not is_available():
        return False
    try:
        from UserNotifications import (
            UNMutableNotificationContent, UNNotificationRequest
        )

        content = UNMutableNotificationContent.alloc().init()
        content.setTitle_(title)
        content.setBody_(message)
        # No sound here — NotificationService plays the alarm itself.

        request = UNNotificationRequest.requestWithIdentifier_content_trigger_(
            f"stellarpulse-{next(_ids)}", content, None
        )
        _center.addNotificationRequest_withCompletionHandler_(request, None)
        return True
    except Exception:
        return False
