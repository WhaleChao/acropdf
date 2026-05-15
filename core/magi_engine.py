# ~/Desktop/acropdf/core/magi_engine.py
from __future__ import annotations

import re


class MAGIEngine:

    _DOC_PATTERNS = {
        "判決": r"判決|裁定|裁判",
        "書狀": r"起訴|答辯|聲請|陳報|補充理由",
        "合約": r"合約|合同|契約|協議",
        "函文": r"函|通知|公告|函告",
    }

    def smart_classify(self, doc) -> str:
        """智慧文件分類（合約/判決/書狀/函文/其他）"""
        text = ""
        fitz_doc = doc.fitz_doc if hasattr(doc, "fitz_doc") else doc
        if fitz_doc is None:
            return "其他"
        for i in range(min(3, fitz_doc.page_count)):
            text += fitz_doc[i].get_text()
        for label, pattern in self._DOC_PATTERNS.items():
            if re.search(pattern, text):
                return label
        return "其他"

    def extract_key_info(self, doc, doc_type: str) -> dict:
        """依文件類型擷取結構化資訊"""
        fitz_doc = doc.fitz_doc if hasattr(doc, "fitz_doc") else doc
        text = ""
        if fitz_doc:
            for i in range(min(5, fitz_doc.page_count)):
                text += fitz_doc[i].get_text()

        info: dict = {"doc_type": doc_type}

        # 日期
        dates = re.findall(r"\d{3,4}年\d{1,2}月\d{1,2}日|\d{4}/\d{1,2}/\d{1,2}", text)
        info["dates"] = dates[:5]

        # 案號
        case_nums = re.findall(r"[（(]\d{2,3}[）)][^\s]{2,20}[號号]", text)
        info["case_numbers"] = case_nums[:3]

        # 金額
        amounts = re.findall(r"新臺幣[\s]*[\d,]+元|[\d,]+萬元|NT\$[\d,]+", text)
        info["amounts"] = amounts[:5]

        # 當事人
        parties = re.findall(r"原告[：:]?\s*([^\n\s，,。]{2,10})|被告[：:]?\s*([^\n\s，,。]{2,10})", text)
        info["parties"] = [p[0] or p[1] for p in parties[:4]]

        return info

    def suggest_filename(self, doc) -> str:
        """產生建議檔名"""
        doc_type = self.smart_classify(doc)
        info = self.extract_key_info(doc, doc_type)
        date = info["dates"][0].replace("/", "") if info["dates"] else ""
        party = info["parties"][0] if info["parties"] else ""
        case = info["case_numbers"][0] if info["case_numbers"] else ""
        parts = [p for p in [date, party, doc_type, case] if p]
        name = "_".join(parts) or "未分類文件"
        # 清理非法字元
        name = re.sub(r'[<>:"/\\|?*]', "", name)
        return name[:60] + ".pdf"

    def legal_analysis(self, doc) -> str:
        """臺灣法律分析（相關法條/判例）"""
        text = ""
        fitz_doc = doc.fitz_doc if hasattr(doc, "fitz_doc") else doc
        if fitz_doc:
            for i in range(min(3, fitz_doc.page_count)):
                text += fitz_doc[i].get_text()

        articles = re.findall(r"(?:民法|刑法|行政訴訟法|民事訴訟法|刑事訴訟法)[第第]\d+條", text)
        unique_articles = list(dict.fromkeys(articles))

        if not unique_articles:
            return "未偵測到明確法條引用。"
        return "偵測到相關法條：\n" + "\n".join(f"• {a}" for a in unique_articles[:20])
