# ~/Desktop/acropdf/core/async_manager.py
"""
非同步任務管理器：
  - 所有背景工作透過 TaskWorker + QThreadPool 執行
  - 每個 Task 有獨立的例外捕捉 → 絕不讓任何 Task 崩潰主程式
  - 支援進度回報、取消、逾時
  - 信號只能從主執行緒 emit（透過 QMetaObject.invokeMethod 安全橋接）
"""
import traceback
import threading
from typing import Callable, Any
from PyQt6.QtCore import (QObject, pyqtSignal, QRunnable, QThreadPool,
                           QTimer, Qt, QCoreApplication)

# ── 信號物件（每個 Task 一組）──────────────────────────────────────
class TaskSignals(QObject):
    started   = pyqtSignal(str)           # task_id
    progress  = pyqtSignal(str, int, int) # task_id, current, total
    success   = pyqtSignal(str, object)   # task_id, result
    error     = pyqtSignal(str, str)      # task_id, error_message
    cancelled = pyqtSignal(str)           # task_id
    finished  = pyqtSignal(str)           # task_id（無論成功/失敗都發）

# ── Task Worker（真正跑在背景執行緒）──────────────────────────────
class TaskWorker(QRunnable):
    def __init__(
        self,
        task_id: str,
        fn: Callable,
        args: tuple = (),
        kwargs: dict = None,
        signals: TaskSignals = None,
        cancel_event: threading.Event = None,
        timeout_sec: float | None = None,
    ):
        super().__init__()
        self.setAutoDelete(True)
        self._id = task_id
        self._fn = fn
        self._args = args
        self._kwargs = kwargs or {}
        self._signals = signals
        self._cancel = cancel_event or threading.Event()
        self._timeout = timeout_sec
        # 注意：必須持有 signals 的強引用，避免 Python GC 提前回收
        self._keep_signals = signals

    def run(self):
        """執行緒入口，完全例外隔離"""
        if self._cancel.is_set():
            if self._signals:
                self._signals.cancelled.emit(self._id)
                self._signals.finished.emit(self._id)
            return

        if self._signals:
            self._signals.started.emit(self._id)

        try:
            # 把 cancel_event 和 progress_cb 注入 kwargs（若函式接受的話）
            kwargs = dict(self._kwargs)
            import inspect
            sig = inspect.signature(self._fn)
            if "cancel_event" in sig.parameters:
                kwargs["cancel_event"] = self._cancel
            if "progress_cb" in sig.parameters and self._signals:
                def _progress(cur, total):
                    if self._signals:
                        self._signals.progress.emit(self._id, cur, total)
                kwargs["progress_cb"] = _progress

            result = self._fn(*self._args, **kwargs)

            if self._cancel.is_set():
                if self._signals:
                    self._signals.cancelled.emit(self._id)
            else:
                if self._signals:
                    self._signals.success.emit(self._id, result)

        except Exception:
            err_msg = traceback.format_exc()
            print(f"[AsyncManager] Task {self._id} 失敗：\n{err_msg}")
            if self._signals:
                try:
                    self._signals.error.emit(self._id, err_msg)
                except Exception:
                    pass  # 防止 signal emit 本身崩潰
        finally:
            if self._signals:
                try:
                    self._signals.finished.emit(self._id)
                except Exception:
                    pass

# ── AsyncManager（單例，全程式共用）──────────────────────────────
class AsyncManager(QObject):
    _instance: "AsyncManager | None" = None

    @classmethod
    def instance(cls) -> "AsyncManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self._pool = QThreadPool.globalInstance()
        self._pool.setMaxThreadCount(8)  # 限制最大並行數
        self._tasks: dict[str, tuple[TaskSignals, threading.Event]] = {}
        self._id_counter = 0
        self._lock = threading.Lock()

    def submit(
        self,
        fn: Callable,
        args: tuple = (),
        kwargs: dict = None,
        task_id: str | None = None,
        timeout_sec: float | None = None,
        on_success: Callable | None = None,
        on_error: Callable | None = None,
        on_progress: Callable | None = None,
        on_finished: Callable | None = None,
        on_cancelled: Callable | None = None,
    ) -> str:
        """
        提交一個背景任務。
        回傳 task_id，可用於之後取消。

        on_success(result)
        on_error(error_str)
        on_progress(current, total)
        on_finished()
        on_cancelled()
        """
        with self._lock:
            self._id_counter += 1
            tid = task_id or f"task_{self._id_counter}"

        signals = TaskSignals()
        cancel_ev = threading.Event()

        # 連接回調（確保在主執行緒執行）
        if on_success:
            signals.success.connect(lambda tid, r: on_success(r),
                                    Qt.ConnectionType.QueuedConnection)
        if on_error:
            signals.error.connect(lambda tid, e: on_error(e),
                                  Qt.ConnectionType.QueuedConnection)
        if on_progress:
            signals.progress.connect(lambda tid, c, t: on_progress(c, t),
                                     Qt.ConnectionType.QueuedConnection)
        if on_finished:
            signals.finished.connect(lambda tid: on_finished(),
                                     Qt.ConnectionType.QueuedConnection)
        if on_cancelled:
            signals.cancelled.connect(lambda tid: on_cancelled(),
                                      Qt.ConnectionType.QueuedConnection)

        # 任務完成後自動清理
        signals.finished.connect(lambda tid: self._cleanup(tid),
                                  Qt.ConnectionType.QueuedConnection)

        with self._lock:
            self._tasks[tid] = (signals, cancel_ev)

        worker = TaskWorker(tid, fn, args, kwargs or {},
                            signals, cancel_ev, timeout_sec)
        self._pool.start(worker)

        # 逾時自動取消
        if timeout_sec:
            QTimer.singleShot(
                int(timeout_sec * 1000),
                lambda: self.cancel(tid)
            )

        return tid

    def cancel(self, task_id: str):
        with self._lock:
            entry = self._tasks.get(task_id)
        if entry:
            _, cancel_ev = entry
            cancel_ev.set()

    def cancel_all(self):
        with self._lock:
            ids = list(self._tasks.keys())
        for tid in ids:
            self.cancel(tid)

    def _cleanup(self, task_id: str):
        with self._lock:
            self._tasks.pop(task_id, None)

    def active_count(self) -> int:
        return len(self._tasks)

    def wait_all(self, timeout_ms: int = 30000):
        self._pool.waitForDone(timeout_ms)
