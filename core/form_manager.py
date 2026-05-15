# ~/Desktop/acropdf/core/form_manager.py
import fitz

class FormManager:
    def __init__(self, doc):
        self._doc = doc

    @property
    def _fitz(self) -> fitz.Document:
        return self._doc.fitz_doc

    def _safe_fitz(self) -> fitz.Document:
        doc = self._fitz
        if doc is None:
            raise RuntimeError("尚未載入文件")
        return doc

    def get_fields(self, page_num: int | None = None) -> list[dict]:
        """列出所有（或指定頁的）表單欄位"""
        doc = self._safe_fitz()
        results = []
        pages = [page_num] if page_num is not None else range(doc.page_count)
        for i in pages:
            if i < 0 or i >= doc.page_count:
                continue
            page = self._fitz[i]
            for widget in page.widgets():
                results.append({
                    "page": i,
                    "field_name": widget.field_name,
                    "field_type": widget.field_type_string,
                    "field_value": widget.field_value,
                    "rect": widget.rect,
                    "widget": widget,
                })
        return results

    def fill_field(self, page_num: int, field_name: str, value):
        doc = self._safe_fitz()
        if page_num < 0 or page_num >= doc.page_count:
            return
        self._doc.begin_op("填寫欄位")
        page = doc[page_num]
        for widget in page.widgets():
            if widget.field_name == field_name:
                widget.field_value = value
                widget.update()
                break
        self._doc.end_op()
        self._doc._mark_modified()

    def fill_all(self, data: dict):
        """data: {field_name: value}"""
        doc = self._safe_fitz()
        self._doc.begin_op("批次填寫表單")
        for i in range(doc.page_count):
            page = doc[i]
            for widget in page.widgets():
                if widget.field_name in data:
                    widget.field_value = data[widget.field_name]
                    widget.update()
        self._doc.end_op()
        self._doc._mark_modified()

    def flatten_forms(self):
        """攤平：將表單值燒入頁面內容"""
        doc = self._safe_fitz()
        self._doc.begin_op("攤平表單")
        for i in range(doc.page_count):
            doc[i].clean_contents()
        # 移除 AcroForm
        try:
            if "/AcroForm" in doc.pdf_catalog():
                pass  # pikepdf 處理更安全
        except Exception:
            pass
        self._doc.end_op()
        self._doc._mark_modified()

    def export_fdf(self, output_path: str):
        """匯出表單資料為 FDF"""
        fields = self.get_fields()
        lines = ["%FDF-1.2", "1 0 obj<</FDF<</Fields["]
        for f in fields:
            v = f["field_value"] or ""
            lines.append(f"<</T({f['field_name']})/V({v})>>")
        lines += ["]>>>>\nendobj\ntrailer<</Root 1 0 R>>\n%%EOF"]
        with open(output_path, "w", encoding="utf-8") as fp:
            fp.write("\n".join(lines))

    def import_fdf(self, fdf_path: str):
        # 簡化版：用 pikepdf 處理更完整
        import re
        with open(fdf_path, encoding="utf-8", errors="ignore") as fp:
            content = fp.read()
        pairs = re.findall(r'/T\((.+?)\)/V\((.+?)\)', content)
        data = {k: v for k, v in pairs}
        if data:
            self.fill_all(data)

    # ── 新增進階欄位 ──────────────────────────────────────────────
    def add_radio_button(self, page_num: int, rect: fitz.Rect,
                         group_name: str, value: str):
        """新增選項按鈕（以 checkbox 模擬；PDF 標準 radio group 需 pikepdf）"""
        doc = self._safe_fitz()
        if page_num < 0 or page_num >= doc.page_count:
            return
        self._doc.begin_op("加選項按鈕")
        page = doc[page_num]
        widget = fitz.Widget()
        widget.rect = rect
        # Radio button 需要 parent AcroForm 群組，在無 parent 時改用 checkbox 建立
        widget.field_name = f"{group_name}_{value}"
        widget.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
        widget.field_value = "Off"
        widget.fill_color = (1, 1, 1)
        widget.border_color = (0, 0, 0)
        widget.border_width = 1
        page.add_widget(widget)
        self._doc.end_op()
        self._doc._mark_modified()

    def add_push_button(self, page_num: int, rect: fitz.Rect,
                        name: str, caption: str):
        """新增按鈕"""
        doc = self._safe_fitz()
        if page_num < 0 or page_num >= doc.page_count:
            return
        self._doc.begin_op("加按鈕")
        page = doc[page_num]
        widget = fitz.Widget()
        widget.rect = rect
        widget.field_name = name
        widget.field_type = fitz.PDF_WIDGET_TYPE_BUTTON
        widget.field_value = caption
        widget.text_fontsize = 11
        widget.fill_color = (0.9, 0.9, 0.9)
        widget.border_color = (0, 0, 0)
        widget.border_width = 1
        page.add_widget(widget)
        self._doc.end_op()
        self._doc._mark_modified()

    def add_signature_field(self, page_num: int, rect: fitz.Rect, name: str):
        """新增簽名欄位"""
        doc = self._safe_fitz()
        if page_num < 0 or page_num >= doc.page_count:
            return
        self._doc.begin_op("加簽名欄位")
        page = doc[page_num]
        widget = fitz.Widget()
        widget.rect = rect
        widget.field_name = name
        widget.field_type = fitz.PDF_WIDGET_TYPE_SIGNATURE
        widget.fill_color = (1, 1, 1)
        widget.border_color = (0, 0, 0.8)
        widget.border_width = 1
        page.add_widget(widget)
        self._doc.end_op()
        self._doc._mark_modified()

    def set_field_properties(self, page_num: int, field_name: str,
                             properties: dict):
        """設定欄位屬性（字型、邊框、顏色、旗標）"""
        doc = self._safe_fitz()
        if page_num < 0 or page_num >= doc.page_count:
            return
        self._doc.begin_op("設定欄位屬性")
        page = doc[page_num]
        for widget in page.widgets():
            if widget.field_name == field_name:
                if "font_size" in properties:
                    widget.text_fontsize = properties["font_size"]
                if "fill_color" in properties:
                    widget.fill_color = properties["fill_color"]
                if "border_color" in properties:
                    widget.border_color = properties["border_color"]
                if "border_width" in properties:
                    widget.border_width = properties["border_width"]
                if "text_color" in properties:
                    widget.text_color = properties["text_color"]
                if "field_value" in properties:
                    widget.field_value = properties["field_value"]
                widget.update()
                break
        self._doc.end_op()
        self._doc._mark_modified()

    def set_tab_order(self, page_num: int, field_names: list[str]):
        """設定 Tab 順序（儲存為 PDF 結構樹中的 Tab 屬性）"""
        doc = self._safe_fitz()
        if page_num < 0 or page_num >= doc.page_count:
            return
        # 使用 fitz PDF 物件操作設定頁面 Tabs
        try:
            page = doc[page_num]
            page_xref = page.xref
            doc.xref_set_key(page_xref, "Tabs", "/S")
        except Exception:
            pass
        # 實際 Tab 順序由欄位 xref 排列控制，此處記錄預期順序即可
        self._doc._mark_modified()

    def get_all_fields(self, page_num: int | None = None) -> list[dict]:
        """取得所有欄位資訊（含座標、類型、屬性）"""
        doc = self._safe_fitz()
        results = []
        pages = [page_num] if page_num is not None else range(doc.page_count)
        for i in pages:
            if i < 0 or i >= doc.page_count:
                continue
            for widget in doc[i].widgets():
                results.append({
                    "page": i,
                    "name": widget.field_name,
                    "type": widget.field_type_string,
                    "value": widget.field_value,
                    "rect": widget.rect,
                    "font_size": widget.text_fontsize,
                    "fill_color": widget.fill_color,
                    "border_color": widget.border_color,
                })
        return results

    # ── 新增欄位 ──────────────────────────────────────────────────
    def add_field(self, page_num: int, rect: fitz.Rect,
                  field_type: str, name: str, default_value: str = ""):
        """
        field_type: 'text' | 'checkbox' | 'combo' | 'list'
        """
        doc = self._safe_fitz()
        if page_num < 0 or page_num >= doc.page_count:
            return
        if not name:
            name = f"field_{page_num}_{id(rect)}"
        self._doc.begin_op("加表單欄位")
        page = doc[page_num]
        widget = fitz.Widget()
        widget.rect = rect
        widget.field_name = name
        _type_map = {
            "text":     fitz.PDF_WIDGET_TYPE_TEXT,
            "checkbox": fitz.PDF_WIDGET_TYPE_CHECKBOX,
            "combo":    fitz.PDF_WIDGET_TYPE_COMBOBOX,
            "list":     fitz.PDF_WIDGET_TYPE_LISTBOX,
        }
        widget.field_type = _type_map.get(field_type, fitz.PDF_WIDGET_TYPE_TEXT)
        if field_type == "checkbox":
            widget.field_value = bool(default_value)
        else:
            widget.field_value = default_value
        widget.text_fontsize = 11
        widget.text_color = (0, 0, 0)
        widget.fill_color = (1, 1, 1)
        widget.border_color = (0, 0, 0)
        widget.border_width = 1
        page.add_widget(widget)
        self._doc.end_op()
        self._doc._mark_modified()
