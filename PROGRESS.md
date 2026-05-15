# AcroPDF 開發進度記錄

## 專案概覽
- **語言 / 框架**：Python 3.14 + PyQt6 + PyMuPDF (fitz)
- **目標**：跨平台（macOS / Windows）PDF 編輯器，對齊 Adobe Acrobat 功能集

---

## Commit 歷史

### 2026-05-05 — Desktop MD cleanup 狀態收斂
- 原桌面 `AcroPDF_開發計劃.md` 已歸檔至 `/Users/ai/Desktop/desktop_md_archive_20260505/`。
- 本專案不再列入 MAGI 桌面 MD 未完成項；後續以本檔追蹤產品進度。
- 本輪驗證：`python3 -m pytest -q tests` → **89 passed, 5 warnings in 3.93s**。
- 剩餘項目屬 AcroPDF 產品 roadmap，不是 MAGI cleanup blocker：
  - 浮水印 / 頁首頁尾 UI 對話框 polish
  - replace page 保留向量元素策略
  - Windows 版實機驗證
  - 打包後 OCR `TESSDATA_PREFIX` 路徑確認

### `5a8d0f5` — AcroPDF v1.0.1（標注工具、渲染修復、Undo/Redo）
- 螢光筆、底線、便利貼、文字框、圖章、標記塗黑 六種標注工具
- 修復：標注新增後不重繪（`is_modified` 分支改走同步渲染）
- 修復：儲存後灰畫面（`RenderSignals` GC race → `_pending_signals` 保留強參照）
- `document_saved` signal → view 自動清快取重建
- Undo/Redo 快照機制（BytesIO）；Cmd+Shift+Z 補綁 Redo

### `fdab77c` — 多頁選取、右鍵選單、頁面操作（2026-04-12）
- **縮圖面板**：QListWidget ExtendedSelection；Cmd+click 跳選、Shift+click 範圍選
- **縮圖右鍵選單**（對齊 Adobe Acrobat）：
  - 插入頁面 ▶（從 PDF / 空白頁在前 / 空白頁在後）
  - 刪除 / 擷取 / 取代 / 分割（均顯示選取頁數）
  - 旋轉 CW / CCW、浮水印、頁首頁尾、頁面屬性
- **主頁面右鍵選單**：標注工具快速啟動 + 頁面操作子選單
  - Bug fix：`CustomContextMenu` policy 需接 `customContextMenuRequested`，不能靠 `contextMenuEvent`
- **新增對話框**：
  - `ExtractDialog`：擷取頁面 → 另存新 PDF，支援預選頁
  - `PagePropertiesDialog`：尺寸 pt/mm、方向、旋轉角
  - `SplitDialog`：三模式（分割點 / 每頁獨立 / 依選取）
- `core/page_manager.py`：補 `insert_pdf()` alias

---

## 架構速查

```
acropdf/
├── main.py                  # 入口點
├── loader.py                # 熱重載 Launcher（外層守護程序）
├── build_mac.py             # macOS 打包腳本（PyInstaller → .app）
├── build_win.py             # Windows 打包腳本（PyInstaller → .exe）
├── core/
│   ├── document.py          # PDFDocument（信號：document_saved, document_modified）
│   └── page_manager.py      # 頁面增刪轉移操作
├── rendering/
│   └── renderer.py          # PageRenderer（sync/async）；RenderSignals GC 保護
├── ui/
│   ├── main_window.py       # 主視窗；工具列、選單、右鍵分派
│   ├── panels/
│   │   └── thumbnail_panel.py  # 縮圖列表（ExtendedSelection + 右鍵選單）
│   ├── viewer/
│   │   ├── pdf_view.py         # QScrollArea 頁面容器
│   │   └── page_widget.py      # 單頁 QWidget（繪製 + 工具事件）
│   └── dialogs/
│       ├── page_ops/
│       │   ├── extract_dialog.py
│       │   ├── split_dialog.py
│       │   └── page_properties_dialog.py
│       └── ...
└── acro_platform/
    └── ocr/                 # macOS Vision / Windows WinRT OCR

```

---

## 已知限制 / 待辦

- [ ] Shift+click 在 computer-use 自動測試中只能選到錨點相鄰頁（batch action 時序問題，手動測試正常）
- [ ] 浮水印 / 頁首頁尾 UI 對話框尚未實作（已有 stub handler）
- [ ] 取代頁面（replace）目前用 fitz `show_pdf_page`，不保留向量元素
- [ ] 打包後 OCR 路徑需設 `TESSDATA_PREFIX` 環境變數（見 build 腳本說明）
- [ ] Windows 版尚未實測（需 Win 環境驗證）

---

## 熱重載架構（loader.py）

```
loader.py（常駐）
    ↓  subprocess.Popen
main.py（PDF 應用程式）
    ↓  若 .py 檔變更
loader 殺舊程序 → 重啟 main.py（帶回上次開啟的 PDF 路徑）
```

loader 透過 `--last-file <path>` 傳遞上次開啟的 PDF，讓重啟後自動回到相同文件。
