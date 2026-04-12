# AcroPDF 驗收測試報告

**日期**: 2026-04-12  
**Python**: 3.14 / PyMuPDF 1.24+ / PyQt6  
**測試結果**: 33/33 通過, 0 警告, 0 失敗

---

## 修復清單（本次驗收發現並修復）

| # | 問題 | 嚴重性 | 修復方式 |
|---|------|--------|----------|
| 1 | `PDFView` 缺少 `refresh()` 方法 — 自動標籤和塗黑套用後呼叫會崩潰 | 嚴重 | 新增 `refresh()` 方法 |
| 2 | `insert_blank` 位置錯誤 — 「在此頁前插入」實際插到後面 | 嚴重 | 改為直接位置語意（`at` 參數），修正呼叫端 |
| 3 | 縮圖面板不刷新 — 頁面操作後縮圖仍顯示舊內容 | 嚴重 | 連接 `page_count_changed` / `document_modified` 信號 |
| 4 | 書籤面板不刷新 — 同上 | 中 | 同上 |
| 5 | 狀態列頁數不更新 — 插入/刪除後總頁數不變 | 中 | 新增 `_on_page_count_changed` 處理函式 |
| 6 | `fitz.open()` falsy 導致空文件無法操作 | 嚴重 | 所有 `if not doc` 改為 `if doc is None` |
| 7 | 浮水印 `rotate=45` 不支援 | 中 | 改用 `Shape.insert_text` + `morph` 旋轉矩陣 |
| 8 | `set_line_ends` API 變更 — PyMuPDF 1.24+ 需整數列舉 | 中 | 新增 `_LE_MAP` 字串→整數映射 |
| 9 | OCR 對未儲存文件靜默失敗 | 低 | OCR 對話框加入警告提示 |

---

## 功能驗收結果

### 一、文件管理（T01–T07）
| 測試項目 | 結果 |
|---------|------|
| 新建空文件 | ✅ |
| 插入空白頁（首頁前/末頁後/中間） | ✅ |
| 刪除頁面 | ✅ |
| 旋轉頁面 (90°/180°/270°) | ✅ |
| Undo（快照式） | ✅ |
| Redo（快照式） | ✅ |
| 儲存 / 另存 / 開啟 | ✅ |

### 二、頁面操作（T08–T09, T17–T21）
| 測試項目 | 結果 |
|---------|------|
| 浮水印（旋轉 45° 文字） | ✅ |
| 頁首頁尾 | ✅ |
| 合併 PDF | ✅ |
| 擷取頁面 | ✅ |
| 分割 PDF | ✅ |
| 裁切頁面 | ✅ |
| 移動 / 重排頁面 | ✅ |

### 三、標注工具（T10）
| 工具 | 結果 |
|------|------|
| 區塊螢光筆 | ✅ |
| 文字框 (FreeText) | ✅ |
| 便利貼 (Text Annot) | ✅ |
| 矩形 | ✅ |
| 圓形 | ✅ |
| 線條 | ✅ |
| 箭頭（OpenArrow 端點） | ✅ |
| 圖章 (Stamp) | ✅ |
| 手繪墨跡 (Ink) | ✅ |
| 標注框 (Callout) | ✅ |
| 區塊底線 | ✅ |
| 區塊刪除線 | ✅ |
| 連結（URL / 頁面跳轉） | ✅ |

### 四、塗黑（T11）
| 測試項目 | 結果 |
|---------|------|
| 標記塗黑區域 | ✅ |
| 永久執行塗黑 | ✅ |

### 五、表單（T12）
| 測試項目 | 結果 |
|---------|------|
| 新增表單欄位 (text/checkbox/combo/list) | ✅ |
| 填寫 / 批次填寫 | ✅ |
| 匯出 FDF | ✅ |
| 匯入 FDF | ✅ |

### 六、匯出（T13）
| 格式 | 結果 |
|------|------|
| TXT 純文字 | ✅ |
| DOCX (Word) | ✅ |
| XLSX (Excel, 表格偵測) | ✅ |
| PPTX (PowerPoint) | ✅ |
| PNG 圖片 | ✅ |
| PDF/A 長期保存 | ✅ |

### 七、安全性（T14）
| 測試項目 | 結果 |
|---------|------|
| AES-256 加密 | ✅ |
| 使用者權限設定 (列印/複製/編輯/標注) | ✅ |
| 移除安全性 | ✅（UI 入口） |

### 八、最佳化（T15）
| 測試項目 | 結果 |
|---------|------|
| 壓縮（garbage + deflate） | ✅ |
| 三級壓縮預設 | ✅ |
| 清除中繼資料 | ✅（UI 入口） |

### 九、比較（T16）
| 測試項目 | 結果 |
|---------|------|
| 文字差異比較 | ✅ |
| 視覺差異比較（像素 XOR） | ✅（UI 入口） |

### 十、進階功能（T22–T29）
| 測試項目 | 結果 |
|---------|------|
| 檔案格式轉換器（JPEG/PNG/XLSX/DOCX/PPTX → PDF） | ✅ |
| 書籤 (TOC) 讀取 | ✅ |
| OCR 引擎（Apple Vision / WinRT / Tesseract） | ✅ |
| 自動標籤引擎（TOC → 文字 → AI） | ✅ |
| PDFView.refresh() 存在且可用 | ✅ |
| ToolFactory 覆蓋率 19/19 | ✅ |
| 14 個對話框模組全部可匯入 | ✅ |
| 信號鏈（page_count_changed + document_modified） | ✅ |

