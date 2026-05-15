#!/usr/bin/env python3
from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

APP_PATH = Path("/Applications/AcroPDF.app")


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("$ " + " ".join(cmd))
    return subprocess.run(cmd, check=check, text=True)


def main() -> int:
    print("AcroPDF macOS 安全性解除工具")
    print("================================")
    print()

    if platform.system() != "Darwin":
        print("此工具僅適用 macOS。")
        return 1

    if not APP_PATH.is_dir():
        print(f"找不到 {APP_PATH}")
        print("請先打開 AcroPDF.dmg，將 AcroPDF.app 拖到「應用程式」。")
        return 1

    print(f"目標：{APP_PATH}")
    print("只移除 AcroPDF.app 的下載隔離標記，不會關閉整台 Mac 的 Gatekeeper。")
    print()

    result = subprocess.run(
        ["xattr", "-dr", "com.apple.quarantine", str(APP_PATH)],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        print("一般權限移除失敗，嘗試使用管理員權限。")
        print("系統可能會要求輸入這台 Mac 的登入密碼。")
        run(["sudo", "xattr", "-dr", "com.apple.quarantine", str(APP_PATH)])

    print()
    print("檢查 App 簽章狀態...")
    verify = subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", str(APP_PATH)],
        text=True,
        capture_output=True,
    )
    if verify.returncode == 0:
        print("簽章檢查完成。")
    else:
        print("提醒：此私有版未使用 Apple Developer ID 公證，macOS 仍可能顯示未驗證開發者提示。")

    print()
    print("完成。正在開啟 AcroPDF...")
    run(["open", str(APP_PATH)], check=False)
    print("如果仍跳出安全性提示，請到：系統設定 > 隱私權與安全性 > 仍要打開。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
