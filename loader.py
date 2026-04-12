#!/usr/bin/env python3
"""
AcroPDF 熱重載 Launcher
=======================
用法：
    python3 loader.py [initial_pdf_path]

功能：
- 啟動 main.py 作為子程序
- 監聽 acropdf/ 目錄所有 .py 檔的變更（mtime）
- 偵測到變更後自動殺掉舊程序、重啟（帶回上次開啟的 PDF）
- 子程序將當前開啟的 PDF 路徑寫入 .loader_state，loader 讀取後傳給下一次啟動

按 Ctrl+C 關閉 loader 及子程序。
"""

import os
import sys
import time
import signal
import subprocess
import threading
import json
from pathlib import Path

# ── 設定 ────────────────────────────────────────────────────
WATCH_DIRS = ["ui", "core", "rendering", "acro_platform", "app"]
WATCH_EXT  = {".py"}
POLL_INTERVAL = 1.0          # 秒，輪詢間隔
RESTART_DEBOUNCE = 0.8       # 秒，變更後等待（避免連存多次重複重啟）
STATE_FILE = Path(".loader_state")   # 子程序儲存當前 PDF 路徑

# ── 狀態 ────────────────────────────────────────────────────
_child: subprocess.Popen | None = None
_lock = threading.Lock()
_restart_pending = False
_stop = False


# ════════════════════════════════════════════════════════════
# 工具函數
# ════════════════════════════════════════════════════════════

def _collect_mtimes(base: Path) -> dict[str, float]:
    """掃描所有受監控目錄的 .py 檔，回傳 {path: mtime}。"""
    mtimes: dict[str, float] = {}
    for d in WATCH_DIRS:
        target = base / d
        if not target.is_dir():
            continue
        for f in target.rglob("*"):
            if f.suffix in WATCH_EXT:
                try:
                    mtimes[str(f)] = f.stat().st_mtime
                except OSError:
                    pass
    # 也監控根目錄的 main.py
    for name in ("main.py",):
        p = base / name
        if p.exists():
            try:
                mtimes[str(p)] = p.stat().st_mtime
            except OSError:
                pass
    return mtimes


def _read_last_file() -> str | None:
    """從 .loader_state 讀取上次開啟的 PDF 路徑。"""
    try:
        data = json.loads(STATE_FILE.read_text())
        path = data.get("current_file")
        if path and os.path.isfile(path):
            return path
    except Exception:
        pass
    return None


def _kill_child():
    global _child
    with _lock:
        if _child and _child.poll() is None:
            try:
                if sys.platform == "win32":
                    _child.terminate()
                else:
                    os.killpg(os.getpgid(_child.pid), signal.SIGTERM)
            except Exception:
                try:
                    _child.kill()
                except Exception:
                    pass
            _child.wait(timeout=5)
        _child = None


def _launch(base: Path, pdf_path: str | None = None):
    """啟動 main.py 子程序。"""
    global _child
    _kill_child()

    cmd = [sys.executable, str(base / "main.py")]
    if pdf_path:
        cmd.append(pdf_path)

    kwargs: dict = {}
    if sys.platform != "win32":
        kwargs["start_new_session"] = True   # 子程序自己一個 process group，方便整組殺

    with _lock:
        _child = subprocess.Popen(cmd, **kwargs)

    print(f"[loader] 🚀 啟動 main.py (pid={_child.pid})"
          + (f"  ← {pdf_path}" if pdf_path else ""))


def _schedule_restart(base: Path):
    """Debounce：等待短暫時間後重啟，避免連存多次。"""
    global _restart_pending
    if _restart_pending:
        return
    _restart_pending = True

    def _do():
        global _restart_pending
        time.sleep(RESTART_DEBOUNCE)
        pdf = _read_last_file()
        print(f"[loader] 🔄 偵測到變更，重啟中…")
        _launch(base, pdf)
        _restart_pending = False

    threading.Thread(target=_do, daemon=True).start()


# ════════════════════════════════════════════════════════════
# 主監控迴圈
# ════════════════════════════════════════════════════════════

def run(base: Path, initial_pdf: str | None):
    global _stop

    print("=" * 56)
    print("  AcroPDF Loader — 熱重載模式")
    print(f"  監控目錄: {', '.join(WATCH_DIRS)}")
    print(f"  輪詢間隔: {POLL_INTERVAL}s")
    print("  按 Ctrl+C 離開")
    print("=" * 56)

    # 初始啟動
    _launch(base, initial_pdf)
    prev_mtimes = _collect_mtimes(base)

    def _on_sigint(*_):
        global _stop
        print("\n[loader] 收到 Ctrl+C，關閉中…")
        _stop = True
        _kill_child()
        STATE_FILE.unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGINT, _on_sigint)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, _on_sigint)

    while not _stop:
        time.sleep(POLL_INTERVAL)

        # 子程序若自己關掉（使用者關視窗），loader 也退出
        with _lock:
            child = _child
        if child is not None and child.poll() is not None:
            print("[loader] main.py 已結束，loader 退出。")
            STATE_FILE.unlink(missing_ok=True)
            break

        # 掃描 mtime 差異
        curr = _collect_mtimes(base)
        changed = [
            p for p, mt in curr.items()
            if prev_mtimes.get(p) != mt
        ]
        # 也補偵測刪除的檔案
        changed += [p for p in prev_mtimes if p not in curr]

        if changed:
            for p in changed[:3]:
                rel = os.path.relpath(p, base)
                print(f"[loader] 📝 變更: {rel}")
            if len(changed) > 3:
                print(f"[loader]    …共 {len(changed)} 個檔案")
            _schedule_restart(base)
            prev_mtimes = curr
        else:
            # 新增檔案也要納入監控
            if set(curr) != set(prev_mtimes):
                prev_mtimes = curr


# ════════════════════════════════════════════════════════════
# 入口
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    base = Path(__file__).parent.resolve()
    os.chdir(base)   # 確保工作目錄在 acropdf/

    initial = None
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        initial = os.path.abspath(sys.argv[1])

    run(base, initial)
