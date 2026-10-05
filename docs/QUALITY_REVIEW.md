# AcroPDF 1.1.1 本機品質審查

日期：2026-10-05。原始碼重新 clone 至桌面，改善保留在 `quality/desktop-studio` 分支。

## 結論與證據邊界

這是有實作與驗證證據的本機候選版。獎項屬外部評選，不能以自行打分宣稱獲獎或「零缺陷」。已知程式問題逐項修復；正式對外販售仍需第三方授權證據、正式簽章／公證及跨平台實機驗收。

Awwwards 的設計、可用性、創意、內容及 Webby 的視覺、導航、功能與整體體驗是本次設計審查的參考。FWA 是創意目標，未取得其評審結果。來源：https://www.awwwards.com/about-evaluation/ 、https://www.webbyawards.com/judging-criteria/ 、https://thefwa.com/about/ 。

## 缺失及修正

| 領域 | 原有缺失 | 已實作的改正 |
| --- | --- | --- |
| 日夜介面 | 主題只偵測一次、元件不一致 | 全 app 日間／夜間／跟隨系統；統一 palette、選单、側欄、對話框、畫布、向量圖示、焦點及不可用狀態 |
| 工作入口 | 空白頁無引導、工具難尋 | 歡迎工作區、最近文件、工作流程卡片、工具搜尋、Cmd/Ctrl K 指令搜尋；原生選單提供快捷鍵入口、搜尋結果輔助閱讀標籤、方向鍵略過不可用指令；小視窗直向卡片及捲動 |
| 保存／分頁 | 新文件無頁、取消保存仍關閉、Office 來源可能被覆寫、拖曳標籤索引錯誤 | A4 新頁、另存 PDF、原子 fsync 保存／保留權限；Mac 使用排他重新命名，避免硬連結發佈卡住及競爭覆寫；失敗／取消保留文件；同步標籤與文件；各文件視圖設定與信號清理 |
| 渲染 | 背景建立 QPixmap、舊工作回寫、重建殘留、最後頁空白 | QImage 工作者／GUI QPixmap、世代檢查、立即移除版面、導航主動渲染；24M 像素與 16384 邊長上限；錯誤可點擊重試 |
| 恢復／加密 | 沒有當機恢復、匯出加密破壞目前文件 crypt 狀態 | 加密原子快照、700/600 權限／校驗、恢復後另存；加密／移除保護在私有副本執行，原文件與 undo 保持可用 |
| 永久塗黑 | 掃描底層像素仍存在、歷史可恢復敏感內容 | 移除文字、相關圖片像素與圖形，清空 undo／redo 和舊恢復快照 |
| 文字／圖片 | 放不下會丟原文、編輯連帶刪除背景與其他內容 | 先檢查容量、缺字、相鄰文字與待塗黑；交易失敗回復；保留背景及向量；安全多行重排、旋轉單行／頁面座標修正 |
| 字型 | 假嵌入、名稱替換未生效 | 以實際字型資料判定；真正嵌入／替換／子集化，檢查缺字／重疊；ActualText 保留 space/NBSP 等精確 Unicode |
| 頁面 | 整頁取代保留舊內容、重排非法、擷取解密、分割可覆寫 | 取代完整頁物件、完整排列檢查；擷取／分割保留加密；來源／目的碰撞保護及全部暫存後發佈 |
| 表單 | radio 為 checkbox、扁平化丟外觀、Tab 排序未生效 | 真正 AcroForm radio 父子群組、外觀扁平化、PDF 2.0 widget Tab 順序、中文 FDF 往返 |
| 註解 | 區塊高亮無文字關聯、圖章名稱對錯、XFDF 空白或不可用 | 螢光、底線與刪除線按字元四邊形標記；文字框及指向標注先檢查完整外觀、失败保留輸入；指定頁攤平保留頁面物件／連結／書籤；14 款圖章依引擎正確編號；自訂圖章交易與旋轉位置；XML XFDF 實際註解交換、座標及中文、整批失敗回復 |
| 列印 | 失敗仍顯示完成、整頁按印表機 DPI 分配過大影像、PDF 輸出丟向量 | 私有文件列印、記憶體／邊長上限、取消與錯誤回饋；A4／A3／Letter／Legal、直橫向與份數；PDF 保留向量、攤平可列印標注及表單、權限及原檔／既有副本保護 |
| 預檢安全 | 只看影像色彩、只看一處圖片或水平 DPI、純描邊圖形觸發錯誤 | 每個實際呈現位置、兩軸／旋轉／內嵌圖片；文字、向量與巢狀 Form 色彩；不同字型物件分別列出；處理未使用的透明度值 |
| 匯出 | 靜默跳頁、錯檔名、比例失真、Excel 公式注入 | 單檔原子輸出；逐頁影像全部成功後發佈，不覆寫既有圖；PPT 頁面比例、Excel 字串／文字備援、真正 TIFF |
| PDF/A | 只有中繼資料宣告、ICC 不完整 | PDF/A-1b／2b／3b 真正轉換、標準 sRGB v2 ICC／字型嵌入；veraPDF 獨立驗證通過才儲存；加密明確同意解密副本，已簽來源拒絕改寫 |
| PDF/X | 假 SWOP／GRACoL 名稱、無實際 ICC | PDF/X-1a:2001／3:2002／4 真正轉換、印刷廠 CMYK ICC；檢查 ICC 位元組、OutputIntent、邊界、字型、頁數與渲染；不宣稱已經独立印前認證 |
| 無障礙 | 空結構樹、文字未與標記關聯、讀序 API 空實作 | 文字／圖片 MCID、ParentTree、Figure Alt、標題層級、頁面閱讀區段重排、Table/TR/TD 與實際內容關聯；只移動所選段落、限制 10,000 儲存格、重排保護混合內容標記；PDF/UA-1 匯出經 veraPDF 機器驗證；語意仍需人工審閱 |
| OCR | 辨識結果只在暫時 TextPage、中文丟字、使用舊磁碟內容 | 寫入持久隱藏 Unicode 文字層、保留畫面、使用含未儲存修改的快照、加密 KEEP、範圍驗證／取消；原生 Apple Vision 與 Tesseract 實際搜尋輸出；Windows 固定腳本與安全參數、明確語言缺失錯誤 |
| Office 匯入 | 長儲存格／投影片截斷、圖片表格遺失、暫存未清 | 用 LibreOffice 真實版面轉換，獨立使用者 profile、禁用未受信任巨集、逾時及清理；不以截斷文字冒充完成；多頁 TIFF 全頁轉換 |
| 批次／歸檔 | 固定 owner123、同步阻塞、同名覆寫、重複處理、Bates 重置 | 使用輸入密碼、背景私有快照、取消後不顯示成功／失敗彈窗、Bates 跨文件連續、同名來源分開、既有目的檔保護、一次分析、取消回饋、路徑穿越限制、工作者結束後才關閉 |
| 比對／範本 | 比對尺寸不同略過、多頁增刪漏報、比例其實是矩形數、範本寫進簽署 app | 實際像素遮罩／差異比例、尺寸與增刪頁、完整對照報告；範本存使用者資料、名稱／碰撞檢查、中文與安全變數置換 |
| 簽章／AI | 覆寫來源、簽舊文件、把有效當可信、遠端傳全文未同意 | 原子簽章與拒絕未保存、完整／有效／可信分開；遠端 AI 僅 HTTPS，目的地／範圍同意、拒絕重導向；本機預設 |
| 可重現性 | 無依賴鎖定、偏好被測試污染 | 直接與完整環境 lock、測試設定與恢復隔離、macOS／Windows × Python 3.12／3.14 CI、視覺腳本、實際第三方 notices 與版本／hash 清單 |