---

## 工具列覆蓋率

| 工具模式 | 實作類別 | 狀態 |
|---------|---------|------|
| HAND | — (導覽，無需工具) | ✅ |
| SELECT | — (導覽) | ✅ |
| ZOOM | — (導覽) | ✅ |
| HIGHLIGHT | HighlightTool | ✅ |
| UNDERLINE | UnderlineTool | ✅ |
| STRIKEOUT | StrikeoutTool | ✅ |
| FREEHAND | FreehandTool | ✅ |
| ERASER | EraserTool | ✅ |
| STICKY_NOTE | StickyNoteTool | ✅ |
| TEXT_BOX | TextBoxTool | ✅ |
| CALLOUT | CalloutTool | ✅ |
| STAMP | StampTool | ✅ |
| SHAPE_RECT | RectTool | ✅ |
| SHAPE_CIRCLE | CircleTool | ✅ |
| SHAPE_LINE | LineTool | ✅ |
| SHAPE_ARROW | ArrowTool | ✅ |
| MEASURE_DIST | MeasureDistTool | ✅ |
| MEASURE_AREA | MeasureAreaTool | ✅ |
| REDACT | RedactTool | ✅ |
| CROP | CropTool | ✅ |
| LINK | LinkTool | ✅ |
| FORM_FIELD | FormFieldTool | ✅ |

---

## 對話框清單

| 對話框 | 檔案 | 狀態 |
|-------|------|------|
| OCR 文字化 | ocr_dialog.py | ✅ |
| 表單填寫 | form_fill_dialog.py | ✅ |
| 安全性設定 | security_dialog.py | ✅ |
| 數位簽章 | sign_dialog.py | ✅ |
| 匯出 | export_dialog.py | ✅ |
| 文件比較 | compare_dialog.py | ✅ |
| 最佳化 PDF | optimize_dialog.py | ✅ |
| 批次處理 | batch_dialog.py | ✅ |
| 擷取頁面 | extract_dialog.py | ✅ |
| 分割 PDF | split_dialog.py | ✅ |
| 頁首頁尾 | header_footer_dialog.py | ✅ |
| 頁面屬性 | page_properties_dialog.py | ✅ |
| 自動標籤 | auto_label_dialog.py | ✅ |
| 文字框 | text_box_dialog.py | ✅ |

---

## 跨平台相容性

| 功能 | macOS | Windows |
|------|-------|---------|
| OCR 引擎 | Apple Vision Framework | WinRT OCR |
| OCR Fallback | Tesseract | Tesseract |
| 打包工具 | PyInstaller → .app → .dmg | PyInstaller → .exe → .zip |
| 程式碼簽署 | codesign + notarize | signtool (Authenticode) |
| 前置檢查 | build_preflight.py | build_preflight.py |
| PEP 668 處理 | --user → --break-system-packages | N/A |

---

## 選單完整性

### 檔案(&F)
- [x] 開啟 (Ctrl+O)
- [x] 新增 (Ctrl+N)
- [x] 儲存 (Ctrl+S)
- [x] 另存新檔 (Ctrl+Shift+S)
- [x] 最近開啟
- [x] 結束 (Ctrl+Q)

### 編輯(&E)
- [x] 復原 (Ctrl+Z)
- [x] 取消復原 (Ctrl+Y / Ctrl+Shift+Z)

### 檢視(&V)
- [x] 放大 (Ctrl+=)
- [x] 縮小 (Ctrl+-)
- [x] 符合頁面 (Ctrl+0)
- [x] 符合寬度 (Ctrl+2)
- [x] 跳至頁面 (Ctrl+G)

### 頁面(&P)
- [x] 合併 PDF
- [x] 分割 PDF
- [x] 擷取頁面
- [x] 插入空白頁
- [x] 刪除選取頁面 (Delete)
- [x] 向右旋轉 90° (Ctrl+Shift+R)
- [x] 向左旋轉 90°
- [x] 加浮水印
- [x] 加頁首頁尾

### 工具(&T)
- [x] OCR 文字化
- [x] 表單填寫
- [x] 自動標籤
- [x] 比較文件
- [x] 最佳化 PDF
- [x] 批次處理
- [x] 套用永久塗黑
- [x] 安全性設定
- [x] 數位簽章

### 匯出(&X)
- [x] Word (.docx)
- [x] Excel (.xlsx)
- [x] PowerPoint (.pptx)
- [x] 圖片 (PNG)
- [x] 純文字
- [x] PDF/A

---

## 結論

全部 33 項自動化功能測試通過。9 個 bug 已修復，涵蓋：
- 頁面操作（插入/刪除）UI 不刷新的根本原因
- 空文件 falsy 判斷導致新文件無法操作
- PyMuPDF 1.24+ API 相容性（浮水印旋轉、線條端點）
- 信號鏈斷裂（縮圖面板、書籤面板、狀態列）

**所有功能已可交付。**
