# macOS 啟動崩潰修正（1.1.8）

## 原因與修正

1.1.7 的 macOS App 內附 Qt 6.11.0。在 macOS 27.2.1 設定應用程式圖示時，
`QImage::toCGImage()` 使用已釋放的色彩空間，造成 `CGColorSpaceGetType()` 內的
`EXC_BREAKPOINT / SIGTRAP`。原始碼也可在原生 Cocoa 平台重現。

此問題對應 Qt 的 QTBUG-147602：
<https://github.com/qt/qtbase/commit/08e464f85597>

- macOS 的一般依賴要求 `PyQt6-Qt6>=6.11.2`。
- 共用鎖定檔明確指定 macOS Qt runtime 6.11.2，與 `requirements-mac.lock` 一致。
- 打包前置檢查另外檢查 Qt runtime，避免只確認 PyQt6 Python bindings 的版本。
- 新增原生 Cocoa 子程序測試，實際載入並設定應用程式圖示；offscreen 測試不會經過此崩潰路徑。

## 重建

在乾淨的虛擬環境安裝 `requirements-lock.txt`，執行 `python -m pytest -q`，
再執行 `python build_mac.py --skip-preflight`。確認實際載入的
`PyQt6.QtCore.qVersion()` 為 6.11.2 或更新版本。

macOS 產物須另外驗證 codesign、實際啟動及開啟測試 PDF。
本機 ad-hoc 簽署不等於 Apple Developer ID 簽署或公證。
