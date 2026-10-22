"""Background work with callbacks delivered on the UI thread."""
import queue
import traceback
from concurrent.futures import ThreadPoolExecutor


class Tasks:
    def __init__(self, workers=6):
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="rh")
        self.done = queue.Queue()

    def submit(self, fn, *args, callback=None, error=None, **kwargs):
        def run():
            try:
                res = fn(*args, **kwargs)
                if callback:
                    self.done.put((callback, (res,)))
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                if error:
                    self.done.put((error, (e,)))
        return self.pool.submit(run)

    def call_soon(self, fn, *args):
        """Queue fn to run on the UI thread (safe to call from any thread)."""
        self.done.put((fn, args))

    def pump(self, limit=50):
        for _ in range(limit):
            try:
                cb, args = self.done.get_nowait()
            except queue.Empty:
                return
            try:
                cb(*args)
            except Exception:  # noqa: BLE001
                traceback.print_exc()

    def shutdown(self):
        self.pool.shutdown(wait=False, cancel_futures=True)