## 本輪追加審查（1.1.1）

新增 29 項輸出與回歸檢查，覆蓋多行／旋轉標注、文字容量及草稿保留、逐位置 DPI／內嵌影像、表格選取與混合內容保護、向量列印／份數／紙張／表單／非列印旗標、取消／故障、來源硬連結、列印權限、背景工作關閉與 RGB／透明度；新增排他發佈、競爭建立目的檔／符號連結與無硬連結環境下的列印、圖片匯出及單檔／批次分割檢查。

1.1.1 是本輪建置候選版；安裝結果以交付的 candidate-validation.json 與 installation-validation.json 為準。使用者已解鎖 Mac 並關閉舊程序；已實機開啟測試 PDF、切換夜間主題、搜尋並執行指令。最終編輯、輸出及安裝狀態以交付驗證紀錄為準。

## 已執行驗證

- 原始 103 項測試；本次完整測試 **271 passed**，macOS arm64 / Python 3.14 / Qt 6.11。
- pip check、compileall、git diff --check；實际字型／加密／輸出／故障回復檢查。
- PDF/A 三個等級由 veraPDF 1.30.2 驗證；PDF/UA-1 實際帶內容標記及嵌入字型文件通過 veraPDF。
- PDF/X 三等級實際 ICC、邊界、嵌入字型、頁數、渲染檢查；没有獨立 PDF/X 認證。
- Apple Vision 繁中測試文字完整辨識且像素不變；Tesseract 英文搜尋文字及像素不變；Office 實際長文字、表格、圖片檢查。這些固定樣本不等於任意掃描語料零誤差。
- 1280×900 日夜／文件、900×640 小視窗、夜間對話框與指令搜尋，原生 Qt 離屏畫面與對比度檢查。
- 36 次連續縮放，剩餘渲染 0；300 頁可跳到末頁並渲染。量測見 `validation.json`，不作跨裝置效能保證。
- macOS app 建置後需 final codesign strict、封裝版 integration-status／LIVE 往返驗證；安裝狀態與 hash 見交付的 `installation-validation.json`。

