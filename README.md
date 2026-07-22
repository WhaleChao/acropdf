# AcroPDF

AcroPDF 是單機版 PDF 編輯工具，目標是提供接近商用 PDF 編輯器的本機工作流程。

## 目前版本

- app version: `1.0.18`
- 已驗證測試：`103 passed`
- macOS 產物：`AcroPDF.dmg`
- Windows 產物：`AcroPDF_Setup.exe`、`AcroPDF_win.zip`（由 GitHub Actions 的 Windows runner 建置）
- Release 產物會附 `.sha256` checksum。

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
- 針對私有安裝，正式 DMG 會放在 GitHub Release asset。
