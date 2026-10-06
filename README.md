# AcroPDF

AcroPDF 是單機版 PDF 編輯工具，目標是提供接近商用 PDF 編輯器的本機工作流程。

## 目前版本

- app version: `1.2.0`（內部測試候選版）
- 已驗證測試：`290 passed`（本次 macOS arm64 / Python 3.14）
- macOS 產物：`AcroPDF.dmg`
- Windows 產物：`AcroPDF_Setup.exe`、`AcroPDF_win.zip`（由 GitHub Actions 的 Windows runner 建置）
- Release 產物會附 `.sha256` checksum。

## 品質改善與已知限制

- 日間、夜間、跟隨系統主題；工具搜尋與 Cmd/Ctrl K 指令搜尋；小視窗自適應歡迎工作區。
- 原子保存、加密工作恢復、分頁／渲染一致性、真正的 radio 群組、FDF 往返與保留外觀的表單／註解扁平化。
- 永久塗黑移除底層內容；局部文字／圖片編輯加入範圍檢查與失敗回復。
- 遠端 AI 文字傳送前明確詢問目的地與頁範圍。
- PDF/A-1b／2b／3b 真正轉換、ICC 與字型嵌入，通過 veraPDF 才發佈輸出。
- PDF/X-1a:2001／3:2002／4 使用印刷 ICC；檢查 ICC、字型、頁面邊界及渲染，仍需印刷廠的獨立印前驗收。
- 無障礙內容標記包含 MCID、ParentTree、圖片替代文字、標題層級、閱讀順序；PDF/UA-1 匯出經 veraPDF 機器驗證，閱讀語意仍需人工審查。
- 字型真正替換、嵌入與子集化；OCR 保留畫面並寫入可搜尋文字；XFDF 註解交換、Office 經 LibreOffice 保留版面匯入。
- 批次加密使用設定密碼、Bates 連續編號、同名輸入區分、歸檔碰撞保護、取消時安全保留工作者。
- 此版本未取得獎項，也未完成授權、正式程式碼簽章、公證、Windows 實機與跨閱讀器商用驗收。

修正清單、驗證範圍與剩餘商用門檻見 [品質審查](docs/QUALITY_REVIEW.md) 與 [第三方授權](docs/THIRD_PARTY.md)。

可重跑的畫面與大檔檢查：

```bash
python scripts/quality_review.py --output work/quality-review
```

## 無視窗操作模式（--headless-op）

1.2.0 起，AcroPDF 可被其他程式（例如 MAGI）以子程序呼叫，不開視窗、不載入 Qt、不連網：

```bash
AcroPDF.app/Contents/MacOS/AcroPDF --headless-op <op> --input <絕對路徑> --output <絕對路徑> [--params-json '<JSON>']
```

- 只讀 `--input`；只寫 `--output`（同資料夾暫存檔 fsync 後原子更名，已存在則覆寫，但不得與輸入相同）。
- stdout 只輸出一行 JSON：`{"protocol_version":2,"ok":…,"op":…,"output":…,"output_sha256":…,"details":{…},"error":{"code":…,"message":…}|null}`；診斷訊息走 stderr。
- 結束碼：成功 `0`、參數錯誤 `64`、處理失敗 `2`。
- 不處理加密 PDF；轉換 PDF/A 時拒絕已簽署文件。

| op | 說明 | params（皆可省略） |
|---|---|---|
| `pdfa_convert` | Ghostscript 轉 PDF/A 後驗證；未通過驗證不發佈輸出 | `level`：`1b`/`2b`（預設）/`3b`；`gs_path`、`verapdf_path`（絕對路徑）；`timeout_sec` |
| `pdfa_validate` | 只檢查不寫檔，`--output` 可省略；不合規時 `ok:true`、`details.compliant:false` | `level`、`verapdf_path` |
| `vision_ocr` | Apple Vision（預設 zh-Hant、en）逐頁辨識，輸出帶隱形文字層的可搜尋 PDF；details 含每頁字數與信心分數 | `skip_text_pages`（預設 `true`）、`languages`、`dpi`（72–600，預設 300） |
| `capabilities` | 不需 input/output；回報 op、gs/veraPDF/Vision 可用性與版本 | — |

