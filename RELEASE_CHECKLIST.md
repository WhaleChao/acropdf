# AcroPDF Release Checklist

## 必做

- 更新 `main.py` 的 `APP_VERSION`。
- 執行 `python3 -m pytest -q`。
- macOS：執行 `python3 build_mac.py --skip-preflight`。
- Windows：由 GitHub Actions `Build Windows` 產出 `AcroPDF_win.zip`。
- 確認 Release asset 包含 SHA256 checksum。
- 確認 README 的安裝與 macOS 安全性提示仍正確。

## 無 Apple Developer ID 時

- DMG 可供私有內部使用，但不能宣稱已 notarize。
- 使用者若被 Gatekeeper 阻擋，可使用 DMG 內的 `解除 macOS 安全限制.command`。
- 僅對 private Release 下載的 AcroPDF 使用解除工具。

## 有 Apple Developer ID 後

- 使用 `build_mac.py --sign "Developer ID Application: ..."`。
- 使用 `notarytool` 上傳 DMG 並 staple。
- 驗證：

```bash
spctl --assess --type execute -vv /Applications/AcroPDF.app
spctl --assess --type open --context context:primary-signature -vv dist/AcroPDF.dmg
```

## 有 Windows 程式碼簽章憑證後

- 使用 `build_win.py --sign cert.pfx --sign-pass ...`。
- 驗證：

```powershell
Get-AuthenticodeSignature dist\AcroPDF\AcroPDF.exe
```
