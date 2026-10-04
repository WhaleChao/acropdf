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

## 1.1.0 品質與商用發佈關卡

- [ ] 保留完整測試日誌、視覺回顧 `validation.json`、依賴清單與 checksum。
- [ ] macOS 最終 bundle 修改完畢後重新簽署並通過 `codesign --verify --deep --strict`。
- [ ] 在 Windows 真實執行 CI 與安裝／文件工作流；未執行前不能宣稱跨平台通過。
- [ ] 完成 PyQt、PyMuPDF、字型及其他套件的商用再散布授權審查。
- [ ] 正式公開版本完成 Developer ID、公證及 Windows 程式碼簽章。
- [ ] PDF/A／X／UA 等功能只有通過相應外部驗證器才可開啟合規宣告。
- [ ] 以原始文件語料完成內容保留、OCR、Office 保真、簽章信任、列印與視障操作驗收。
- [ ] 完成 `docs/QUALITY_REVIEW.md` 的 P0/P1 門檻後才可標為可商用；獎項必須有實際評審結果。
