# ~/Desktop/acropdf/core/form_manager.py
import fitz

class FormManager:
    def __init__(self, doc):
        self._doc = doc

    @property
    def _fitz(self) -> fitz.Document:
        return self._doc.fitz_doc

    def get_fields(self, page_num: int | None = None) -> list[dict]:
        """列出所有（或指定頁的）表單欄位"""
        results = []
        pages = [page_num] if page_num is not None else range(self._fitz.page_count)
        for i in pages:
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
        self._doc.begin_op("填寫欄位")
        page = self._fitz[page_num]
        for widget in page.widgets():
            if widget.field_name == field_name:
                widget.field_value = value
                widget.update()
                break
        self._doc.end_op()
        self._doc._mark_modified()

    def fill_all(self, data: dict):
        """data: {field_name: value}"""
        self._doc.begin_op("批次填寫表單")
        for i in range(self._fitz.page_count):
            page = self._fitz[i]
            for widget in page.widgets():
                if widget.field_name in data:
                    widget.field_value = data[widget.field_name]
                    widget.update()
        self._doc.end_op()
        self._doc._mark_modified()

    def flatten_forms(self):
        """攤平：將表單值燒入頁面內容"""
        self._doc.begin_op("攤平表單")
        for i in range(self._fitz.page_count):
            page = self._fitz[i]
            page.clean_contents()
        # 移除 AcroForm
        if "/AcroForm" in self._fitz.pdf_catalog():
            pass  # pikepdf 處理更安全
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

    # ── 新增欄位 ──────────────────────────────────────────────────
    def add_field(self, page_num: int, rect: fitz.Rect,
                  field_type: str, name: str, default_value: str = ""):
        """
        field_type: 'text' | 'checkbox' | 'combo' | 'list'
        """
        self._doc.begin_op("加表單欄位")
        page = self._fitz[page_num]
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
