"""RetroHome's built-in web browser (separate process, Qt WebEngine).

Every download is saved into a staging folder and, when finished, unpacked and filed into
roms/<system> by installer.install(). Results are appended to a JSON report the main app
reads when the browser closes.

    python -m retrohome.browser --url URL --rom-dir DIR --folder psx --report out.json
"""
import argparse
import json
import os
import queue
import sys
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QPoint, Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QCursor, QKeySequence
from PyQt6.QtTest import QTest
from PyQt6.QtWebEngineCore import QWebEngineDownloadRequest, QWebEnginePage, QWebEngineProfile
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QProgressBar,
                             QToolBar, QVBoxLayout, QWidget)

from .installer import InstallError, install
from .paths import cache_dir
from .systems import get_system

STYLE = """
QMainWindow, QWidget { background: #0a1020; color: #eef2fa; font-size: 15px; }
QToolBar { background: #121b36; border: none; padding: 6px; spacing: 6px; }
QToolButton { color: #eef2fa; padding: 6px 12px; border-radius: 8px; background: #1d2850; }
QToolButton:hover { background: #2b3a70; }
QLineEdit { background: #1d2850; border: 1px solid #2b3a70; border-radius: 8px; padding: 6px 10px; color: #eef2fa; }
QProgressBar { background: #1d2850; border: none; border-radius: 6px; height: 12px; text-align: center; }
QProgressBar::chunk { background: #40a0ff; border-radius: 6px; }
#bar { background: #121b36; }
#hint { color: #9aa6c0; font-size: 13px; }
#status { color: #f0be3c; }
"""


class Pad:
    """Optional gamepad polling via pygame (no window). Silent no-op if unavailable."""

    def __init__(self):
        self.ok = False
        self.prev = set()
        try:
            os.environ["SDL_VIDEODRIVER"] = "dummy"
            os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"
            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            import pygame
            from pygame._sdl2 import controller
            pygame.display.init()
            pygame.joystick.init()
            controller.init()
            self.pg, self.ctrl = pygame, controller
            self.pads = []
            self.count = -1
            self.ok = True
        except Exception:  # noqa: BLE001
            self.ok = False

    def _refresh(self):
        n = self.pg.joystick.get_count()
        if n == self.count:
            return
        self.count = n
        self.pads = []
        for i in range(n):
            try:
                if self.ctrl.is_controller(i):
                    self.pads.append(self.ctrl.Controller(i))
            except Exception:  # noqa: BLE001
                pass

    def poll(self):
        """-> (lx, ly, rx, ry, pressed_now:set) with axes in -1..1."""
        if not self.ok:
            return 0, 0, 0, 0, set()
        P = self.pg
        P.event.pump()
        self._refresh()
        lx = ly = rx = ry = 0.0
        held = set()
        names = {P.CONTROLLER_BUTTON_A: "a", P.CONTROLLER_BUTTON_B: "b", P.CONTROLLER_BUTTON_X: "x",
                 P.CONTROLLER_BUTTON_Y: "y", P.CONTROLLER_BUTTON_LEFTSHOULDER: "lb",
                 P.CONTROLLER_BUTTON_RIGHTSHOULDER: "rb", P.CONTROLLER_BUTTON_START: "start",
                 P.CONTROLLER_BUTTON_BACK: "select", P.CONTROLLER_BUTTON_DPAD_UP: "up",
                 P.CONTROLLER_BUTTON_DPAD_DOWN: "down", P.CONTROLLER_BUTTON_DPAD_LEFT: "left",
                 P.CONTROLLER_BUTTON_DPAD_RIGHT: "right"}
        for c in self.pads:
            try:
                ax = [c.get_axis(a) / 32767.0 for a in (P.CONTROLLER_AXIS_LEFTX, P.CONTROLLER_AXIS_LEFTY,
                                                       P.CONTROLLER_AXIS_RIGHTX, P.CONTROLLER_AXIS_RIGHTY)]
                if abs(ax[0]) > abs(lx): lx = ax[0]   # noqa: E701
                if abs(ax[1]) > abs(ly): ly = ax[1]   # noqa: E701
                if abs(ax[2]) > abs(rx): rx = ax[2]   # noqa: E701
                if abs(ax[3]) > abs(ry): ry = ax[3]   # noqa: E701
                for b, name in names.items():
                    if c.get_button(b):
                        held.add(name)
            except Exception:  # noqa: BLE001
                continue
        pressed = held - self.prev
        self.prev = held
        self.held = held
        return lx, ly, rx, ry, pressed


