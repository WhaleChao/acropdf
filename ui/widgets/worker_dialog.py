"""Keep a modal dialog and its workers alive until they have stopped."""
from PyQt6.QtCore import QThread, QTimer
from PyQt6.QtWidgets import QDialog


class WorkerDialog(QDialog):
    def running_workers(self):
        workers = list(self.findChildren(QThread))
        job = getattr(self, '_job', None)
        if job is not None: workers.append(job)
        worker = getattr(self, '_worker', None)
        if isinstance(worker, QThread) and worker not in workers:
            workers.append(worker)
        return [worker for worker in workers if worker.isRunning()]

    def done(self, result):
        workers = self.running_workers()
        if workers:
            self._pending_result = result
            for worker in workers:
                worker.requestInterruption()
            progress = getattr(self, '_progress', None)
            if progress:
                progress.setFormat('等候目前工作安全結束…')
            if not hasattr(self, '_close_timer'):
                self._close_timer = QTimer(self)
                self._close_timer.setInterval(50)
                self._close_timer.timeout.connect(self._finish_pending_close)
            self._close_timer.start()
            return
        super().done(result)

    def reject(self):
        self.done(QDialog.DialogCode.Rejected)

    def accept(self):
        self.done(QDialog.DialogCode.Accepted)

    def closeEvent(self, event):
        if self.running_workers():
            event.ignore()
            self.reject()
        else:
            super().closeEvent(event)

    def _finish_pending_close(self):
        if not self.running_workers():
            self._close_timer.stop()
            self.done(self._pending_result)
