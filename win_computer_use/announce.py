"""announce() — decorator/context-manager that publishes activity + state."""
from __future__ import annotations
import functools
import time
from contextlib import contextmanager
from typing import Any, Callable

from . import activity, state


class EmergencyStopped(RuntimeError):
    pass


@contextmanager
def announce(tool: str, args: dict | None = None, *, gated: bool = True):
    """Wrap a tool call. If gated, raises EmergencyStopped when the hotkey flag is set.

    Pure read-only tools (screenshots, list_windows, get_cursor_position) should pass
    gated=False so reading doesn't get blocked.
    """
    if gated and state.is_emergency():
        raise EmergencyStopped(f"emergency stop is active; call emergency_resume() first")
    t0 = time.time()
    state.set_current_action(tool, args)
    try:
        yield
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        activity.append(tool, args, ok=False, elapsed_ms=elapsed, error=str(e))
        raise
    else:
        elapsed = int((time.time() - t0) * 1000)
        activity.append(tool, args, ok=True, elapsed_ms=elapsed)
    finally:
        state.clear_current_action()


def announced(name: str | None = None, *, gated: bool = True) -> Callable:
    """Decorator: wraps a function so calls publish to activity/state."""

    def deco(fn: Callable) -> Callable:
        tool_name = name or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any):
            # Build a serializable args dict using kwargs only; positional args are
            # logged as positional list to avoid signature introspection slowness.
            payload: dict[str, Any] = {}
            if args:
                payload["args"] = list(args)
            payload.update(kwargs)
            with announce(tool_name, payload, gated=gated):
                return fn(*args, **kwargs)

        return wrapper

    return deco
