#!/bin/zsh
set -euo pipefail

APP_PATH="/Applications/AcroPDF.app"
APP_NAME="AcroPDF"

echo "AcroPDF macOS 安全性解除工具"
echo "================================"
echo

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "此工具僅適用 macOS。"
  read -r "?按 Enter 結束..."
  exit 1
fi

if [[ ! -d "$APP_PATH" ]]; then
  echo "找不到 $APP_PATH"
  echo
  echo "請先打開 AcroPDF.dmg，將 AcroPDF.app 拖到「應用程式」後，再執行本工具。"
  read -r "?按 Enter 結束..."
  exit 1
fi

echo "目標：$APP_PATH"
echo
echo "本工具只會移除 AcroPDF.app 的下載隔離標記，不會關閉整台 Mac 的 Gatekeeper。"
echo

if xattr -p com.apple.quarantine "$APP_PATH" >/dev/null 2>&1; then
  echo "偵測到下載隔離標記，正在移除..."
else
  echo "未偵測到下載隔離標記，仍會確認子檔案狀態..."
fi

if ! xattr -dr com.apple.quarantine "$APP_PATH" 2>/tmp/acropdf_unblock_error.log; then
  echo
  echo "一般權限移除失敗，嘗試使用管理員權限。"
  echo "系統可能會要求輸入這台 Mac 的登入密碼。"
  sudo xattr -dr com.apple.quarantine "$APP_PATH"
fi

echo
echo "檢查 App 簽章狀態..."
if codesign --verify --deep --strict "$APP_PATH" >/dev/null 2>&1; then
  echo "簽章檢查完成。"
else
  echo "提醒：此私有版未使用 Apple Developer ID 公證，macOS 仍可能顯示未驗證開發者提示。"
fi

echo
echo "完成。正在開啟 $APP_NAME..."
open "$APP_PATH"
echo
echo "如果仍跳出安全性提示，請到：系統設定 > 隱私權與安全性 > 仍要打開。"
echo
read -r "?按 Enter 關閉此視窗..."
