"""Çalışan QThread'lerin merkezi kaydı.

Qt, hâlâ çalışan bir ``QThread`` nesnesi yok edilirse süreci ``abort()`` ile
sonlandırır (Windows'ta 0xc0000409). Uygulama kapanırken arka planda ağ ya da
FFmpeg bekleyen iş parçacıkları olabilir; bu modül onları izler, kapanışta
belirli bir süre bekler ve gerekirse Python'un sonlandırma aşamasını atlayarak
temiz çıkış yapılmasını sağlar.
"""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QThread

_lock = threading.Lock()
_threads: set[QThread] = set()


def track(thread: QThread) -> QThread:
    with _lock:
        _threads.add(thread)

    def _forget() -> None:
        with _lock:
            _threads.discard(thread)

    thread.finished.connect(_forget)
    return thread


def running() -> list[QThread]:
    with _lock:
        items = list(_threads)
    alive: list[QThread] = []
    for t in items:
        try:
            if t.isRunning():
                alive.append(t)
        except RuntimeError:  # C++ nesnesi zaten silinmiş
            with _lock:
                _threads.discard(t)
    return alive


def wait_all(timeout_ms: int) -> bool:
    """Tüm izlenen iş parçacıklarının bitmesini bekler; hepsi bittiyse True."""
    deadline = time.monotonic() + timeout_ms / 1000.0
    for t in running():
        remaining = int((deadline - time.monotonic()) * 1000)
        if remaining <= 0:
            break
        try:
            t.quit()
            t.wait(remaining)
        except RuntimeError:
            pass
    return not running()
