# 第三方套件與商用發佈條件

此版本是內部測試候選版，未確認可對外以專有授權販售。`LICENSE` 的原始私有授權保持不變。

- PyQt6 官方提供 GPL 與商用授權；應取得適用的商用授權證據或審查所選授權條款。
  官方：https://www.riverbankcomputing.com/software/pyqt
- PyMuPDF 官方提供 AGPL 與商用授權；專有產品的發佈方案須另行確認。
  官方：https://pymupdf.io/licensing
- 字型、OCR 語料及其他套件仍需逐項審查版本、授權文字、再散布條件與 notice。
- `python scripts/license_inventory.py --output work/dependency-licenses.json` 可生成目前環境的版本與套件 metadata 清單。清單不是法律意見或發佈授權證明。
- macOS Developer ID／notarization 與 Windows Authenticode 憑證尚未配置。本機 ad-hoc 簽署只驗證 bundle 完整性。

直接依賴版本見 `requirements-lock.txt`；本次 macOS arm64 / Python 3.14 的完整環境快照見 `requirements-mac.lock`。

## 本次新增的標準驗證與色彩資源

- veraPDF CLI 1.30.2 未修改的 jar，SHA-256 `889075253fb9df4db5482efb8f8208fb3b4f2e00f5f7e1b1e31edf6fb4b69bb6`。依官方 MPL 2.0 或 GPL 3+ 雙授權，這份未修改附屬驗證器選用 MPL 2.0；完整 MPL 與 jar 內的第三方 notice 存在 `resources/validators/licenses`。對應原始碼：https://github.com/veraPDF/veraPDF-apps/releases/tag/v1.30.2 、https://github.com/veraPDF/veraPDF-library/tree/v1.30.2 。來源：https://software.verapdf.org/releases/verapdf-installer.zip 。授權說明：https://docs.verapdf.org/develop/ 。必須隨對外發佈提供 notices 和適用來源取得方式。
- ICC 的未修改 `sRGB2014.icc`，來源與完整許可保存在 `resources/color/LICENSE.txt`；官方允許複製、分發、嵌入及商用：https://registry.color.org/profile-library/ 。
- Ghostscript 為外部程序，採 AGPL／商用双授權，需確認產品整合與再散布方案；未擅自打包 Ghostscript。官方：https://ghostscript.com/licensing/index.html 。
- Java、LibreOffice、Tesseract 使用本機外部安裝；本版未再散布這些外部程序。使用其他人的印刷 ICC 或字型需自行確認適用權利。
- 已收集安裝環境中實際存在的 license／notice 文件至 `resources/third-party/licenses`，保留 SHA-256 與來源路徑的 `manifest.json`。沒有聲明的套件仍需人工授權審查，不能把 metadata 或清單当作已購買授權。
