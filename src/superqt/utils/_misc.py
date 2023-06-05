from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator

from superqt.utils._throttler import GenericSignalThrottler

if TYPE_CHECKING:
    from types import FunctionType

    from qtpy.QtCore import QObject


@contextmanager
def signals_blocked(obj: QObject) -> Iterator[None]:
    """Context manager to temporarily block signals emitted by QObject: `obj`."""
    previous = obj.blockSignals(True)
    try:
        yield
    finally:
        obj.blockSignals(previous)


@contextmanager
def throttling_disabled(obj: GenericSignalThrottler | FunctionType) -> Iterator[None]:
    """Context manager to temporarily disabling throttling on a throttled object."""
    if not isinstance(obj, GenericSignalThrottler):
        obj = getattr(obj, "throttler", None)
        if not isinstance(obj, GenericSignalThrottler):
            raise TypeError(
                "Expected GenericSignalThrottler or qthrottled decorated function, "
                f"got {type(obj)}"
            )

    prev, obj.throttle = obj.throttle, lambda: obj.triggered.emit()
    prev_flush, obj.flush = obj.flush, lambda: None
    try:
        yield
    finally:
        obj.throttle = prev
        obj.flush = prev_flush
