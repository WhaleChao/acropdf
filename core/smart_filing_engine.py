# ~/Desktop/acropdf/core/smart_filing_engine.py
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass


@dataclass
class FilingRule:
    pattern: str           # 正規表達式
    category: str          # 文件類別
    subdirectory: str      # 子目錄模板
    filename_template: str # 檔名模板


class SmartFilingEngine:

    @staticmethod
    def default_legal_rules() -> list[FilingRule]:
        return [
            FilingRule(
                pattern=r"判決|裁定",
                category="判決書",
                subdirectory="判決/{date}",
                filename_template="{date}_{party}_判決.pdf",
            ),
            FilingRule(
                pattern=r"起訴狀|答辯狀|聲請書|陳報狀",
                category="書狀",
                subdirectory="書狀/{date}",
                filename_template="{date}_{party}_書狀.pdf",
            ),
            FilingRule(
                pattern=r"合約|合同|契約",
                category="合約",
                subdirectory="合約/{date}",
                filename_template="{date}_合約.pdf",
            ),
            FilingRule(
                pattern=r"繳費|收費|費用",
                category="財務",
                subdirectory="財務/{date}",
                filename_template="{date}_費用單.pdf",
            ),
        ]

    def analyze_and_file(self, input_dir: str, output_dir: str,
                         rules: list[FilingRule] | None = None) -> list[dict]:
        """掃描 → 分析 → 命名 → 歸檔"""
        import fitz
        if rules is None:
            rules = self.default_legal_rules()
        results = []
        for fname in os.listdir(input_dir):
            if not fname.lower().endswith(".pdf"):
                continue
            src = os.path.join(input_dir, fname)
            try:
                doc = fitz.open(src)
                text = "".join(doc[i].get_text() for i in range(min(3, doc.page_count)))
                doc.close()
            except Exception as e:
                results.append({"file": fname, "error": str(e)})
                continue

            matched_rule: FilingRule | None = None
            for rule in rules:
                if re.search(rule.pattern, text):
                    matched_rule = rule
                    break

            if matched_rule is None:
                matched_rule = FilingRule(
                    pattern="",
                    category="未分類",
                    subdirectory="未分類",
                    filename_template="{original}",
                )

            # 解析日期
            dates = re.findall(r"\d{3,4}年\d{1,2}月\d{1,2}日", text)
            date_str = dates[0].replace("年", "").replace("月", "").replace("日", "") if dates else ""
            parties = re.findall(r"原告[：:]?\s*([^\n\s，,。]{2,8})", text)
            party_str = parties[0] if parties else ""

            subdir = (matched_rule.subdirectory
                      .replace("{date}", date_str)
                      .replace("{party}", party_str))
            out_dir = os.path.join(output_dir, subdir)
            os.makedirs(out_dir, exist_ok=True)

            out_name = (matched_rule.filename_template
                        .replace("{date}", date_str)
                        .replace("{party}", party_str)
                        .replace("{original}", fname))
            out_name = re.sub(r'[<>:"/\\|?*]', "", out_name)
            if not out_name.endswith(".pdf"):
                out_name += ".pdf"
            dst = os.path.join(out_dir, out_name)
            shutil.copy2(src, dst)
            results.append({
                "file": fname,
                "category": matched_rule.category,
                "output": dst,
                "ok": True,
            })
        return results