class View(QWebEngineView):
    def createWindow(self, _type):   # links that open new windows load here instead
        return self


class Browser(QMainWindow):
    def __init__(self, a):
        super().__init__()
        self.args = a
        self.system = get_system(a.folder)
        self.report_path = Path(a.report)
        self.results = []
        self.jobs = queue.Queue()
        self.downloads = {}
        self.active = 0                 # unpack jobs running
        self.active_lock = threading.Lock()
        self.setWindowTitle(f"RetroHome Browser - {a.title}")
        self.setStyleSheet(STYLE)

        storage = cache_dir() / "browser"
        self.profile = QWebEngineProfile("RetroHome", self)
        self.profile.setPersistentStoragePath(str(storage / "profile"))
        self.profile.setCachePath(str(storage / "cache"))
        self.profile.setDownloadPath(str(Path(a.rom_dir) / ".rh-downloads"))
        self.profile.downloadRequested.connect(self.on_download)

        self.view = View(self)
        self.view.setPage(QWebEnginePage(self.profile, self.view))
        self.view.urlChanged.connect(lambda u: self.address.setText(u.toString()))
        self.view.loadProgress.connect(lambda p: self.load_bar.setValue(p))

        tb = QToolBar()
        tb.setMovable(False)
        self.addToolBar(tb)

        def act(label, fn, key=None):
            x = QAction(label, self)
            x.triggered.connect(fn)
            if key:
                x.setShortcut(QKeySequence(key))
            tb.addAction(x)
            return x
        act("◀ Back", self.view.back, "Alt+Left")
        act("Forward ▶", self.view.forward, "Alt+Right")
        act("⟳", self.view.reload, "F5")
        act("Game page", lambda: self.go(a.home or a.url))
        if a.hashes:
            act("Supported files", lambda: self.go(a.hashes))
        self.address = QLineEdit()
        self.address.returnPressed.connect(lambda: self.go(self.address.text()))
        tb.addWidget(self.address)
        act("Close", self.close, "Ctrl+W")

        bar = QWidget()
        bar.setObjectName("bar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 6, 12, 6)
        self.where = QLabel(f"Downloads go to  roms/{a.folder}  ({self.system.name})")
        self.status = QLabel("")
        self.status.setObjectName("status")
        self.dl_bar = QProgressBar()
        self.dl_bar.setMaximumWidth(260)
        self.dl_bar.hide()
        hint = QLabel("Pad: L-stick pointer · A click · R-stick/D-pad scroll · LB/RB back/forward · "
                      "Y address bar · X supported files · Menu close")
        hint.setObjectName("hint")
        lay.addWidget(self.where)
        lay.addWidget(self.dl_bar)
        lay.addWidget(self.status, 1)
        lay.addWidget(hint)
        self.load_bar = QProgressBar()
        self.load_bar.setMaximumHeight(3)
        self.load_bar.setTextVisible(False)

        central = QWidget()
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self.load_bar)
        v.addWidget(self.view, 1)
        v.addWidget(bar)
        self.setCentralWidget(central)

        self.pad = Pad()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)
        self.last_tick = time.time()
        self.go(a.url)

    # ------------------------------------------------------------ navigation
    def go(self, text):
        text = text.strip()
        if not text:
            return
        if "://" not in text:
            text = ("https://" + text) if "." in text and " " not in text else \
                "https://duckduckgo.com/?q=" + QUrl.toPercentEncoding(text).data().decode()
        self.view.setUrl(QUrl(text))

    # ------------------------------------------------------------ downloads
    def on_download(self, item: QWebEngineDownloadRequest):
        folder = Path(self.args.rom_dir) / ".rh-downloads"
        folder.mkdir(parents=True, exist_ok=True)
        item.setDownloadDirectory(str(folder))
        item.accept()
        self.downloads[id(item)] = item
        self.dl_bar.show()
        self.dl_bar.setValue(0)
        self.status.setText(f"Downloading {item.downloadFileName()}…")

        def progress():
            total = item.totalBytes()
            if total > 0:
                self.dl_bar.setValue(int(100 * item.receivedBytes() / total))
                mb = item.receivedBytes() / 1e6
                self.status.setText(f"Downloading {item.downloadFileName()}  {mb:.0f} / {total / 1e6:.0f} MB")

        def finished():
            state = item.state()
            path = Path(item.downloadDirectory()) / item.downloadFileName()
            self.downloads.pop(id(item), None)
            if state == QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
                self.status.setText(f"Unpacking {path.name}…")
                self.jobs.put(path)
                with self.active_lock:
                    self.active += 1
                threading.Thread(target=self._install_worker, daemon=True).start()
            else:
                self.status.setText(f"Download stopped: {path.name}")
            if not self.downloads:
                self.dl_bar.hide()
        item.receivedBytesChanged.connect(progress)
        item.isFinishedChanged.connect(finished)

    def _install_worker(self):
        try:
            path = self.jobs.get_nowait()
        except queue.Empty:
            return
        try:
            res = install(path, Path(self.args.rom_dir), self.args.folder)
        except InstallError as e:
            res = {"status": "error", "message": str(e), "files": [], "download": str(path)}
        except Exception as e:  # noqa: BLE001
            res = {"status": "error", "message": f"{path.name}: {e}", "files": [], "download": str(path)}
        finally:
            with self.active_lock:
                self.active -= 1
        res["time"] = time.time()
        self.results.append(res)
        try:
            self.report_path.write_text(json.dumps(self.results), encoding="utf-8")
        except OSError:
            pass

    # ------------------------------------------------------------ gamepad + status
    def tick(self):
        now = time.time()
        dt = min(0.05, now - self.last_tick)
        self.last_tick = now
        if self.results and self.status.property("shown") != len(self.results):
            r = self.results[-1]
            self.status.setProperty("shown", len(self.results))
            self.status.setText(("✓ " if r["status"] == "ok" else "⚠ ") + r["message"])
        lx, ly, rx, ry, pressed = self.pad.poll()
        if not self.pad.ok:
            return

        def curve(v):
            return 0.0 if abs(v) < 0.15 else (abs(v) - 0.15) / 0.85 * (1 if v > 0 else -1)
        mx, my = curve(lx), curve(ly)
        if mx or my:
            speed = 1400 * dt * (1 + 1.5 * max(abs(mx), abs(my)))
            p = QCursor.pos()
            QCursor.setPos(p + QPoint(int(mx * abs(mx) * speed), int(my * abs(my) * speed)))
        held = getattr(self.pad, "held", set())
        sy = curve(ry) * 1600 * dt + (900 * dt if "down" in held else -900 * dt if "up" in held else 0)
        sx = curve(rx) * 1600 * dt
        if sx or sy:
            self.view.page().runJavaScript(f"window.scrollBy({int(sx)}, {int(sy)})")
        if "a" in pressed:
            target = self.view.focusProxy() or self.view
            QTest.mouseClick(target, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                             target.mapFromGlobal(QCursor.pos()))
        if "b" in pressed or "lb" in pressed:
            self.view.back()
        if "rb" in pressed:
            self.view.forward()
        if "x" in pressed and self.args.hashes:
            self.go(self.args.hashes)
        if "y" in pressed:
            self.address.setFocus()
            self.address.selectAll()
            if os.environ.get("SteamDeck") == "1" or os.environ.get("SteamGamepadUI"):
                os.system("xdg-open steam://open/keyboard >/dev/null 2>&1 &")
        if "start" in pressed:
            self.close()

    def closeEvent(self, e):
        # let any running unpack finish so the report is complete
        deadline = time.time() + 120
        if self.active:
            self.status.setText("Finishing unpacking before closing…")
        while self.active and time.time() < deadline:
            QApplication.processEvents()
            time.sleep(0.05)
        super().closeEvent(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--home", default="")
    ap.add_argument("--hashes", default="")
    ap.add_argument("--rom-dir", required=True)
    ap.add_argument("--folder", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--fullscreen", action="store_true")
    a = ap.parse_args()
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu-sandbox")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("RetroHome Browser")
    try:
        from PyQt6.QtGui import QIcon
        from .paths import resource
        app.setWindowIcon(QIcon(str(resource("assets", "icon.png"))))
    except Exception:  # noqa: BLE001
        pass
    w = Browser(a)
    if a.fullscreen:
        w.showFullScreen()
    else:
        w.resize(1280, 800)
        w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
