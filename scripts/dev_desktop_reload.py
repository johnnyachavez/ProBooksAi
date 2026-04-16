#!/usr/bin/env python3
"""
Development launcher: restart the PySide6 desktop app when Python sources change.

Requires: ``pip install watchdog`` (listed under optional dev dependencies).

Usage (from repository root)::

    python scripts/dev_desktop_reload.py
    python scripts/dev_desktop_reload.py -- --help

On a normal window close, the child exits with code 0 and this script exits.
On a watched file change, the child is terminated and restarted.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:
    print(
        "dev_desktop_reload: install watchdog, e.g.  pip install watchdog  "
        'or  pip install -e ".[dev]"',
        file=sys.stderr,
    )
    sys.exit(1)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_WATCH_SUBDIRS = ("desktop_app", "probooks", "probooksai")
_WATCH_SUFFIXES = {".py"}


def _is_watchable(path: Path) -> bool:
    try:
        path.relative_to(_REPO_ROOT)
    except ValueError:
        return False
    parts = set(path.parts)
    if "__pycache__" in parts or ".git" in parts:
        return False
    return path.suffix.lower() in _WATCH_SUFFIXES


class _ChangeHandler(FileSystemEventHandler):
    def __init__(self, debounce_s: float, on_stable_change) -> None:  # type: ignore[no-untyped-def]
        super().__init__()
        self._debounce_s = debounce_s
        self._on_stable_change = on_stable_change
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def on_any_event(self, event):  # type: ignore[no-untyped-def]
        if getattr(event, "is_directory", False):
            return
        src = getattr(event, "src_path", None)
        if not src:
            return
        path = Path(src)
        if not _is_watchable(path):
            return
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(
                self._debounce_s, self._on_stable_change
            )
            self._timer.daemon = True
            self._timer.start()


def _spawn(app_args: list[str]) -> subprocess.Popen:
    cmd = [sys.executable, "-m", "desktop_app.main", *app_args]
    return subprocess.Popen(cmd, cwd=_REPO_ROOT, env=os.environ.copy())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the desktop app and restart it when sources change."
    )
    parser.add_argument(
        "--debounce",
        type=float,
        default=0.45,
        metavar="SEC",
        help="seconds to wait after last change before restarting (default: 0.45)",
    )
    parser.add_argument(
        "app_args",
        nargs=argparse.REMAINDER,
        help="arguments for desktop_app.main (prefix with -- if the first looks like an option)",
    )
    args = parser.parse_args()
    app_args = list(args.app_args)
    if app_args and app_args[0] == "--":
        app_args = app_args[1:]

    restart_flag = [False]
    proc_holder: list[subprocess.Popen | None] = [None]

    def on_stable_change() -> None:
        restart_flag[0] = True
        proc = proc_holder[0]
        if proc is not None and proc.poll() is None:
            proc.terminate()

    handler = _ChangeHandler(args.debounce, on_stable_change)
    observer = Observer()
    for name in _WATCH_SUBDIRS:
        d = _REPO_ROOT / name
        if d.is_dir():
            observer.schedule(handler, str(d), recursive=True)
    observer.start()

    exit_code = 0
    try:
        while True:
            restart_flag[0] = False
            proc = _spawn(app_args)
            proc_holder[0] = proc
            while proc.poll() is None:
                time.sleep(0.1)
                if restart_flag[0]:
                    break
            if proc.poll() is None:
                try:
                    proc.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            exit_code = 0 if proc.returncode is None else proc.returncode
            proc_holder[0] = None

            if not restart_flag[0]:
                break
            time.sleep(0.08)
    finally:
        observer.stop()
        observer.join(timeout=3)
        proc = proc_holder[0]
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
