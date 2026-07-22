# OpenDesk TW × AcroPDF 本機整合協定

AcroPDF 1.0.18 提供協定版本 1，讓 OpenDesk TW 作為一站式文件入口，同時保留 AcroPDF 的完整原生 PDF 工作區。兩個程式皆在使用者電腦執行，不需要雲端帳號。

## 命令列介面

```bash
python3 main.py --integration-status
python3 main.py --integration-inspect /path/to/file.pdf
python3 main.py --integration-live-test /path/to/file.pdf
python3 main.py --opendesk --opendesk-tool pages /path/to/file.pdf
```

- `--integration-status`：回報版本、隱私模式及能力群組。
- `--integration-inspect`：回報頁數、文字、圖片、註解、表單、簽章、連結、書籤、附件、頁面尺寸與警示；不回傳全文。
- `--integration-live-test`：實際渲染首末頁，對序列化後的記憶體 PDF 再次開啟並確認頁數。
- `--opendesk-tool`：只接受程式內建白名單，不會把任意文字當成可執行命令。

所有 JSON 回應都包含 `protocol_version: 1`。失敗時仍輸出版本化 JSON，並以非零狀態碼結束。

## 隱私與安全界線

1. PDF 不會上傳；整合層只傳遞本機絕對路徑。
2. 文件報告只回傳統計與結構，不回傳文件內容。
3. 加密 PDF 只標示加密狀態，不繞過密碼。
4. OpenDesk 在交給 AcroPDF 編輯既有 PDF 前先建立時間戳記備份。
5. OpenDesk TW 的 MIT 授權不涵蓋 AcroPDF；AcroPDF 仍依本專案 `LICENSE` 授權。

## 開發與驗證

```bash
python3 -m pytest -q
python3 main.py --integration-status
python3 main.py --integration-live-test /path/to/sample.pdf
```

OpenDesk 可用環境變數指定引擎：

- `ACROPDF_EXECUTABLE`：已打包的 AcroPDF 執行檔。
- `ACROPDF_PYTHON`：執行桌面 `acropdf/main.py` 的 Python。

未指定時，OpenDesk 會依平台尋找桌面原始碼、應用程式資料夾與常見安裝位置，並以協定探測確認版本相容後才啟用 PDF 中心。
