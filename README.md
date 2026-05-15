# AcroPDF

AcroPDF 是單機版 PDF 編輯工具，目標是提供接近商用 PDF 編輯器的本機工作流程。

## 目前版本

- app version: `1.0.12`
- 已驗證測試：`96 passed`
- macOS 產物：`AcroPDF.dmg`
- Windows 產物：`AcroPDF_win.zip`（由 GitHub Actions 的 Windows runner 建置）

## 在另一台 Mac 安裝

1. 到 GitHub private repo 的 Releases。
2. 下載 `AcroPDF.dmg`。
3. 打開 DMG，將 `AcroPDF.app` 放進「應用程式」。

## 從原始碼打包

```bash
python3 -m pytest -q
python3 build_mac.py --skip-preflight
```

打包完成後產物會在：

- `dist/AcroPDF.app`
- `dist/AcroPDF.dmg`

Windows 版需在 Windows 或 GitHub Actions Windows runner 上建置：

```powershell
python -m pytest -q
python build_win.py --skip-preflight
```

打包完成後產物會在：

- `dist\AcroPDF\AcroPDF.exe`
- `dist\AcroPDF_win.zip`

## 注意

- `dist/`、`build/`、PDF 測試檔與 PyInstaller spec 檔不進版控。
- 針對私有安裝，正式 DMG 會放在 GitHub Release asset。