## 尚需外部資料或環境的商用門檻

| 項目 | 尚需驗收的條件 |
| --- | --- |
| 再散布授權 | PyQt、PyMuPDF、Ghostscript 整合及字型等適用權利／商用合約；notices 已附，未冒充已購買授權 |
| 正式程式碼信任 | Apple Developer ID／公證、Windows Authenticode；本機 ad-hoc 僅檢查封裝完整 |
| 原生與跨平台 | Mac 原生視窗基本流程已有實機證據；Windows CI 已配置但未遠端執行；其他 Retina／DPI 裝置、閱讀器、實體印表機、VoiceOver／Narrator 仍需驗收 |
| 標準與語意 | PDF/X 需印刷廠獨立驗證；PDF/UA 的內容意義、描述、表格表頭及閱讀順序要人工審閱；既有結構樹保留，複雜重複 Form／帶註解來源須先處理 |
| 高階版面 | 任意 RTL、垂直字排、複雜斜向多行、跨區段表格的語意不能靠自動猜測；編輯受安全範圍檢查限制，失敗保留原文 |
| Office 與 OCR | Word 輸出為可編輯文字、PPT 為視覺頁面；不等同任意 PDF 版面重建。需客戶文件、噪聲／直排掃描語料的實際正確率及時延驗收 |
| 信任與大規模可靠性 | 真正受信 PKI／TSA／OCSP／PAdES-LT/LTA、SMB/NAS、断電／多機／超大語料等不能以單機測試替代 |
| 設計目標 | 用戶及設計同行審閱、真實 Awwwards／Webby／FWA 評選；未取得獎項，不宣稱已達評審認可 |

這些條件不以停用按鈕當作修復；已有功能均按其實際能力提供，能力界限明確呈現。此清單是本次可驗證的發現，不能證明沒有未發現問題。

## 重跑

```bash
python -m pip install -r requirements-lock.txt
python -m pip check
python -m pytest -q
python scripts/quality_review.py --output work/quality-review
python scripts/license_inventory.py --output work/dependency-licenses.json
python scripts/collect_notices.py
python build_mac.py --skip-preflight
```

實機列印發現本機硬連結系統呼叫阻塞；已改用 macOS renamex_np(RENAME_EXCL)，保留競爭時不覆寫的原子保護。參考：https://github.com/apple-oss-distributions/xnu/blob/main/bsd/man/man2/rename.2 。

實作參考：https://pymupdf.readthedocs.io/en/latest/page.html 、https://pymupdf.readthedocs.io/en/latest/document.html 、https://doc.qt.io/qt-6/qprinter.html 。

標準參考：https://docs.verapdf.org/cli/validation/ 、https://ghostscript.readthedocs.io/en/gs10.07.0/VectorDevices.html 、https://pdfa.org/wp-content/uploads/2024/02/Well-Tagged-PDF-WTPDF-1.0.pdf 。授權來源與 notices 見 THIRD_PARTY.md。
