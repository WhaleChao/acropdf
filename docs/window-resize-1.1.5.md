# AcroPDF 1.1.5 視窗調整修正

使用者提供的 1.1.4／macOS 27.0.1 崩潰報告顯示，視窗 geometry change 引發 QToolButton 重繪，經 QAppleIconEngine 到 AppKit 的 NSImageSymbolRepProvider，最後由 Objective-C exception 中止。這類原生例外無法由 Python try/except 修復。

Qt 工具列在窄視窗顯示的溢出按鈕會自行向 style 要求系統圖示，並非程式中明確指定的操作圖示。改在建立元件前安裝 macOS proxy style，以 AcroPDF 自繪 pixmap 取代水平／垂直工具列溢出、分頁關閉及搜尋清除圖示，避免這些小型控制項在調整尺寸時進入 SF Symbols 路徑。其餘元件仍使用原有 macOS style；Windows 不變更 style。保留日夜、鍵盤、分頁及溢出操作。

新增四種圖示的極小尺寸、高 DPI、所有 icon mode 回歸，以及日夜、多文件、重複縮放／移動視窗測試。安裝包提供唯測試用途的 `--verify-window-geometry REPORT.json`：使用暫存設定與自行生成的文件，執行 96 次視窗移動與尺寸調整、192 次小型圖示請求、工具列溢出、最大化／最小化還原，確認文件不被修改。Windows 安裝驗證亦執行同一診斷。

單次原生圖示探測未重現使用者的崩潰，不能據此聲稱完整復現；修正根據崩潰堆疊阻斷該圖示路徑，再以原生 Cocoa 安裝包重測。此修正不宣稱解決所有 Qt 或 macOS 原生圖示問題。

依據：[Qt QToolBarExtension 原始碼](https://github.com/qt/qtbase/blob/6.11/src/widgets/widgets/qtoolbarextension.cpp)、[Qt QIcon 文件](https://doc.qt.io/qt-6/qicon.html)。

此熱修從已交付的 1.1.4 建立，保留桌面原有的 `feat/headless-op` 1.2.0 分支，不覆寫該分支內容。