PDF/A 驗證：找到 veraPDF（`params.verapdf_path`、環境變數 `ACROPDF_VERAPDF`、PATH，或 App 內附 jar 加系統 Java）時 `details.validation = "verapdf"`，採其正式結果；找不到時 `"basic_only"`，只檢查 XMP pdfaid、字型內嵌、OutputIntent，正式驗證需 veraPDF。

## OpenDesk TW 一站式整合

AcroPDF 1.0.18 提供本機、版本化的 OpenDesk 整合協定。OpenDesk TW 可顯示 PDF 文件報告、執行渲染與往返 LIVE 驗證，並把使用者直接帶到 AcroPDF 的頁面整理、編輯、表單、簽署、OCR、保護、預檢、批次或 MAGI 工具。

- 整合只透過本機程序與 JSON 通訊，不上傳 PDF，也不回傳文件全文。
- 開啟既有 PDF 前由 OpenDesk 建立版本備份。
- OpenDesk TW 是公開的 MIT 啟動器；AcroPDF 維持本專案的私有授權與獨立安裝。
- 協定與開發測試方式詳見 `OPENDESK_INTEGRATION.md`。

## 在另一台 Mac 安裝

1. 到 GitHub private repo 的 Releases。
2. 下載 `AcroPDF.dmg`。
3. 打開 DMG，將 `AcroPDF.app` 放進「應用程式」。
4. 如果 macOS 顯示「無法驗證開發者」，請雙擊 DMG 內的 `解除 macOS 安全限制.command`，或執行本 repo 的 `scripts/unblock_acropdf_macos.command`。

### macOS 安全性提示處理

目前沒有 Apple Developer ID 憑證，所以 macOS 會把從 GitHub 下載的私有版本視為「未驗證開發者」App。請只對你從本 repo private Release 下載的 `AcroPDF.dmg` 使用以下方式。

一鍵方式：

1. 確認 `AcroPDF.app` 已放在 `/Applications`。
2. 雙擊 DMG 內的 `解除 macOS 安全限制.command`。
3. 若系統詢問是否允許執行，選「打開」。
4. 若終端機要求密碼，輸入這台 Mac 的登入密碼。

終端機方式：

```bash
python3 scripts/unblock_macos.py
```

手動方式：

1. 將 `AcroPDF.app` 放進「應用程式」。
2. 在 Finder 的「應用程式」中，按住 Control 並點選 `AcroPDF.app`。
3. 選「打開」。
4. 出現安全性提示時，再按「打開」。

如果仍被阻擋：

1. 開啟「系統設定」。
2. 進入「隱私權與安全性」。
3. 在下方安全性區塊找到 `AcroPDF` 被阻擋的訊息。
4. 按「仍要打開」。

信任此私有版本時，也可以用終端機移除下載隔離標記：

```bash
xattr -dr com.apple.quarantine /Applications/AcroPDF.app
```

執行後再從「應用程式」開啟 `AcroPDF.app`。

## 從原始碼打包

```bash
python3 -m pip install -r requirements-lock.txt
python3 -m pytest -q
python3 build_mac.py --skip-preflight
```

打包完成後產物會在：

- `dist/AcroPDF.app`
- `dist/AcroPDF.dmg`
- `dist/AcroPDF.dmg.sha256`

Windows 版需在 Windows 或 GitHub Actions Windows runner 上建置：

```powershell
python -m pytest -q
python build_win.py --skip-preflight
```

打包完成後產物會在：

- `dist\AcroPDF\AcroPDF.exe`
- `dist\AcroPDF_win.zip`
- `dist\AcroPDF_win.zip.sha256`
- `dist\AcroPDF_Setup.exe`（需 Inno Setup）
- `dist\AcroPDF_Setup.exe.sha256`

## 下載檔案驗證

macOS：

```bash
shasum -a 256 -c AcroPDF.dmg.sha256
```

Windows PowerShell：

```powershell
Get-FileHash .\AcroPDF_Setup.exe -Algorithm SHA256
Get-Content .\AcroPDF_Setup.exe.sha256
```

## 注意

- `dist/`、`build/`、PDF 測試檔與 PyInstaller spec 檔不進版控。
- 針對私有安裝，內部測試 DMG 會放在 GitHub Release asset。
